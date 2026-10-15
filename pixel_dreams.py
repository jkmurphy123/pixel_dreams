#!/usr/bin/env python3
# pixel_dreams.py
#
# Unified mode controller — replaces the old mode_controller.py,
# single_mode_controller.py, and auto_mode_controller.py.
#
# Usage:
#   python3 pixel_dreams.py --show_modes
#   python3 pixel_dreams.py --play 3                     # single mode, ESC quits
#   python3 pixel_dreams.py --play 3 --windowed --width 1280 --height 720
#   python3 pixel_dreams.py                              # manual: arrows switch, ESC quits
#   python3 pixel_dreams.py --auto 30                    # auto-cycle every 30s
#   python3 pixel_dreams.py --auto 30 --shuffle --start 2
#   python3 pixel_dreams.py --input rotary               # Raspberry Pi rotary encoder
#
# Input:
#   keyboard (default): LEFT/RIGHT switch modes, ESC quits
#   rotary (--input rotary): knob switches, tap quits, hold 2s reboots (Pi only)

import argparse
import os
import sys
import time

import pygame

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core import profiles as profiles_mod
from core.bus import ControlBus, require_loopback_or_token
from core.config import (
    enabled_mode_indices,
    infer_max_modes_from_config,
    list_configured_modes,
    load_project_config,
    load_secrets,
)
from core.hardware import RotaryHardware
from core.manager import ModeManager
from core.playlist import Playlist
from core.store import sha256_file


def _rss_mb() -> float:
    """Resident memory, for the verification runs. Linux /proc first, rusage as backup."""
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except Exception:
        pass
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:
        return float("nan")


def _summary(frames: int, elapsed: float, panel_url: str | None) -> str:
    """One parseable line about a completed run (used by the Phase 1 verification)."""
    avg = (frames / elapsed) if elapsed > 0 else 0.0
    return (f"[Controller] Summary: frames={frames} elapsed={elapsed:.2f}s "
            f"avg_fps={avg:.1f} rss_mb={_rss_mb():.1f} "
            f"nicegui_imported={'nicegui' in sys.modules} "
            f"panel={panel_url or 'off'}")


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="pixel_dreams — kiosk mode controller"
    )

    parser.add_argument("--show_modes", action="store_true",
                        help="List all configured modes and exit")
    parser.add_argument("--play", type=int, default=None, metavar="N",
                        help="Play only mode N (no switching)")
    parser.add_argument("--auto", type=float, default=None, metavar="SECONDS",
                        help="Auto-cycle through modes every N seconds")
    parser.add_argument("--start", type=int, default=0,
                        help="Mode index to start on (default: 0)")
    parser.add_argument("--shuffle", action="store_true",
                        help="Cycle through modes in random order (with --auto)")
    parser.add_argument("--max-modes", type=int, default=None,
                        help="Override maximum number of modes")
    parser.add_argument("--input", choices=["keyboard", "rotary", "none"],
                        default="keyboard",
                        help="Input source for mode switching (default: keyboard)")
    parser.add_argument("--config", default=None, metavar="FILE",
                        help="Override modes config file (default: from registry settings)")

    parser.add_argument("--windowed", action="store_true",
                        help="Run in a window instead of fullscreen")
    parser.add_argument("--width", type=int, default=1280,
                        help="Window width (used with --windowed)")
    parser.add_argument("--height", type=int, default=720,
                        help="Window height (used with --windowed)")

    parser.add_argument("--gc-seconds", type=float, default=30.0,
                        help="Run gc.collect() every N seconds (default: 30, 0 disables)")

    # ---- control panel (see AGENTS.md, "the thread contract") ----
    parser.add_argument("--panel-port", type=int, default=None, metavar="N",
                        help="Serve the web control panel on port N (default: off)")
    parser.add_argument("--panel-bind", default="127.0.0.1", metavar="ADDR",
                        help="Panel bind address (default: 127.0.0.1). A non-loopback address "
                             "requires panel_token in secrets.json")
    parser.add_argument("--panel-only", action="store_true",
                        help="Serve the panel without initialising pygame (no display needed)")
    parser.add_argument("--frames", type=int, default=None, metavar="N",
                        help="Exit after N frames (verification aid)")

    args = parser.parse_args(argv[1:])

    if args.auto is not None and args.auto <= 0:
        parser.error("--auto duration must be > 0")
    if args.max_modes is not None and args.max_modes < 1:
        parser.error("--max-modes must be >= 1")
    if args.width <= 0 or args.height <= 0:
        parser.error("--width and --height must be > 0")
    if args.gc_seconds < 0:
        parser.error("--gc-seconds must be >= 0")
    if args.play is not None and args.auto is not None:
        parser.error("--play and --auto are mutually exclusive")
    if args.panel_port is not None and not (1 <= args.panel_port <= 65535):
        parser.error("--panel-port must be between 1 and 65535")
    if args.panel_only and args.panel_port is None:
        parser.error("--panel-only needs --panel-port N (there is nothing else to serve)")
    if args.frames is not None and args.frames < 1:
        parser.error("--frames must be >= 1")

    return args


def main(argv=None):
    args = parse_args(argv or sys.argv)

    registry_json, registry, modes_config, config_path = load_project_config(
        BASE_DIR, config_override=args.config
    )
    secrets = load_secrets(BASE_DIR)
    max_modes = args.max_modes or infer_max_modes_from_config(modes_config)

    if args.show_modes:
        list_configured_modes(modes_config, config_path)
        return 0

    print(f"[Controller] Max modes: {max_modes}")

    # ---------------- control bus + panel ----------------

    bus = ControlBus()
    profile_path, profile_source = profiles_mod.resolve_active_profile(BASE_DIR, args.config)
    bus.update_status(profile_abs=profile_path,
                      profile_rel=os.path.relpath(profile_path, BASE_DIR),
                      profile_source=profile_source,
                      mode_count=max_modes)

    panel = None
    panel_url = None
    if args.panel_port is not None:
        try:
            require_loopback_or_token(args.panel_bind, secrets.get("panel_token"))
        except ValueError as e:
            print(f"[Panel] Refusing to start: {e}")
            return 2
        from panel import start_panel          # lazy: imports nicegui only when enabled
        panel = start_panel(
            base_dir=BASE_DIR, bus=bus, host=args.panel_bind, port=args.panel_port,
            token=secrets.get("panel_token"), config_override=args.config,
        )
        panel_url = panel.url
        print(f"[Panel] Control panel on {panel_url} (bind {args.panel_bind})")

    if args.panel_only:
        # No display at all: the panel is the whole program.
        bus.update_status(display="off")
        print("[Panel] --panel-only: no display initialised. Ctrl-C to stop.")
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        print(_summary(0, 0.0, panel_url))
        return 0

    # ---------------- pygame shell ----------------

    pygame.init()
    pygame.display.init()
    pygame.font.init()
    pygame.mouse.set_visible(False)

    if args.windowed:
        screen = pygame.display.set_mode((args.width, args.height), pygame.RESIZABLE)
        pygame.display.set_caption("pixel_dreams — windowed")
    else:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption("pixel_dreams")

    # ---------------- playlist / manager ----------------

    single_mode_lock = args.play is not None
    # The rotation honours each mode's "enabled" flag from the first frame, not only after a
    # panel save: disabling a mode and restarting must keep it off.
    allowed_modes, enabled_fell_back = enabled_mode_indices(modes_config)
    configured = sorted(int(k) for k in modes_config if str(k).isdigit())
    # The profile's OWN answer, which is not the same as the rotation's when every mode is
    # disabled and the fallback kicks in. Reporting both is what lets the panel say "this profile
    # disables everything, so the app is ignoring the flag to avoid a blank wall".
    disabled_modes = [i for i in configured
                      if modes_config.get(str(i), {}).get("enabled") is False]
    if single_mode_lock:
        playlist = Playlist.single(args.play % max_modes)
        print(f"[Controller] Single-mode lock: mode {args.play % max_modes}")
    else:
        playlist = Playlist(max_modes, shuffle=args.shuffle,
                            start_index=args.start % max_modes, allowed=allowed_modes)
        if enabled_fell_back:
            print("[Controller] WARNING: every mode is disabled in this profile — playing them "
                  "all anyway so the wall does not go blank")
        elif disabled_modes:
            print(f"[Controller] Rotation: {len(allowed_modes)} of {len(configured)} mode(s) "
                  f"enabled (disabled: {disabled_modes})")

    manager = ModeManager(screen, registry, modes_config, max_modes, secrets)
    manager.start(initial_index=playlist.current)
    bus.update_status(
        display="windowed" if args.windowed else "fullscreen",
        mode_index=manager.mode_index,
        # What this process is actually running, so the panel can say whether the file on disk is
        # what is on the wall (and spot a save that has not been applied).
        applied_config_path=config_path,
        applied_config_sha256=sha256_file(config_path) if os.path.exists(config_path) else "",
        enabled_modes=allowed_modes,
        disabled_modes=disabled_modes,
        enabled_fell_back=enabled_fell_back,
        applied_rotation=playlist.entries if not single_mode_lock else [playlist.current],
        max_modes=max_modes,
        # The mode's identity and the digest of the config it was built from, present from the
        # first frame: a consumer must never have to guess whether a missing key means "not yet".
        mode_type=type(manager.current_mode).__name__ if manager.current_mode else None,
        mode_name=(modes_config.get(str(manager.mode_index), {}).get("name")
                   or modes_config.get(str(manager.mode_index), {}).get("title") or ""),
        mode_config_digest=manager.last_build_digest,
        mode_build_index=manager.last_build_index,
        # Present from the first frame so a consumer never has to guess a default
        applies_count=0,
        refresh_count=0,
        pending_steps=0,
        # Whether this app is locked to one mode (--play N): the panel needs it to explain why the
        # Next/Prev controls are unavailable, rather than offering buttons that do nothing.
        single_mode=single_mode_lock,
    )

    # ---------------- hardware input (optional) ----------------

    hardware = None
    quit_requested = False

    if args.input == "rotary" and not single_mode_lock:
        def on_rotate(delta):
            if manager.is_transitioning():
                return
            playlist.advance(delta)
            manager.request_switch(playlist.current)

        def on_tap():
            nonlocal quit_requested
            quit_requested = True

        def on_hold():
            print("[Controller] Encoder held 2s -> rebooting")
            os.system("sudo reboot")

        hardware = RotaryHardware(on_rotate, on_tap, on_hold)
        if hardware.setup():
            hardware.set_mode(manager.mode_index)
        else:
            hardware = None
            print("[Controller] Falling back to keyboard input")

    # ---------------- main loop ----------------

    clock = pygame.time.Clock()
    elapsed_in_mode = 0.0
    queued_delta = 0
    pending_refresh = False
    last_gc = time.time()

    # Panel plumbing, all of it inside the frame loop:
    #   * frame counter + a real fps sample (not the 60 we asked for)
    #   * bus.dispatch() applies at most MAX_DRAIN_PER_FRAME panel commands per frame
    #   * status is published at ~4Hz so a panel poll never sees a stale mode
    started = time.time()
    frame = 0
    fps = 0.0
    sample_at = started
    sample_frame = 0

    def _publish() -> None:
        mode = manager.current_mode
        cfg = manager.modes_config.get(str(manager.mode_index), {})
        bus.update_status(
            frame=frame,
            fps=fps,
            uptime_s=time.time() - started,
            mode_index=manager.mode_index,
            mode_type=type(mode).__name__ if mode is not None else None,
            mode_name=(cfg.get("name") or cfg.get("title") or "") if isinstance(cfg, dict) else "",
            # Proof of WHICH config the mode on screen was built from: after a refresh this must
            # match the profile file, and the panel says so on the status card.
            mode_config_digest=manager.last_build_digest,
            mode_build_index=manager.last_build_index,
        )

    def _panel_ping(_cmd) -> None:
        # The pump the panel uses to prove the loop is alive and reachable.
        pongs = bus.status("pong_count", 0) or 0
        bus.update_status(pong_count=int(pongs) + 1)

    def _apply_config(cmd) -> None:
        """
        The panel wrote the files and sent the finished dicts; the loop only swaps references.

        Rebuilds the rotation from the new config's enabled set, so disabling a mode takes effect
        without a restart. If the mode on screen is no longer in the rotation it fades away like a
        normal switch would, and `refresh` rebuilds the mode on screen so edited parameters appear.
        """
        nonlocal playlist, pending_refresh
        new_modes = cmd.get("modes_config") or {}
        if not isinstance(new_modes, dict) or not new_modes:
            print("[Panel] apply ignored: the payload carried no modes")
            return

        max_modes = cmd.get("max_modes") or infer_max_modes_from_config(new_modes)
        report = manager.apply_config(registry=cmd.get("registry") or manager.registry,
                                     modes_config=new_modes, max_modes=max_modes)
        allowed, fell_back = enabled_mode_indices(new_modes)

        if not single_mode_lock:
            start = min(manager.mode_index, max(0, max_modes - 1))
            playlist = Playlist(max_modes, shuffle=args.shuffle, start_index=start, allowed=allowed)
            if playlist.current != manager.mode_index:
                manager.request_switch(playlist.current)

        applies = (bus.status("applies_count", 0) or 0) + 1
        all_indices = sorted(int(k) for k in new_modes if str(k).isdigit())
        bus.update_status(
            applies_count=applies,
            applied_config_path=cmd.get("config_path") or "",
            applied_config_sha256=cmd.get("config_sha256") or "",
            max_modes=max_modes,
            enabled_modes=allowed,
            # The profile's own answer, not the rotation's: when every mode is disabled the
            # fallback plays them all, and both facts have to be visible or the panel would claim
            # the flag was respected when it was deliberately overridden.
            disabled_modes=[i for i in all_indices
                            if (new_modes.get(str(i)) or {}).get("enabled") is False],
            enabled_fell_back=fell_back,
            last_apply_at=time.time(),
            applied_rotation=playlist.entries if not single_mode_lock else [playlist.current],
        )
        if fell_back:
            print("[Panel] WARNING: every mode is disabled — keeping them all so the wall keeps "
                  "showing something")
        print(f"[Panel] applied {os.path.basename(cmd.get('config_path') or '?')}: "
              f"{len(allowed)} enabled mode(s)"
              + (f", max_modes={max_modes}" if report.get("max_modes_changed") else ""))
        if cmd.get("refresh"):
            pending_refresh = True

    def _refresh_mode(_cmd) -> None:
        """Queue a rebuild of the mode on screen (done at the next frame that is not fading)."""
        nonlocal pending_refresh
        pending_refresh = True

    def _step_mode(cmd) -> None:
        """
        Next/Prev from the panel: exactly the path a LEFT/RIGHT key press takes.

        Reusing that path is the point — a step that arrives during a fade is QUEUED rather than
        dropped (the keyboard already does this with `queued_delta`), so clicking Next twice quickly
        advances twice instead of losing the second click. A manual step also resets the auto-cycle
        timer, so with `--auto` running you get the mode you asked for and a full interval on it.

        Refused when `--play N` locked the app to a single mode: there is no rotation to step
        through, and the panel says so instead of offering buttons that do nothing.
        """
        nonlocal queued_delta, elapsed_in_mode
        if single_mode_lock:
            bus.update_status(last_step="refused: this app was started with --play (single mode)")
            return
        try:
            delta = int(cmd.get("delta", 1))
        except (TypeError, ValueError):
            delta = 1
        delta = 1 if delta > 0 else -1

        if manager.is_transitioning():
            queued_delta += delta
            bus.update_status(last_step=f"queued {'next' if delta > 0 else 'prev'} (mid-fade)",
                              pending_steps=queued_delta)
            print(f"[Panel] step queued ({delta:+d}); {queued_delta} pending")
            return

        playlist.advance(delta)
        manager.request_switch(playlist.current)
        elapsed_in_mode = 0.0
        bus.update_status(last_step=f"stepped {'next' if delta > 0 else 'prev'}",
                          pending_steps=queued_delta)
        print(f"[Panel] step {'next' if delta > 0 else 'prev'} -> mode {playlist.current}")

    handlers = {"ping": _panel_ping, "apply_config": _apply_config, "refresh_mode": _refresh_mode,
                "step_mode": _step_mode}

    if args.auto:
        print(f"[Controller] Auto-cycle every {args.auto:.1f}s. ESC quits.")
    elif single_mode_lock:
        print("[Controller] Running single mode. ESC quits.")
    else:
        print("[Controller] Manual mode. LEFT/RIGHT switch, ESC quits.")

    import gc as _gc

    try:
        while not quit_requested:
            dt = clock.tick(60) / 1000.0
            elapsed_in_mode += dt
            frame += 1

            bus.dispatch(handlers)

            # A refresh requested while a fade was in flight waits here instead of landing
            # mid-transition (and is never silently dropped).
            if pending_refresh and not manager.is_transitioning():
                pending_refresh = False
                manager.refresh_current()
                refreshes = (bus.status("refresh_count", 0) or 0) + 1
                bus.update_status(refresh_count=refreshes, last_refresh_at=time.time(),
                                  refreshed_mode=manager.mode_index)
                print(f"[Panel] refreshed mode {manager.mode_index} from the live config")

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    quit_requested = True
                    continue

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        quit_requested = True
                        continue

                    if not single_mode_lock and args.input == "keyboard":
                        if event.key == pygame.K_RIGHT:
                            if manager.is_transitioning():
                                queued_delta += 1
                            else:
                                playlist.advance(+1)
                                manager.request_switch(playlist.current)
                                elapsed_in_mode = 0.0
                            continue
                        if event.key == pygame.K_LEFT:
                            if manager.is_transitioning():
                                queued_delta -= 1
                            else:
                                playlist.advance(-1)
                                manager.request_switch(playlist.current)
                                elapsed_in_mode = 0.0
                            continue

                manager.handle_event(event)

            # Apply arrow presses queued during a fade, once stable
            if not single_mode_lock and not manager.is_transitioning() and queued_delta != 0:
                step = 1 if queued_delta > 0 else -1
                queued_delta -= step
                playlist.advance(step)
                manager.request_switch(playlist.current)
                elapsed_in_mode = 0.0
                # Keep the panel's view of pending steps honest: it shows "N queued" while a burst
                # is working through, and a stale count would make the buttons look stuck.
                bus.update_status(pending_steps=queued_delta, mode_index=manager.mode_index)

            # Auto-cycle
            if (args.auto is not None and not single_mode_lock
                    and not manager.is_transitioning()
                    and elapsed_in_mode >= args.auto):
                playlist.advance(+1)
                manager.request_switch(playlist.current)
                elapsed_in_mode = 0.0

            manager.update(dt)
            manager.render()
            pygame.display.flip()

            if hardware is not None:
                hardware.set_mode(manager.mode_index)

            if args.gc_seconds > 0:
                now = time.time()
                if now - last_gc >= args.gc_seconds:
                    _gc.collect()
                    last_gc = now

            # Publish status only a few times a second: the loop's own timing stays the
            # loop's business, and the panel's poll reads a small dict.
            if time.time() - sample_at >= 0.25:
                span = time.time() - sample_at
                fps = (frame - sample_frame) / span if span > 0 else 0.0
                sample_at, sample_frame = time.time(), frame
                _publish()

            if args.frames is not None and frame >= args.frames:
                print(f"[Controller] Reached --frames {args.frames}")
                break

    finally:
        print("[Controller] Quitting cleanly...")
        try:
            if manager.current_mode is not None:
                manager.current_mode.exit()
        except Exception:
            pass
        if hardware is not None:
            hardware.close()
        try:
            pygame.quit()
        except Exception:
            pass

    print("[Controller] Exited.")
    if args.frames is not None:
        print(_summary(frame, time.time() - started, panel_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
