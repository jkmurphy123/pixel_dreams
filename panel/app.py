# panel/app.py
#
# The control panel's NiceGUI pages.
#
# The pages show which profile the display is using, that profile's modes, the render loop's live
# status — and, since Phase 3, let you EDIT a mode's parameters and save them while the kiosk runs.
#
# What is where:
#   * the FILE is the truth for editing (core.editor.ProfileEditor stages and writes it);
#   * the running app's status is the truth for what is on the wall;
#   * the difference between the two is shown on the mode page instead of being assumed.
#
# Everything here runs on the panel thread. It may read files and the ControlBus; it must never
# touch pygame, ModeManager or a mode object, and the render thread must never touch disk. See
# AGENTS.md for the thread contract. The panel does the disk I/O; the loop only swaps dicts.
#
# Two shapes are used deliberately:
#   * status labels are built ONCE and updated in place through a dict of element references
#     (never a timed page rebuild), so a poll cannot destroy anything a client is using;
#   * the mode list is rebuilt only when the user changes the inspected profile or clicks
#     Reload from disk;
#   * the editing form is @ui.refreshable so Save/Revert/Reload can re-render fields from the
#     file, while a field change only refreshes the small staged-changes summary (which keeps
#     focus in the box you are typing in).

from __future__ import annotations

import json
import os
import secrets as _secrets
import time
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from nicegui import app, context, ui

from core import profiles as profiles_mod
from core.bus import APP_NAME, APP_VERSION, ControlBus, is_loopback
from core.config import (
    config_digest,
    enabled_mode_indices,
    infer_max_modes_from_config,
    load_json,
    normalize_type,
    read_active_profile,
)
from core.editor import (
    EditorRefused,
    ProfileEditor,
    create_profile,
    list_backups,
    load_payload,
    restore_backup,
    switch_profile,
)
from core.layout_edit import (
    LayoutEditor,
    backgrounds_dir,
    resolve_background,
    create_freeform,
    list_backgrounds,
    list_layouts,
)
from core.params import GROUPS, group_params, resolve_params, validate_param_value
from core.store import sha256_file

#: How often the status labels are refreshed (a poll, never a page rebuild).
REFRESH_SECONDS = 1.0

#: Cookie the auth route sets, so the token is not needed in every URL.
COOKIE_NAME = "pd_panel_token"

#: How long the access cookie lasts: 60 days. Long enough that a laptop or tablet you use to tune
#: the kiosk does not ask for the token every session, which was the whole friction this removes.
#: The tradeoff is deliberate and worth stating: a browser that remembers this cookie is a device
#: that can open the panel without the token, so the cookie now outlives the browser session.
#: Rotation is "edit panel_token in secrets.json" — the cookie then stops matching.
COOKIE_MAX_AGE_SECONDS = 60 * 24 * 60 * 60

#: The one path that must be reachable without a token (it is how you get one).
AUTH_PATH = "/_panel/auth"


@dataclass
class PageContext:
    """Everything the pages need. Handed to register_pages() once at startup."""

    base_dir: str
    bus: ControlBus
    bind: str = "127.0.0.1"
    port: int = 8090
    token: str | None = None
    config_override: str | None = None

    @property
    def token_required(self) -> bool:
        """A panel reachable off-machine must be gated; a loopback bind needs no token."""
        return not is_loopback(self.bind)


# ---------------------------------------------------------------- formatting helpers

def _fmt_uptime(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _fmt_ago(stamp: float | None) -> str:
    if not stamp:
        return "never"
    delta = time.time() - stamp
    if delta < 5:
        return "just now"
    if delta < 90:
        return f"{delta:.0f}s ago"
    return f"{delta / 60:.1f}m ago"


def _mode_text(snap: dict) -> str:
    if snap.get("mode_index") is None:
        return "no mode active"
    name = snap.get("mode_name") or ""
    return f"{snap['mode_index']} — {snap.get('mode_type')}" + (f" — {name}" if name else "")


def _loop_text(snap: dict, uptime: float) -> str:
    if snap.get("display") == "off":
        return "not attached (panel-only: no display initialised in this process)"
    return (f"{snap.get('display')}, {snap.get('fps', 0.0):.1f} fps, "
            f"frame {snap.get('frame', 0)}, up {_fmt_uptime(uptime)}, pid {snap.get('pid')}")


def _rotation_text(snap: dict) -> str:
    """
    What the running app is actually rotating through — the APP's answer, not the file's.

    The two can disagree (a saved change that has not been applied, or a profile the app did not
    load), and seeing the applied filename and hash next to the editor's is how you tell.
    """
    if snap.get("display") == "off":
        return "no display process attached to this panel"
    rotation = snap.get("applied_rotation")
    if not rotation:
        return "starting up"
    enabled = snap.get("enabled_modes") or []
    max_modes = snap.get("max_modes", "?")
    text = f"playing {rotation} — {len(enabled)} of {max_modes} slot(s) enabled"
    if snap.get("enabled_fell_back"):
        text += ("; WARNING: the profile disables EVERY mode, so the app is ignoring the flag to "
                 "keep the wall from going blank")
    elif snap.get("disabled_modes"):
        text += f"; disabled: {snap['disabled_modes']}"
    path = snap.get("applied_config_path")
    if path:
        text += f" · {os.path.basename(path)} @ {str(snap.get('applied_config_sha256') or '')[:10]}"
    return text


def _render_switch_button(container, ctx: PageContext, state: dict, info, is_active: bool,
                          after) -> None:
    """
    The one control that changes what the display is showing: make the inspected profile active.

    Not offered when the profile is already active, and replaced by an explanation when the app was
    started with --config — that flag outranks the record at every restart, so a switch here would
    look like it worked and be gone after a reboot.

    The outcome is kept in `state` and rendered on the next build, because a successful switch
    re-renders this container (the mode list changes with the profile) and would otherwise wipe the
    message just before the user could read it.
    """
    container.clear()
    if info is None:
        return
    with container:
        prior = state.get("switch_outcome")
        if prior:
            text, colour = prior
            ui.label(text).classes(f"text-xs {colour}").mark("switch-outcome")

        if is_active:
            ui.label("This profile is active.").classes("text-xs opacity-60")
            return
        if ctx.config_override:
            ui.label(f"--config {ctx.config_override} pins the profile at every restart; restart "
                     f"without it to switch from here.") \
                .classes("text-xs text-orange-300").mark("switch-blocked")
            return

        def do_switch() -> None:
            result = switch_profile(ctx.base_dir, info.path, _load_registry(ctx.base_dir),
                                    config_override=ctx.config_override)
            if not result.ok:
                detail = " ".join([result.reason] + list(result.errors))
                state["switch_outcome"] = (detail, "text-red-400")
            else:
                ctx.bus.post(_apply_payload(ctx, result.profile_abs, refresh=True))
                state["switch_outcome"] = (
                    f"Switched: {result.profile} is now the active profile, recorded in "
                    f"runtime/active_profile.json, and the running app was told to reload it — "
                    f"no restart.", "text-green-400")
            after(result)

        ui.button(f"Switch the display to {info.rel}", on_click=do_switch) \
            .props("color=primary").mark("switch-profile")
        ui.label("Writes runtime/active_profile.json (one line, gitignored) and reloads the "
                 "running app. It refuses a profile that does not validate.") \
            .classes("text-xs opacity-50")


def _create_summary(result) -> str:
    """
    The report after a create, in full: what landed, where each value came from, and what still
    needs a human. Summarising this to "created" would hide the two things that matter — the
    placeholders and the modes that could not be included at all.
    """
    parts = [f"Created {result.rel} — {result.modes} modes"]
    origin = []
    if result.inherited:
        origin.append(f"{len(result.inherited)} carried over from {result.seed or 'the seed profile'}")
    if result.at_defaults:
        origin.append(f"{len(result.at_defaults)} at registry defaults")
    parts.append(" (" + ", ".join(origin) + ")." if origin else ".")
    text = " ".join(parts)
    if result.placeholders:
        text += ("\nStill needs a value (" + str(len(result.placeholders)) +
                 "): " + ", ".join(result.placeholders) +
                 " — the registry records no real default for these, and a mode with an empty one "
                 "shows nothing until you fill it in.")
    if result.left_out:
        listed = "; ".join(f"{t} ({', '.join(keys)})" for t, keys in result.left_out)
        text += (f"\nLeft out ({len(result.left_out)}): {listed} — the registry declares these as "
                 f"required with no default, so an entry could not be written that the app would "
                 f"build. Give them defaults in the registry to include them.")
    if result.switched is not None:
        text += "\n" + ("Switched: " + result.switched.reason if result.switched.ok
                        else "Created, but not switched: " + result.switched.reason)
    return text


def _render_new_config(ctx: PageContext, after_create) -> None:
    """
    Create a new profile: every mode the registry knows, in a file you name, under configs/.

    This writes a file, so it can refuse but it can never be half-done: the name is checked, an
    existing file is never overwritten, and the document goes through the same validation and atomic
    write as an edit. The result is reported in full and the dialog stays open to be read, because
    the interesting part is rarely "created" — it is which values still need filling and which modes
    the registry declares but cannot be created at all.

    The one choice worth making here is the seed: copying the tuned values from the profile you are
    looking at (the default) means a new orientation starts from the settings you have already
    adjusted, rather than from nothing. Unticking it gives a file of bare registry defaults.
    """
    active_path, _ = profiles_mod.resolve_active_profile(ctx.base_dir, ctx.config_override)
    try:
        seed_rel = os.path.relpath(active_path, ctx.base_dir)
    except ValueError:                      # different drive: nothing sensible to show
        seed_rel = active_path

    dialog = ui.dialog()
    ui.button("New config…", on_click=dialog.open).props("outline").mark("new-config")

    with dialog, ui.card().classes("w-full max-w-2xl gap-2"):
        ui.label("New config").classes("text-base font-semibold")
        ui.label("Every mode in modes_registry.json, in one new file under configs/. Nothing else "
                 "in the project is touched, and an existing file is never overwritten.") \
            .classes("text-xs opacity-60")
        name_input = ui.input("File name", placeholder="modes_config_livingroom") \
            .classes("w-full").mark("new-config-name")
        ui.label(f"Saved as configs/<name>.json — '.json' is added if you leave it off.") \
            .classes("text-xs opacity-50")
        inherit = ui.checkbox(f"Copy the tuned values from {seed_rel}", value=True) \
            .mark("new-config-inherit")
        switch_it = ui.checkbox("Make it the active profile once it is created", value=False) \
            .mark("new-config-switch")
        outcome = ui.label().classes("text-xs whitespace-pre-line").mark("new-config-outcome")

        def do_create() -> None:
            result = create_profile(
                ctx.base_dir, name_input.value or "", _load_registry(ctx.base_dir),
                inherit_from=active_path if inherit.value else None,
                switch=bool(switch_it.value), config_override=ctx.config_override)
            if not result.ok:
                outcome.classes(replace="text-xs whitespace-pre-line text-red-400")
                outcome.set_text("Refused: " + " ".join([result.reason] + list(result.errors)))
                return
            if result.switched is not None and result.switched.ok:
                ctx.bus.post(_apply_payload(ctx, result.switched.profile_abs, refresh=True))
            outcome.classes(replace="text-xs whitespace-pre-line text-green-400")
            outcome.set_text(_create_summary(result))
            after_create(result)

        with ui.row().classes("items-center gap-2"):
            ui.button("Create", on_click=do_create).props("color=primary").mark("new-config-create")
            ui.button("Close", on_click=dialog.close).props("flat")


def _render_backups(container, ctx: PageContext, state: dict, after) -> None:
    """
    Restore a previous version of the profile being inspected.

    Two-step on purpose: the first click asks, the second does it. A restore replaces a live config,
    and one mis-click next to a list of timestamps is not a good way to make that decision.
    """
    container.clear()
    path, _ = profiles_mod.resolve_active_profile(ctx.base_dir, ctx.config_override)
    shown = state.get("view") or ""
    infos = profiles_mod.discover_profiles(ctx.base_dir, path)
    target = next((p for p in infos if p.rel == shown), None) or \
        next((p for p in infos if p.path == path), None)
    with container:
        if target is None:
            ui.label("No profile selected.").classes("text-xs opacity-60")
            return
        backups = list_backups(target.path)
        ui.label(f"{len(backups)} backup(s) of {target.rel} — taken automatically before every "
                 f"save, newest first.").classes("text-xs opacity-60")
        if not backups:
            ui.label("None yet: a backup appears the first time this profile is saved from here.") \
                .classes("text-xs opacity-50")
            return

        pending = state.get("pending_restore")

        def do_restore(backup: dict) -> None:
            result = restore_backup(target.path, backup["path"],
                                    registry=_load_registry(ctx.base_dir), base_dir=ctx.base_dir)
            if not result.ok:
                state["backup_outcome"] = (" ".join([result.reason] + list(result.errors)),
                                           "text-red-400")
            else:
                ctx.bus.post(_apply_payload(ctx, target.path, refresh=True))
                state["backup_outcome"] = (
                    f"Restored {backup['name']} ({backup['when']}) and reloaded the running app. "
                    f"The version it replaced was itself backed up, so this is undoable.",
                    "text-green-400")
            state["pending_restore"] = None
            after(None)

        outcome = state.get("backup_outcome")
        if outcome:
            ui.label(outcome[0]).classes(f"text-xs {outcome[1]}").mark("backup-outcome")

        for backup in backups[:20]:
            with ui.row().classes("w-full items-center gap-3 py-1 border-b border-white/5"):
                ui.label(backup["when"]).classes("font-mono text-xs w-44")
                ui.label(f"{backup['bytes']} bytes").classes("text-xs opacity-50 w-24")
                ui.label(backup["sha256"][:10]).classes("text-xs opacity-40 font-mono")
                if pending == backup["name"]:
                    def confirm(entry=backup) -> None:
                        do_restore(entry)

                    def cancel() -> None:
                        state["pending_restore"] = None
                        after(None)

                    ui.label("Restore this over the live profile?") \
                        .classes("text-xs text-amber-300 ml-auto")
                    ui.button("Yes, restore", on_click=confirm).props("color=primary dense") \
                        .mark("confirm-restore")
                    ui.button("No", on_click=cancel).props("flat dense")
                else:
                    def ask(name=backup["name"]) -> None:
                        state["pending_restore"] = name
                        after(None)

                    ui.button("restore", on_click=ask).props("flat dense ml-auto") \
                        .mark(f"restore-{backup['stamp']}")


def _transport_text(snap: dict) -> str:
    """
    What the Next/Prev buttons will do, said plainly: where we are, what is either side, and
    anything still queued. The loop owns the rotation, so this reads it rather than guessing.
    """
    if snap.get("single_mode"):
        return ("this app was started with --play (single mode), so there is no rotation to step "
                "through")
    if snap.get("display") == "off":
        return "no display is attached to this panel, so a step would have nothing to show"
    rotation = snap.get("applied_rotation") or []
    if not rotation:
        return "starting up"
    index = snap.get("mode_index")
    try:
        position = rotation.index(index)
    except ValueError:
        return f"showing mode {index}, which is not in the rotation the app reported"
    nxt = rotation[(position + 1) % len(rotation)]
    prev = rotation[(position - 1) % len(rotation)]
    text = (f"showing mode {index} — {position + 1} of {len(rotation)} in the rotation · "
            f"next {nxt}, prev {prev}")
    pending = snap.get("pending_steps") or 0
    if pending:
        text += f" · {pending} step(s) queued (mid-fade)"
    if snap.get("last_step"):
        text += f" · last: {snap['last_step']}"
    return text


def _transport_controls(ctx: PageContext, labels: dict) -> None:
    """
    Next/Prev, directly under the display status: the buttons for when the kiosk is across the room.

    They post one step to the render loop, which is the same thing LEFT/RIGHT already do on the
    keyboard — including the part where a press during a fade is QUEUED instead of dropped, so
    clicking Next twice quickly advances twice. `--auto` is unaffected while it runs; a manual step
    just resets its timer, so you get a full interval on the mode you picked.

    The hint line and the enabled state are driven by the status poll (see _refresh_status), so the
    buttons are never rebuilt under the cursor and their state follows the running app — including
    the single-mode case, where they are disabled rather than silently doing nothing.
    """
    state = {"enabled": None}

    def post_step(delta: int) -> None:
        ctx.bus.post({"cmd": "step_mode", "delta": delta})
        labels["transport"].set_text("stepping…" if delta > 0 else "stepping back…")

    with ui.card().classes("w-full mt-3 gap-2"):
        ui.label("Mode control").classes("text-base font-semibold")
        with ui.row().classes("items-center gap-2"):
            labels["transport_prev"] = ui.button("◀ Prev", on_click=lambda: post_step(-1)) \
                .props("outline").mark("prev-mode")
            labels["transport_next"] = ui.button("Next ▶", on_click=lambda: post_step(1)) \
                .props("color=primary").mark("next-mode")
            labels["transport"] = ui.label("—").classes("text-xs opacity-70 ml-2") \
                .mark("transport-hint")
        ui.label("One press, one step — no auto-cycling needed. Presses during a fade queue up "
                 "instead of being dropped, and with --auto running a manual step restarts that "
                 "timer.").classes("text-xs opacity-50").mark("transport-help")
    labels["transport_state"] = state


def _commands_text(snap: dict) -> str:
    text = f"{snap.get('commands_applied', 0)} applied"
    if snap.get("last_command"):
        text += f" (last: {snap['last_command']}, {_fmt_ago(snap.get('last_command_at'))})"
    if snap.get("commands_unknown"):
        text += f", {snap['commands_unknown']} unknown"
    return text


def _profile_option_label(info) -> str:
    bits = [info.label]
    if info.resolution:
        bits.append(info.resolution)
    if info.active:
        bits.append("ACTIVE")
    if info.error:
        bits.append(f"({info.error})")
    return " · ".join(bits) + f"   [{info.rel}]"


# ---------------------------------------------------------------- access rule

def _presented_token(request) -> str:
    """
    The token a request offers: header first (keeps it out of URLs and access logs), then
    the auth cookie, then a query parameter (first-visit convenience).
    """
    if request is None:
        return ""
    header = request.headers.get("x-panel-token")
    if header:
        return header
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        return cookie
    return request.query_params.get("token", "") or ""


def _authorised(ctx: PageContext, request) -> bool:
    """
    The panel's only access rule, checked in the page builder AND in the status endpoint:
    a page-level redirect is not protection for a route someone can call directly.
    """
    if not ctx.token_required:
        return True
    if not ctx.token:
        return False                      # start_panel() refuses this bind; belt and braces
    offered = _presented_token(request)
    return bool(offered) and _secrets.compare_digest(offered, ctx.token)


# ---------------------------------------------------------------- shared page frame

def _chrome(subtitle: str) -> None:
    """One frame for every panel page, defined once (per-page copies drift silently)."""
    with ui.header().classes("items-center justify-between px-6 py-3"):
        with ui.row().classes("items-baseline gap-3"):
            ui.label(APP_NAME).classes("text-lg font-semibold")
            ui.label("control panel").classes("text-sm opacity-70")
            ui.label(f"v{APP_VERSION}").classes("text-xs opacity-50")
        with ui.row().classes("gap-4 text-sm"):
            ui.link("Modes", "/").classes("text-inherit").mark("nav-modes")
            ui.link("Raw JSON", "/raw").classes("text-inherit").mark("nav-raw")
    with ui.column().classes("w-full max-w-5xl mx-auto px-4 py-2 gap-1"):
        ui.label(subtitle).classes("text-sm opacity-70")


def _footer() -> None:
    ui.label(
        "Edit and Save & Apply writes the profile and reloads the running app; the switch in the "
        "profile card changes which profile plays; Refresh rebuilds the current mode. Nothing here "
        "writes a file without a click, every save keeps a backup (see the Backups section), and a "
        "file that changed underneath you (another tab, an ssh edit) is refused rather than "
        "overwritten."
    ).classes("text-xs opacity-50")


def _render_refusal() -> None:
    """The page a token-less request gets. Never reveals the token."""
    with ui.column().classes("w-full max-w-3xl mx-auto px-4 py-8 gap-2"):
        ui.label("pixel_dreams control panel").classes("text-lg font-semibold")
        ui.label("A token is required.").classes("text-base")
        ui.label(
            "This panel is bound to a network address. Open /_panel/auth?token=<panel_token> "
            "once to set the access cookie, or send an X-Panel-Token header."
        ).classes("text-sm opacity-70")


# ---------------------------------------------------------------- routes

def register_pages(ctx: PageContext) -> None:
    """Declare every route. Called once, before the server starts."""
    if ctx.token_required:
        _install_token_gate(ctx)
        _register_auth_route(ctx)

    _register_layout_route(app, ctx)
    _register_layout_raw_route(app, ctx)

    @app.get("/api/status")
    def api_status(request: Request):
        """Machine-readable status: the same snapshot the pages render."""
        if not _authorised(ctx, request):
            return PlainTextResponse("token required", status_code=403)
        return {"status": ctx.bus.snapshot(), "profiles": _profile_rows(ctx)}

    @app.get("/api/ping")
    def api_ping(request: Request):
        """
        The same command the "Ping the render loop" button posts, exposed for scripts and
        the acceptance runs: it proves the panel->loop direction on the running app.
        Non-mutating, and gated exactly like the page.
        """
        if not _authorised(ctx, request):
            return PlainTextResponse("token required", status_code=403)
        ctx.bus.post({"cmd": "ping"})
        return {"queued": True, "pending": ctx.bus.pending()}

    @app.post("/api/apply")
    async def api_apply(request: Request):
        """
        Re-read a profile from disk and tell the running app to use it — the same thing the
        "Save & Apply" button does, minus the write.

        Useful on its own (after a hand edit, a git pull, or a scripted change) and it is how the
        apply path is exercised end to end without a browser. It cannot change a config: it only
        reads what is already on disk. Gated exactly like the pages.
        """
        if not _authorised(ctx, request):
            return PlainTextResponse("token required", status_code=403)

        body = {}
        raw = await request.body()
        if raw:
            try:
                body = json.loads(raw)
            except ValueError:
                return JSONResponse({"ok": False, "reason": "body must be JSON"}, status_code=400)
            if not isinstance(body, dict):
                return JSONResponse({"ok": False, "reason": "body must be a JSON object"},
                                    status_code=400)

        active_path, _ = profiles_mod.resolve_active_profile(ctx.base_dir, ctx.config_override)
        path = active_path
        rel = str(body.get("profile") or "").strip()
        if rel:
            infos = profiles_mod.discover_profiles(ctx.base_dir, active_path)
            match = next((p for p in infos if p.rel == rel or p.name == rel), None)
            if match is None:
                return JSONResponse(
                    {"ok": False, "reason": f"unknown profile {rel!r}",
                     "profiles": [p.rel for p in infos]}, status_code=404)
            path = match.path
        if not os.path.exists(path):
            return JSONResponse({"ok": False, "reason": f"no such profile file: {path}"},
                                status_code=404)

        refresh = bool(body.get("refresh", True))
        payload = _apply_payload(ctx, path, refresh=refresh)
        ctx.bus.post(payload)
        return {
            "ok": True, "queued": True, "pending": ctx.bus.pending(),
            "profile": os.path.relpath(path, ctx.base_dir),
            "config_sha256": payload["config_sha256"],
            "enabled_modes": payload["enabled"],
            "refresh": refresh,
        }

    @app.post("/api/refresh")
    async def api_refresh(request: Request):
        """Ask the running app to rebuild the mode on screen from the config it already holds."""
        if not _authorised(ctx, request):
            return PlainTextResponse("token required", status_code=403)
        ctx.bus.post({"cmd": "refresh_mode"})
        return {"ok": True, "queued": True, "pending": ctx.bus.pending()}

    @app.post("/api/step")
    async def api_step(request: Request):
        """
        Step the rotation one mode forward ({"delta": 1}, the default) or back ({"delta": -1}).

        The same thing the Next/Prev buttons post, for scripts and the acceptance runs. A step that
        lands mid-fade is QUEUED by the render loop rather than dropped — which is why this answers
        200 even when a transition is in flight: `mode_index` in /api/status is what actually moved.
        Refused by the loop (and reported in `last_step`) when the app was started with `--play N`.
        """
        if not _authorised(ctx, request):
            return PlainTextResponse("token required", status_code=403)
        body = {}
        raw = await request.body()
        if raw:
            try:
                body = json.loads(raw)
            except ValueError:
                return JSONResponse({"ok": False, "reason": "body must be JSON"}, status_code=400)
            if not isinstance(body, dict):
                return JSONResponse({"ok": False, "reason": "body must be a JSON object"},
                                    status_code=400)
        try:
            delta = 1 if int(body.get("delta", 1)) > 0 else -1
        except (TypeError, ValueError):
            return JSONResponse({"ok": False, "reason": "delta must be 1 (next) or -1 (prev)"},
                                status_code=400)

        ctx.bus.post({"cmd": "step_mode", "delta": delta})
        snap = ctx.bus.snapshot()
        if snap.get("single_mode"):
            return JSONResponse(
                {"ok": False, "queued": False,
                 "reason": "this app was started with --play (single mode): there is no rotation to "
                           "step through"}, status_code=409)
        # Deliberately no mode_index here: the loop applies the step on its next frame, so anything
        # read now would be the position BEFORE the step and a script would act on a stale number.
        # Poll /api/status for the real position (`mode_index`, and `last_step` to confirm).
        return {"ok": True, "queued": delta}

    @app.post("/api/profile/new")
    async def api_profile_new(request: Request):
        """
        Create a new profile containing every mode the registry knows.

        Body: {"name": "modes_config_livingroom", "inherit": true, "switch": false}. `inherit`
        copies the tuned values from the profile that is currently active, so a new orientation
        starts from settings already adjusted. The response is the report, not just a boolean: which
        modes came from where, which values are still empty, and which types could not be created.

        Refused (409) for a name that is not a safe file name or a file that already exists — a
        create never overwrites, because there is no backup to fall back on for a file you meant to
        keep. Nothing is written on refusal.
        """
        if not _authorised(ctx, request):
            return PlainTextResponse("token required", status_code=403)
        body = {}
        raw = await request.body()
        if raw:
            try:
                body = json.loads(raw)
            except ValueError:
                return JSONResponse({"ok": False, "reason": "body must be JSON"}, status_code=400)
            if not isinstance(body, dict):
                return JSONResponse({"ok": False, "reason": "body must be a JSON object"},
                                    status_code=400)

        inherit_from = None
        if body.get("inherit", True):
            inherit_from, _ = profiles_mod.resolve_active_profile(ctx.base_dir, ctx.config_override)
        result = create_profile(ctx.base_dir, str(body.get("name") or ""),
                                _load_registry(ctx.base_dir), inherit_from=inherit_from,
                                switch=bool(body.get("switch", False)),
                                config_override=ctx.config_override)
        if not result.ok:
            return JSONResponse({"ok": False, "reason": result.reason, "errors": list(result.errors)},
                                status_code=409)
        if result.switched is not None and result.switched.ok:
            ctx.bus.post(_apply_payload(ctx, result.switched.profile_abs, refresh=True))
        return {
            "ok": True, "path": result.rel, "sha256": result.sha256, "modes": result.modes,
            "carried_over": list(result.inherited), "at_registry_defaults": list(result.at_defaults),
            "seed": result.seed,
            "needs_a_value": list(result.placeholders),
            "left_out": [{"type": t, "keys": list(k)} for t, k in result.left_out],
            "switched": bool(result.switched is not None and result.switched.ok),
            "switch_reason": (result.switched.reason if result.switched is not None else ""),
            "warnings": list(result.warnings),
        }

    @app.post("/api/duplicate")
    async def api_duplicate(request: Request):
        """
        Copy a mode into a new slot: {"index": 3, "profile": "configs/..."} — the row button for
        scripts and the acceptance runs.

        `profile` defaults to the active one. The copy keeps every setting including whether it is
        enabled, and is named "<name> copy" when it has a name. When the profile being changed is the
        one on the display, the running app is told to reload it, so the new slot is live at once;
        the response's `applied` says whether that happened.

        Refused (409) for a mode that is not in the profile, and for a profile that does not validate
        afterwards — nothing is written in either case.
        """
        if not _authorised(ctx, request):
            return PlainTextResponse("token required", status_code=403)
        body = {}
        raw = await request.body()
        if raw:
            try:
                body = json.loads(raw)
            except ValueError:
                return JSONResponse({"ok": False, "reason": "body must be JSON"}, status_code=400)
            if not isinstance(body, dict):
                return JSONResponse({"ok": False, "reason": "body must be a JSON object"},
                                    status_code=400)
        try:
            index = int(body.get("index"))
        except (TypeError, ValueError):
            return JSONResponse({"ok": False, "reason": "index must be a mode number"},
                                status_code=400)

        active_path, _ = profiles_mod.resolve_active_profile(ctx.base_dir, ctx.config_override)
        wanted = body.get("profile")
        path = active_path if not wanted else (
            os.path.abspath(wanted) if os.path.isabs(str(wanted))
            else os.path.abspath(os.path.join(ctx.base_dir, str(wanted))))
        if not os.path.exists(path):
            return JSONResponse({"ok": False, "reason": f"no such profile: {wanted}"}, status_code=404)

        try:
            result, applied = _duplicate_into(ctx, path, index)
        except EditorRefused as e:
            return JSONResponse({"ok": False, "reason": str(e)}, status_code=409)
        if not result.ok:
            return JSONResponse({"ok": False, "reason": result.reason,
                                 "errors": list(result.errors)}, status_code=409)
        return {
            "ok": True, "slot": result.slot, "label": result.label, "renamed": result.renamed,
            "enabled": result.enabled, "applied": applied,
            "profile": os.path.relpath(path, ctx.base_dir),
        }

    @app.post("/api/layout")
    async def api_layout(request: Request):
        """
        Drive the alignment editor without a browser — the same bus command the page's buttons post,
        so there is one path and not two.

        Body: {"op": "set_rect", "layout": "steampunk1", "index": 3, "rect": [x, y, w, h]},
        {"op": "select", "index": 3} (or null to clear), {"op": "freeze", "on": true}.

        Answers 202 with what was queued: the loop applies it on its next frame and reports the
        outcome in /api/status (`layout_edit`, `layout_report`), which is also where the live rects
        and the selection state are published. 409 when the mode on screen is not a control panel or
        is showing a different layout — refused HERE too rather than queued, so a script gets the
        reason immediately instead of a status line it might not read.
        """
        if not _authorised(ctx, request):
            return PlainTextResponse("token required", status_code=403)
        body = {}
        raw = await request.body()
        if raw:
            try:
                body = json.loads(raw)
            except ValueError:
                return JSONResponse({"ok": False, "reason": "body must be JSON"}, status_code=400)
            if not isinstance(body, dict):
                return JSONResponse({"ok": False, "reason": "body must be a JSON object"},
                                    status_code=400)

        op = body.get("op")
        if op not in ("set_rect", "select", "freeze"):
            return JSONResponse({"ok": False, "reason": "op must be set_rect, select or freeze"},
                                status_code=400)

        snap = ctx.bus.snapshot()
        live = snap.get("layout_report")
        if not isinstance(live, dict):
            return JSONResponse(
                {"ok": False, "reason": "the mode on screen is not a control panel (it publishes no "
                                        "layout), so there is nothing to align"},
                status_code=409)
        wanted = body.get("layout")
        if wanted and _layout_key(wanted) != _layout_key(live.get("layout_file", "")):
            return JSONResponse(
                {"ok": False, "reason": f"the control panel on screen is showing "
                                        f"'{live.get('layout_file')}', not '{wanted}'"},
                status_code=409)

        cmd: dict = {"cmd": "layout_edit", "op": op}
        if wanted:
            cmd["layout"] = wanted
        if op == "set_rect":
            try:
                cmd["index"] = int(body.get("index"))
                rect = [int(v) for v in (body.get("rect") or [])]
            except (TypeError, ValueError):
                return JSONResponse({"ok": False,
                                     "reason": "set_rect needs an integer index and rect [x, y, w, h]"},
                                    status_code=400)
            if len(rect) != 4:
                return JSONResponse({"ok": False, "reason": "rect must be [x, y, w, h]"},
                                    status_code=400)
            cmd["rect"] = rect
        elif op == "select":
            index = body.get("index")
            if index is not None:
                try:
                    index = int(index)
                except (TypeError, ValueError):
                    return JSONResponse({"ok": False, "reason": "index must be a number or null"},
                                        status_code=400)
            cmd["index"] = index
        else:
            cmd["on"] = bool(body.get("on", True))

        ctx.bus.post(cmd)
        return JSONResponse({"ok": True, "queued": cmd,
                             "note": "the loop applies this on its next frame; read /api/status for "
                                     "layout_edit and layout_report"},
                            status_code=202)

    @app.post("/api/profile")
    async def api_profile(request: Request):
        """
        Make a profile the active one: validate it, record it in runtime/active_profile.json, and
        tell the running app to switch over. The same thing the "Switch the display to this
        profile" button does, for scripts and the acceptance runs.

        Refusals are explicit rather than half-done: 404 when there is no such profile, 409 when
        the switch was refused (a broken profile, or an app started with --config, which outranks
        the record at every restart).
        """
        if not _authorised(ctx, request):
            return PlainTextResponse("token required", status_code=403)

        body = {}
        raw = await request.body()
        if raw:
            try:
                body = json.loads(raw)
            except ValueError:
                return JSONResponse({"ok": False, "reason": "body must be JSON"}, status_code=400)
            if not isinstance(body, dict):
                return JSONResponse({"ok": False, "reason": "body must be a JSON object"},
                                    status_code=400)

        rel = str(body.get("profile") or "").strip()
        if not rel:
            return JSONResponse({"ok": False, "reason": "a 'profile' is required"}, status_code=400)

        result = switch_profile(ctx.base_dir, rel, _load_registry(ctx.base_dir),
                               config_override=ctx.config_override)
        if not result.ok:
            status = 404 if "no such profile file" in result.reason else 409
            return JSONResponse({"ok": False, "reason": result.reason,
                                 "errors": list(result.errors)}, status_code=status)

        refresh = bool(body.get("refresh", True))
        payload = _apply_payload(ctx, result.profile_abs, refresh=refresh)
        ctx.bus.post(payload)
        return {
            "ok": True, "profile": result.profile, "runtime_file": result.runtime_file,
            "applied": True, "refresh": refresh,
            "config_sha256": payload["config_sha256"], "enabled_modes": payload["enabled"],
            "warnings": list(result.warnings),
        }

    @app.get("/api/profiles")
    def api_profiles(request: Request):
        """Every profile, which one is active, and why — the machine-readable form of the picker."""
        if not _authorised(ctx, request):
            return PlainTextResponse("token required", status_code=403)
        active_path, source = profiles_mod.resolve_active_profile(ctx.base_dir, ctx.config_override)
        return {"active": os.path.relpath(active_path, ctx.base_dir), "source": source,
                "switchable": not ctx.config_override,
                "recorded": read_active_profile(ctx.base_dir),
                "profiles": _profile_rows(ctx)}

    @ui.page("/")
    def modes_page() -> None:
        if not _authorised(ctx, context.client.request):
            _render_refusal()
            return

        active_path, active_source = profiles_mod.resolve_active_profile(
            ctx.base_dir, ctx.config_override
        )
        # ?profile=<rel> opens the page inspecting a specific profile (bookmarkable, and
        # scriptable for the acceptance checks). Anything unknown falls back to the active one.
        state = {"view": _initial_view(ctx.base_dir, active_path,
                                       requested=_requested_profile(ctx))}

        _chrome("Live tuning for the kiosk display — pick a profile, then a mode's parameters.")
        labels = _status_card(ctx, active_path, active_source)
        _transport_controls(ctx, labels)

        with ui.card().classes("w-full mt-4"):
            ui.label("Profiles").classes("text-base font-semibold")
            ui.label(
                "Mode numbers are slots within a profile, so the same number is a different mode "
                "in another profile. Exactly one profile is active on the display at a time."
            ).classes("text-xs opacity-60")

            select = ui.select(options={}, value=None, label="Profile to inspect") \
                .classes("w-full max-w-2xl").mark("profile-select")
            notice = ui.label().classes("text-sm").mark("profile-notice")
            switch_row = ui.row().classes("w-full gap-2 items-center mt-1")
            rows = ui.column().classes("w-full gap-0 mt-2")

            def active_now() -> tuple:
                """Re-resolve every time: a switch changes the answer, and this page must follow."""
                return profiles_mod.resolve_active_profile(ctx.base_dir, ctx.config_override)

            def render_rows() -> None:
                """Rebuild the mode list for the profile currently selected."""
                current_path, current_source = active_now()
                infos = profiles_mod.discover_profiles(ctx.base_dir, current_path)
                info = next((p for p in infos if p.rel == state["view"]), None)
                is_active = info is not None and info.active
                if is_active:
                    notice.set_text(f"This is the profile on the display now (chosen via "
                                    f"{current_source}).")
                elif ctx.config_override:
                    notice.set_text(
                        f"PREVIEW — this app was started with --config {ctx.config_override}, "
                        f"which pins the profile at every restart, so it cannot be switched here.")
                else:
                    notice.set_text("PREVIEW — not the profile on the display. Switching to it "
                                    "changes what plays, with no restart.")
                _render_mode_rows(rows, info, ctx, state, reload_from_disk)
                _render_switch_button(switch_row, ctx, state, info, is_active, after_switch)

            def reload_from_disk() -> None:
                current_path, _ = active_now()
                infos = profiles_mod.discover_profiles(ctx.base_dir, current_path)
                options = {p.rel: _profile_option_label(p) for p in infos}
                if state["view"] not in options:
                    state["view"] = _initial_view(ctx.base_dir, current_path, infos)
                select.options = options
                select.value = state["view"]
                select.update()
                render_rows()

            def after_switch(result) -> None:
                """A switch happened (or was explained): re-render everything that depends on it."""
                reload_from_disk()
                _refresh_status(ctx, labels)

            def after_create(result) -> None:
                """
                A new profile exists. Show it rather than only saying so: the list is rebuilt with
                the new file selected, so the modes it contains are immediately visible (and, with
                the seed ticked, recognisably the ones from the profile you were looking at).
                """
                state["view"] = result.rel
                reload_from_disk()
                _refresh_status(ctx, labels)

            _render_new_config(ctx, after_create)

            def on_view_change() -> None:
                state["view"] = select.value
                render_rows()

            select.on_value_change(on_view_change)
            reload_from_disk()

            def ping() -> None:
                ctx.bus.post({"cmd": "ping"})
                _refresh_status(ctx, labels)

            with ui.row().classes("gap-2 mt-2"):
                ui.button("Reload from disk", on_click=reload_from_disk).props("flat")
                ui.button("Ping the render loop", on_click=ping).props("outline")

            with ui.expansion("Backups — restore a previous version of the inspected profile") \
                    .classes("w-full mt-3"):
                backup_box = ui.column().classes("w-full gap-1")

                def refresh_backups() -> None:
                    def after_backup(_result) -> None:
                        reload_from_disk()
                        refresh_backups()

                    _render_backups(backup_box, ctx, state, after_backup)

                refresh_backups()
                # the list follows the picker: a different profile has different backups
                select.on_value_change(lambda _e: refresh_backups())

        ui.timer(REFRESH_SECONDS, lambda: _refresh_status(ctx, labels))
        _refresh_status(ctx, labels)
        _footer()

    @ui.page("/raw")
    def raw_page() -> None:
        """
        The whole profile file, as JSON, editable.

        For what the generated form cannot express: copy a mode block, paste three at once, fix a
        nested value by hand. It goes through the SAME editor as everything else — same validation,
        same atomic write, same backup, same conflict refusal — so it is another view of one write
        path, not a second write path.
        """
        if not _authorised(ctx, context.client.request):
            _render_refusal()
            return

        active_path, active_source = profiles_mod.resolve_active_profile(
            ctx.base_dir, ctx.config_override)
        view = _initial_view(ctx.base_dir, active_path, requested=_requested_profile(ctx))
        infos = profiles_mod.discover_profiles(ctx.base_dir, active_path)
        info = next((p for p in infos if p.rel == view), None)

        _chrome(f"Raw JSON — {view}")
        if info is None:
            ui.label(f"Profile not found: {view}").classes("text-sm")
            _footer()
            return

        editor = ProfileEditor(ctx.base_dir, info.path, _load_registry(ctx.base_dir))
        box = {"text": json.dumps(editor.document, indent=2, ensure_ascii=False) + "\n"}

        with ui.card().classes("w-full mt-2 gap-2"):
            ui.label(info.rel).classes("text-base font-semibold")
            ui.label(f"{os.path.relpath(info.path, ctx.base_dir)} — the whole document, including "
                     f"the optional \"profile\" block. Saving validates the entire profile, writes "
                     f"atomically and keeps a backup, exactly like the generated form.") \
                .classes("text-xs opacity-60")
            if not editor.mode_in_file(0) and not editor.modes():
                ui.label("This file has no modes.").classes("text-xs text-orange-300")

            outcome = ui.label().classes("text-xs").mark("raw-outcome")

            area = ui.textarea(value=box["text"]) \
                .props("rows=28 spellcheck=false").classes("w-full font-mono text-xs") \
                .mark("raw-textarea")
            area.on_value_change(lambda e: box.update(text=e.value))

            def say(text: str, kind: str = "info") -> None:
                outcome.set_text(text)
                outcome.classes(replace="text-xs " + {"good": "text-green-400",
                                                     "bad": "text-red-400"}.get(kind, "opacity-70"))

            def parse():
                try:
                    return json.loads(box["text"]), ""
                except ValueError as e:
                    return None, f"not valid JSON: {e}"

            def stage_from_box() -> str:
                doc, err = parse()
                if err:
                    say(err, "bad")
                    return err
                try:
                    editor.stage_document(doc)
                except EditorRefused as e:
                    say(str(e), "bad")
                    return str(e)
                return ""

            def do_validate() -> None:
                if stage_from_box():
                    return
                problems = editor.validate()
                if problems.ok:
                    changed = editor.changed_modes()
                    say(f"Valid. " + (f"Mode(s) whose values differ: {changed}."
                                      if changed else "Nothing differs from the file on disk."),
                        "good")
                else:
                    say("Not valid: " + " | ".join(problems.messages()), "bad")

            def do_save() -> None:
                if stage_from_box():
                    return
                result = editor.save()
                if not result.ok:
                    extra = f" On disk now: {editor.conflict_detail()}" if result.conflict else ""
                    say(f"{result.reason}.{' ' + ' | '.join(result.errors) if result.errors else ''}"
                        f"{extra}", "bad")
                    return
                if not result.wrote_anything:
                    say("Nothing differs — nothing was written.", "info")
                    return
                ctx.bus.post(_apply_payload(ctx, info.path, refresh=True))
                box["text"] = json.dumps(editor.document, indent=2, ensure_ascii=False) + "\n"
                area.value = box["text"]
                area.update()
                say(f"Saved ({result.reason}) and applied to the running app."
                    + (f" Backup: {os.path.basename(result.backup)}" if result.backup else "")
                    + (f" | {' | '.join(result.warnings)}" if result.warnings else ""), "good")

            def do_reload() -> None:
                editor.reload()
                box["text"] = json.dumps(editor.document, indent=2, ensure_ascii=False) + "\n"
                area.value = box["text"]
                area.update()
                say("Re-read from disk.", "info")

            def do_format() -> None:
                doc, err = parse()
                if err:
                    say(err, "bad")
                    return
                box["text"] = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
                area.value = box["text"]
                area.update()
                say("Re-indented (not saved).", "info")

            with ui.row().classes("gap-2"):
                ui.button("Validate", on_click=do_validate).props("outline").mark("raw-validate")
                ui.button("Save & Apply", on_click=do_save).props("color=primary") \
                    .mark("raw-save")
                ui.button("Re-indent", on_click=do_format).props("flat").mark("raw-format")
                ui.button("Reload from disk", on_click=do_reload).props("flat").mark("raw-reload")
            ui.label("Editing here writes the WHOLE document, so it is the tool for restructuring; "
                     "the generated form is the tool for tuning one mode.") \
                .classes("text-xs opacity-50")
        _footer()

    @ui.page("/mode/{number}")
    def mode_page(number: str) -> None:
        """
        The generated parameter form for one mode in one profile: edit, Save & Apply, enable or
        disable the mode, Refresh it, or edit the mode's JSON by hand.

        Fields the panel must not write (secrets, values the local override supplies, values the
        mode computes at runtime) still render read-only, each saying why on the page.
        """
        if not _authorised(ctx, context.client.request):
            _render_refusal()
            return

        active_path, active_source = profiles_mod.resolve_active_profile(
            ctx.base_dir, ctx.config_override
        )
        view = _initial_view(ctx.base_dir, active_path, requested=_requested_profile(ctx))
        profiles = profiles_mod.discover_profiles(ctx.base_dir, active_path)
        info = next((p for p in profiles if p.rel == view), None)

        _chrome(f"Mode {number} — {view}")
        if info is None:
            ui.label(f"Profile not found: {view}").classes("text-sm")
            return
        if not str(number).isdigit():
            ui.label(f"Mode number must be an integer (got {number!r}).").classes("text-sm")
            return

        wanted = int(number)
        modes, _meta = profiles_mod.profile_modes(info.path)
        merged, overridden = profiles_mod.merge_local_override(
            modes, profiles_mod.load_local_overrides(ctx.base_dir)
        )
        entry = next((e for e in profiles_mod.mode_entries(merged, overridden)
                      if e.number == wanted), None)

        if entry is None:
            with ui.card().classes("w-full mt-2"):
                ui.label(f"No mode {wanted} in this profile.").classes("text-base")
                ui.label("Mode numbers are SLOTS within a profile, so that number may exist in "
                         "another profile while meaning something else entirely.") \
                    .classes("text-xs opacity-60")
            _footer()
            return

        registry = _load_registry(ctx.base_dir)
        state = _ModeEditor(ctx, info, entry, registry, overridden)

        _mode_header(ctx, info, entry, active_source)
        _align_link(ctx, info, entry)
        _enable_card(state)
        if state.editor.mode_in_file(entry.number):
            _editable_mode_form(state)
        else:
            ui.label("This mode exists only in modes_config.local.json, so there is nothing in "
                     "this profile to edit — the override supplies every value it has.") \
                .classes("text-sm text-orange-300 mt-3").mark("override-only-note")
            _readonly_mode_form(entry, state.params, state.warnings)
        _footer()


def _requested_profile(ctx: PageContext) -> str:
    """The ?profile= query parameter, if the caller asked for a specific profile."""
    request = context.client.request
    if request is None:
        return ""
    return request.query_params.get("profile", "") or ""


def _initial_view(base_dir: str, active_path: str, infos=None, requested: str = "") -> str:
    infos = infos if infos is not None else profiles_mod.discover_profiles(base_dir, active_path)
    known = {p.rel for p in infos}
    if requested and requested in known:
        return requested
    for p in infos:
        if p.active:
            return p.rel
    return infos[0].rel if infos else ""


# ---------------------------------------------------------------- status card

def _status_card(ctx: PageContext, active_path: str, active_source: str) -> dict:
    """
    Build the live-status card ONCE and return the label elements keyed by name, so the
    timer mutates text in place instead of rebuilding anything.
    """
    labels: dict = {}
    with ui.card().classes("w-full"):
        ui.label("Display status").classes("text-base font-semibold")
        with ui.grid(columns=2).classes("w-full gap-x-6 gap-y-1 text-sm"):
            for key, caption in (("mode", "Live mode"), ("loop", "Render loop"),
                                 ("profile", "Active profile"), ("panel", "Panel"),
                                 ("commands", "Commands"), ("rotation", "Rotation")):
                ui.label(caption).classes("opacity-60")
                labels[key] = ui.label("-").mark(f"status-{key}")
        if not ctx.token_required:
            ui.label(
                f"Panel bound to {ctx.bind} — reachable from this machine only. "
                f"For LAN access, set panel_token in secrets.json and bind 0.0.0.0."
            ).classes("text-xs opacity-50")
    labels["profile"].set_text(
        f"{os.path.relpath(active_path, ctx.base_dir)} (chosen via {active_source})"
    )
    return labels


def _refresh_status(ctx: PageContext, labels: dict) -> None:
    """Poll the bus and mutate the labels in place."""
    snap = ctx.bus.snapshot()
    labels["mode"].set_text(_mode_text(snap))
    labels["loop"].set_text(_loop_text(snap, time.time() - snap.get("started_at", time.time())))
    labels["panel"].set_text(
        f"{snap.get('panel_bind')}:{snap.get('panel_port')} (nicegui {snap.get('nicegui_version')})"
    )
    labels["commands"].set_text(_commands_text(snap))
    labels["rotation"].set_text(_rotation_text(snap))
    # Re-resolved every poll, so a profile switch (from this page or another) shows up here.
    active_path, source = profiles_mod.resolve_active_profile(ctx.base_dir, ctx.config_override)
    labels["profile"].set_text(f"{os.path.relpath(active_path, ctx.base_dir)} (via {source})")
    _refresh_transport(labels, snap)


def _refresh_transport(labels: dict, snap: dict) -> None:
    """
    Update the Next/Prev hint and their enabled state in place (no rebuild: the buttons must not
    move under the cursor mid-click). Guarded so a poll only pushes a change when something
    actually changed.
    """
    hint = labels.get("transport")
    if hint is None:
        return
    text = _transport_text(snap)
    if labels.get("transport_text") != text:
        labels["transport_text"] = text
        hint.set_text(text)

    usable = not snap.get("single_mode") and snap.get("display") != "off"
    state = labels.get("transport_state")
    if state is not None and state.get("enabled") != usable:
        state["enabled"] = usable
        for key in ("transport_prev", "transport_next"):
            if labels.get(key) is not None:
                labels[key].set_enabled(usable)


# ---------------------------------------------------------------- data for pages

def _duplicate_into(ctx: PageContext, profile_path: str, number: int) -> tuple:
    """
    Copy a mode into a new slot, and apply it when that profile is the one on the display.

    Shared by the row button and the endpoint so there is one behaviour, not two. A fresh editor per
    call on purpose: the row shows the FILE, so the copy is made from the file, and there is no
    half-finished form to reconcile. Raises EditorRefused for a refusal that is nobody's error.
    """
    editor = ProfileEditor(ctx.base_dir, profile_path, _load_registry(ctx.base_dir))
    result = editor.duplicate_mode(number)
    applied = False
    if result.ok:
        active_path, _ = profiles_mod.resolve_active_profile(ctx.base_dir, ctx.config_override)
        if os.path.realpath(active_path) == os.path.realpath(profile_path):
            # The slot is in the file now; without this the wall would keep playing the old rotation
            # until something else triggered an apply.
            ctx.bus.post(_apply_payload(ctx, profile_path, refresh=False))
            applied = True
    return result, applied


def _render_mode_rows(container, info, ctx: PageContext, state: dict, after_change) -> None:
    """Rebuild the mode list for the profile being inspected."""
    container.clear()
    with container:
        # The outcome of a duplicate lives in `state`, not in this container: rebuilding the list
        # clears everything in here, including the message the user has not read yet.
        prior = state.get("duplicate_outcome")
        if prior:
            text, colour = prior
            ui.label(text).classes(f"text-xs whitespace-pre-line {colour}").mark("duplicate-outcome")

        if info is None:
            ui.label("Profile not found.").classes("text-sm")
            return
        if info.error:
            ui.label(f"{info.rel}: {info.error}").classes("text-sm")

        local_modes = profiles_mod.load_local_overrides(ctx.base_dir)
        modes, _meta = profiles_mod.profile_modes(info.path)
        merged, overridden = profiles_mod.merge_local_override(modes, local_modes)
        entries = profiles_mod.mode_entries(merged, overridden)

        if not entries:
            ui.label("No modes in this profile.").classes("text-sm")
            return

        def duplicator(number: int):
            """One handler per row, closing over that row's number (not over the loop variable)."""
            def do_duplicate() -> None:
                """
                Copy this mode into a new slot. One click, no confirmation: it is additive and
                reversible — the copy is an ordinary mode you can edit, disable or remove from its
                own params page — and the point of it is speed while tuning.
                """
                try:
                    result, applied = _duplicate_into(ctx, info.path, number)
                except EditorRefused as e:
                    state["duplicate_outcome"] = (f"Not copied: {e}", "text-red-400")
                    after_change()
                    return
                if not result.ok:
                    state["duplicate_outcome"] = (f"Not copied: {result.reason}", "text-red-400")
                    after_change()
                    return
                note = f"Copied mode {number} to mode {result.slot}"
                if result.renamed:
                    note += f", named '{result.label}' so the two are distinguishable in this list"
                note += ". Edit the copy on its own params page; the original is untouched."
                if applied:
                    note += (" It is in the rotation from now on — flip its switch in the list below "
                             "if you would rather tune it first." if result.enabled else
                             " It is disabled, so it stays out of the rotation until you enable it.")
                state["duplicate_outcome"] = (note, "text-green-400")
                after_change()
            return do_duplicate

        ui.label(f"{len(entries)} mode(s)").classes("text-xs opacity-60")
        for e in entries:
            with ui.row().classes("w-full items-center gap-3 py-1 border-b border-white/5"):
                ui.label(str(e.number)).classes("w-8 text-right font-mono text-xs opacity-70") \
                    .mark(f"mode-number-{e.number}")
                ui.label(e.label or "—").classes("w-44 truncate text-sm")
                ui.label(e.type).classes("w-56 truncate text-xs opacity-70")
                if not e.enabled:
                    ui.badge("disabled").props("outline color=orange").classes("text-xs") \
                        .mark(f"mode-disabled-{e.number}")
                if e.override_keys:
                    ui.badge(f"local override: {', '.join(e.override_keys)}") \
                        .props("outline color=orange").classes("text-xs")
                else:
                    ui.label(f"{len(e.params)} params").classes("text-xs opacity-50")
                ui.link("params →", f"/mode/{e.number}?profile={info.rel}") \
                    .classes("text-xs ml-auto").mark(f"open-mode-{e.number}")
                ui.button("duplicate", on_click=duplicator(e.number)) \
                    .props("flat dense size=sm no-caps").classes("text-xs") \
                    .mark(f"duplicate-mode-{e.number}")


def _layout_key(name) -> str:
    """Compare a layout the way a person would: 'steampunk1' == 'assets/.../steampunk1.json'."""
    base = os.path.basename(str(name or "")).strip()
    return (base[:-5] if base.lower().endswith(".json") else base).lower()


# ---------------------------------------------------------------- the alignment page (design Phase 6B)
#
# The page holds the DOCUMENT and edits it; the wall follows through the bus; Save writes the file.
# That split is the whole design: nudging is dozens of presses per overlay, so a press must not be a
# write — but a structural change (add/remove) is one deliberate act, and it writes immediately, the
# same way the duplicate button and the enable switch do, because a mode that does not exist in the
# file cannot be tuned.


def _open_layout(name: str):
    """A LayoutEditor for a layout name or path, or None when it cannot be opened."""
    from controlpanel.layout import LayoutError
    try:
        return LayoutEditor(name)
    except LayoutError:
        return None


def _artwork_in_use(ctx: PageContext, rel: str, number, editor) -> tuple:
    """
    (artwork path, canvas [w, h], where it came from) — what the boxes must be drawn over.

    The MODE owns the picture and the layout file's background_image is only its default, so reading
    the layout document alone can draw the boxes over a picture the wall is not using — which makes
    every position on this page a lie. Order of authority:

      1. the LIVE mode, when the display is showing this layout: it reports the artwork it is
         actually drawing and the canvas it is working in, and nothing beats that;
      2. this mode's background_image parameter — resolved by asking the package to load the layout
         WITH the override, so the artwork and the canvas (which the artwork decides when the layout
         declares none) both come from the one authority instead of a rule re-implemented here;
      3. the layout file's own field, for a panel being prepared but not shown.
    """
    live = ctx.bus.snapshot().get("layout_report")
    if isinstance(live, dict) and _layout_key(live.get("layout_file")) == _layout_key(editor.name):
        artwork = str(live.get("background_image") or "")
        canvas = [int(v) for v in (live.get("canvas") or [])]
        if artwork and len(canvas) == 2:
            return artwork, canvas, "the live display"

    document = load_json(os.path.join(ctx.base_dir, rel), {})
    modes = document.get("modes") if isinstance(document, dict) else None
    entry = (modes or {}).get(str(number)) if isinstance(modes, dict) else None
    override = str((entry or {}).get("background_image") or "").strip() \
        if isinstance(entry, dict) else ""
    if override:
        from controlpanel.layout import LayoutError, layout_from_data
        try:
            loaded = layout_from_data(json.loads(json.dumps(editor.document)), name=editor.name,
                                      background_override=override)
        except LayoutError as e:
            return resolve_background(override), list(editor.canvas()), \
                   f"this mode's background_image ({e})"
        return str(loaded.background_image or ""), [int(v) for v in loaded.design_resolution], \
               "this mode's background_image parameter"

    own = str(editor.document.get("background_image") or "").strip()
    return (resolve_background(own) if own else ""), list(editor.canvas()), "the layout file"


def _first_controlpanel_slot(modes: dict) -> int | None:
    for slot in sorted(modes, key=lambda k: int(k) if str(k).isdigit() else 10 ** 9):
        entry = modes.get(slot)
        if isinstance(entry, dict) and normalize_type(entry.get("type", "")) == "controlpanel":
            return int(slot)
    return None


def _layout_page(ctx: PageContext, rel: str, number: int | None) -> None:
    """The /layout page: pick the overlay, nudge it, see it on the wall, save the file."""
    from controlpanel.layout import LayoutError        # on demand: it imports pygame

    path = os.path.join(ctx.base_dir, rel)
    document = load_json(path, {})
    modes = document.get("modes") if isinstance(document, dict) else None
    modes = modes if isinstance(modes, dict) else {}

    _chrome("Align a control panel's overlays to its artwork")

    if number is None:
        number = _first_controlpanel_slot(modes)
    entry = modes.get(str(number)) if number is not None else None
    if not isinstance(entry, dict):
        ui.label(f"No control panel mode in {rel} — mode {number} is not there."
                 ).classes("text-sm text-orange-300")
        ui.link("Back to the profile", f"/?profile={rel}").classes("text-xs")
        _footer()
        return
    if normalize_type(entry.get("type", "")) != "controlpanel":
        ui.label(f"Mode {number} in {rel} is {entry.get('type')!r}, not a controlpanel. Pick a "
                 f"control panel mode on the profile page, then open its params.") \
            .classes("text-sm text-orange-300")
        ui.link("Back to the profile", f"/?profile={rel}").classes("text-xs")
        _footer()
        return

    layout_name = str(entry.get("layout_file") or "").strip()
    try:
        editor = LayoutEditor(layout_name)
    except LayoutError as e:
        ui.label(f"The layout this mode points at could not be opened: {e}") \
            .classes("text-sm text-red-400")
        ui.link("Back to the profile", f"/?profile={rel}").classes("text-xs")
        _footer()
        return

    state: dict = {"selected": None, "outcome": None, "step": 1, "pending_remove": None}
    background, canvas, artwork_source = _artwork_in_use(ctx, rel, number, editor)
    cw, ch = canvas[0], canvas[1]

    def live_report() -> dict:
        report = ctx.bus.snapshot().get("layout_report")
        return report if isinstance(report, dict) else {}

    def on_screen() -> bool:
        """Is the control panel ON THE WALL showing this layout? Nudges are refused otherwise."""
        return _layout_key(live_report().get("layout_file")) == _layout_key(layout_name)

    def selected() -> int | None:
        return state["selected"]

    def post_layout(op: str, **fields) -> None:
        command = {"cmd": "layout_edit", "op": op, "layout": layout_name}
        command.update(fields)
        ctx.bus.post(command)

    def say(text: str, good: bool = True) -> None:
        state["outcome"] = (text, "text-green-400" if good else "text-red-400")

    with ui.card().classes("w-full mt-2 gap-1"):
        with ui.row().classes("items-center gap-2 w-full"):
            ui.label(f"{editor.name}").classes("text-base font-semibold")
            ui.badge(f"{editor.mode}").props("outline").classes("text-xs")
            ui.label(f"{cw}x{ch} · {len(editor.controls())} overlays").classes("text-xs opacity-60")
            ui.label(f"artwork: {os.path.basename(str(background)) or '(none)'} — from "
                     f"{artwork_source}").classes("text-xs opacity-60") \
                .mark("layout-artwork-source")
            ui.link("raw JSON →", f"/layout/raw?layout={layout_name}&profile={rel}"
                    + (f"&mode={number}" if number is not None else "")) \
                .classes("text-xs ml-auto").mark("layout-raw-link")
            ui.link("mode params →", f"/mode/{number}?profile={rel}").classes("text-xs")
        live_line = ui.label().classes("text-xs").mark("layout-live")
        ui.label("The page edits the document; the wall follows live; Save writes the file. "
                 "Nudges are refused unless the display is showing THIS layout, so an edit can never "
                 "move something you cannot see.").classes("text-xs opacity-50")

    if editor.mode != "freeform":
        with ui.card().classes("w-full mt-2"):
            ui.label("This is a grid layout.").classes("text-sm text-orange-300")
            ui.label("Its controls sit in whole 128px cells inside panels and are validated to fit "
                     "there, so there is no pixel position to align. The alignment editor works on "
                     "freeform layouts — the ones that put overlays over a background PNG.") \
                .classes("text-xs opacity-70")
            ui.link("Back to the profile", f"?profile={rel}").classes("text-xs")

    outcome = ui.label().classes("text-xs whitespace-pre-line").mark("layout-outcome")
    preview_box = ui.column().classes("w-full")
    list_box = ui.column().classes("w-full")
    pad_box = ui.column().classes("w-full")

    def render_all() -> None:
        if state["outcome"]:
            text, colour = state["outcome"]
            outcome.classes(replace=f"text-xs whitespace-pre-line {colour}")
            outcome.set_text(text)
        report = live_report()
        if report:
            showing = _layout_key(report.get("layout_file")) == _layout_key(layout_name)
            live_line.set_text(
                f"on the wall: {report.get('layout_file')}"
                + ("  (this layout — nudges apply live)" if showing else
                   "  (a DIFFERENT layout: nudges will be refused, and Save only changes the file)"))
            live_line.classes(replace="text-xs " + ("text-green-400" if showing
                                                   else "text-orange-300"))
        else:
            live_line.set_text("the mode on screen is not a control panel, so nothing can be "
                               "nudged live — you can still edit and Save the file")
            live_line.classes(replace="text-xs opacity-60")
        _draw_preview()
        _draw_rows()
        _draw_pad()

    # ------------------------------------------------------------------ preview

    def _draw_preview() -> None:
        preview_box.clear()
        with preview_box:
            with ui.card().classes("w-full mt-2 gap-1"):
                ui.label("The artwork").classes("text-base font-semibold")
                if not background:
                    ui.label("This layout has no background_image, so there is nothing to align to "
                             "(a freeform layout normally points at a PNG in "
                             "assets/control_panel/backgrounds/).").classes("text-xs opacity-70")
                else:
                    ui.label("Boxes are geometry from the file, not a render — the wall is the real "
                             "render. Click one to select that overlay.").classes("text-xs opacity-50")
                with ui.element("div").classes("relative w-full").style(
                        f"max-width: 820px; aspect-ratio: {cw} / {ch};"):
                    if background:
                        ui.image(f"/api/asset/background?layout={editor.name}&profile={rel}"
                                 + (f"&mode={number}" if number is not None else "")) \
                            .classes("absolute inset-0 w-full h-full").mark("layout-artwork")
                    for i, _control in enumerate(editor.controls()):
                        rect = editor.rect_of(i) or (0, 0, 0, 0)
                        chosen = i == selected()
                        box = ui.element("div").classes("absolute cursor-pointer").style(
                            "border:2px solid %s; background:%s; left:%.4f%%; top:%.4f%%; "
                            "width:%.4f%%; height:%.4f%%;" % (
                                "#ffd23c" if chosen else "#7dd3fc",
                                "rgba(255,210,60,0.18)" if chosen else "rgba(125,211,252,0.10)",
                                rect[0] / cw * 100, rect[1] / ch * 100,
                                rect[2] / cw * 100, rect[3] / ch * 100))
                        box.mark(f"layout-box-{i}")
                        box.on("click", lambda _=None, index=i: choose(index))

    # ------------------------------------------------------------------ the list

    def _draw_rows() -> None:
        list_box.clear()
        with list_box:
            with ui.card().classes("w-full mt-2 gap-1"):
                ui.label(f"Overlays ({len(editor.controls())})").classes("text-base font-semibold")
                for i, control in enumerate(editor.controls()):
                    rect = editor.rect_of(i) or (0, 0, 0, 0)
                    with ui.row().classes("w-full items-center gap-2 py-1 "
                                          "border-b border-white/5"):
                        ui.label(str(i)).classes("w-8 text-right font-mono text-xs opacity-70")
                        ui.label(str(control.get("type", "?"))).classes("w-32 truncate text-sm")
                        ui.label(str(control.get("sprite", ""))).classes("w-44 truncate text-xs opacity-70")
                        ui.label(f"{rect[0]},{rect[1]}  {rect[2]}x{rect[3]}") \
                            .classes("font-mono text-xs opacity-70 w-40")
                        if i == selected():
                            ui.badge("selected").props("color=amber").classes("text-xs")
                        ui.button("select", on_click=lambda _=None, index=i: choose(index)) \
                            .props("flat dense size=sm no-caps").classes("text-xs") \
                            .mark(f"layout-select-{i}")
                        pending = state["pending_remove"] == i
                        ui.button("confirm remove" if pending else "remove",
                                  on_click=lambda _=None, index=i: ask_remove(index)) \
                            .props("flat dense size=sm no-caps" +
                                   (" color=negative" if pending else "")).classes("text-xs") \
                            .mark(f"layout-remove-{i}")
                with ui.row().classes("items-center gap-2 mt-1"):
                    ui.button("Add overlay…", on_click=add_dialog.open).props("outline dense") \
                        .mark("layout-add")
                    ui.button("Save", on_click=do_save).props("color=primary dense") \
                        .mark("layout-save")
                    ui.button("Reload from disk", on_click=do_reload).props("flat dense") \
                        .mark("layout-reload")
                    ui.label("unsaved changes" if editor.is_dirty() else "no changes") \
                        .classes("text-xs opacity-60").mark("layout-dirty")

    # ------------------------------------------------------------------ the nudge pad

    def _draw_pad() -> None:
        pad_box.clear()
        with pad_box:
            with ui.card().classes("w-full mt-2 gap-2"):
                ui.label("Position").classes("text-base font-semibold")
                if selected() is None:
                    ui.label("Select an overlay above (or click a box on the artwork) to move it.") \
                        .classes("text-xs opacity-60")
                    return
                index = selected()
                rect = editor.rect_of(index) or (0, 0, 0, 0)
                ui.label(f"overlay #{index} — {editor.controls()[index].get('type')} "
                         f"{editor.controls()[index].get('sprite')}").classes("text-xs opacity-70")

                with ui.row().classes("items-center gap-1"):
                    ui.label("step").classes("text-xs opacity-60")
                    for step in (1, 5, 10):
                        ui.button(f"{step}px", on_click=lambda _=None, s=step: set_step(s)) \
                            .props("flat dense no-caps" +
                                   (" color=primary" if state["step"] == step else "")) \
                            .classes("text-xs").mark(f"layout-step-{step}")

                with ui.row().classes("items-center gap-1"):
                    ui.button("←", on_click=lambda _=None: nudge(-state["step"], 0)) \
                        .props("dense").mark("layout-left")
                    ui.button("→", on_click=lambda _=None: nudge(state["step"], 0)) \
                        .props("dense").mark("layout-right")
                    ui.button("↑", on_click=lambda _=None: nudge(0, -state["step"])) \
                        .props("dense").mark("layout-up")
                    ui.button("↓", on_click=lambda _=None: nudge(0, state["step"])) \
                        .props("dense").mark("layout-down")
                    ui.button("W+", on_click=lambda _=None: resize(state["step"], 0)).props("dense") \
                        .mark("layout-w-plus")
                    ui.button("W−", on_click=lambda _=None: resize(-state["step"], 0)).props("dense") \
                        .mark("layout-w-minus")
                    ui.button("H+", on_click=lambda _=None: resize(0, state["step"])).props("dense") \
                        .mark("layout-h-plus")
                    ui.button("H−", on_click=lambda _=None: resize(0, -state["step"])).props("dense") \
                        .mark("layout-h-minus")

                with ui.row().classes("items-center gap-2"):
                    fields = {}
                    for name, value in (("x", rect[0]), ("y", rect[1]), ("w", rect[2]),
                                        ("h", rect[3])):
                        fields[name] = ui.number(name, value=value, format="%d").classes("w-24") \
                            .mark(f"layout-field-{name}")

                    def apply_fields() -> None:
                        try:
                            rect_now = [int(fields["x"].value), int(fields["y"].value),
                                        int(fields["w"].value), int(fields["h"].value)]
                        except (TypeError, ValueError):
                            say("x, y, w and h must be whole numbers", good=False)
                            render_all()
                            return
                        move_to(rect_now)

                    ui.button("Apply", on_click=apply_fields).props("outline dense") \
                        .mark("layout-apply")
                    ui.button("centre", on_click=lambda _=None: centre()).props("flat dense") \
                        .mark("layout-centre")

                with ui.row().classes("items-center gap-2 mt-1"):
                    ui.switch("Freeze the overlays (hold still while you align)",
                              value=bool(live_report().get("frozen")),
                              on_change=lambda e: post_layout("freeze", on=bool(e.value))) \
                        .mark("layout-freeze")
                    ui.label("freezing stops update() for every overlay — a zero timestep does not "
                             "hold several of them still").classes("text-xs opacity-50")

    # ------------------------------------------------------------------ actions

    def choose(index: int) -> None:
        state["selected"] = index
        post_layout("select", index=index)
        render_all()

    def set_step(step: int) -> None:
        state["step"] = step
        render_all()

    def move_to(rect) -> None:
        index = selected()
        report = editor.set_rect(index, rect)
        if not report["ok"]:
            say(report["reason"], good=False)
        else:
            if on_screen():
                post_layout("set_rect", index=index, rect=report["rect"])
                say(f"overlay #{index} at {report['rect']} — live on the wall, Save to keep it")
            else:
                say(f"overlay #{index} moved to {report['rect']} in the document. The display is not "
                    f"showing this layout, so nothing was applied to the wall — Save writes the file.")
        render_all()

    def nudge(dx: int, dy: int) -> None:
        rect = editor.rect_of(selected())
        if rect is None:
            return
        move_to([rect[0] + dx, rect[1] + dy, rect[2], rect[3]])

    def resize(dw: int, dh: int) -> None:
        rect = editor.rect_of(selected())
        if rect is None:
            return
        move_to([rect[0], rect[1], max(1, rect[2] + dw), max(1, rect[3] + dh)])

    def centre() -> None:
        report = editor.centre_rect(selected())
        if not report["ok"]:
            say(report["reason"], good=False)
            render_all()
            return
        move_to(report["rect"])

    def ask_remove(index: int) -> None:
        if state["pending_remove"] != index:
            state["pending_remove"] = index
            say(f"press confirm remove to delete overlay #{index} (from the file, and from the wall)",
                good=False)
            render_all()
            return
        state["pending_remove"] = None
        report = editor.remove_control(index)
        if not report["ok"]:
            say(report["reason"], good=False)
            render_all()
            return
        saved = editor.save()
        if not saved.ok:
            say(f"removed from the document, but not saved: {saved.reason}", good=False)
        else:
            if state["selected"] == index:
                state["selected"] = None
                post_layout("select", index=None)
            if on_screen():
                ctx.bus.post({"cmd": "refresh_mode"})
                say(f"removed overlay #{index} and saved. The wall is rebuilding the mode so the "
                    f"removal shows there too.")
            else:
                say(f"removed overlay #{index} and saved {saved.rel}.")
        render_all()

    def do_save() -> None:
        result = editor.save()
        if not result.ok:
            say(result.reason, good=False)
        else:
            backup = f" (backup: {os.path.basename(result.backup)})" if result.backup else ""
            say(f"saved {result.rel}{backup}")
        render_all()

    def do_reload() -> None:
        try:
            editor.reload()
        except LayoutError as e:
            say(f"could not reload: {e}", good=False)
        else:
            state["selected"] = None
            state["pending_remove"] = None
            post_layout("select", index=None)
            say("reloaded from disk — unsaved changes dropped")
        render_all()

    # ------------------------------------------------------------------ add / create dialogs

    add_dialog = ui.dialog()
    with add_dialog, ui.card().classes("w-full max-w-2xl gap-2"):
        ui.label("Add an overlay").classes("text-base font-semibold")
        ui.label("It is appended at the centre of the artwork and written to the file straight away, "
                 "so the mode can be rebuilt with it — a control that exists only on screen could "
                 "not be tuned.").classes("text-xs opacity-60")
        try:
            from controlpanel.controls import CONTROL_CLASSES as _CATALOGUE
            from controlpanel.layout import load_sprite_defs as _sprite_defs
            type_options = sorted(set(_CATALOGUE) | {"plate"})
            sprite_options = sorted(_sprite_defs()["sprites"])
        except Exception as e:                                    # pragma: no cover
            type_options, sprite_options = [], []
            ui.label(f"could not read the control catalogue: {e}").classes("text-xs text-red-400")
        type_select = ui.select(type_options, value=(type_options[0] if type_options else None),
                                label="type").classes("w-64").mark("layout-add-type")
        sprite_select = ui.select(sprite_options,
                                  value=("GAUGE_ROUND_SMALL_1" if "GAUGE_ROUND_SMALL_1"
                                         in sprite_options else None),
                                  label="sprite", with_input=True).classes("w-64") \
            .mark("layout-add-sprite")
        add_outcome = ui.label().classes("text-xs").mark("layout-add-outcome")

        def do_add() -> None:
            report = editor.add_control({"type": type_select.value, "sprite": sprite_select.value,
                                         "size": [160, 160]})
            if not report["ok"]:
                add_outcome.classes(replace="text-xs text-red-400")
                add_outcome.set_text(report["reason"])
                return
            saved = editor.save()
            add_outcome.classes(replace="text-xs text-green-400")
            if not saved.ok:
                add_outcome.classes(replace="text-xs text-red-400")
                add_outcome.set_text(f"added to the document, but not saved: {saved.reason}")
                return
            add_outcome.set_text(f"added overlay #{report['index']}"
                                 + (" and saved" if saved.ok else ""))
            state["selected"] = report["index"]
            if on_screen():
                ctx.bus.post({"cmd": "refresh_mode"})
            render_all()

        with ui.row().classes("items-center gap-2"):
            ui.button("Add", on_click=do_add).props("color=primary").mark("layout-add-confirm")
            ui.button("Close", on_click=add_dialog.close).props("flat")

    create_dialog = ui.dialog()
    with create_dialog, ui.card().classes("w-full max-w-2xl gap-2"):
        ui.label("New freeform layout over a PNG").classes("text-base font-semibold")
        ui.label("Name the artwork and the layout: a bare file name is looked up under "
                 "assets/control_panel/backgrounds/, a path (like /mnt/ssd/projects/images/panels/"
                 "panel.png) is used as given. Seeding copies the controls from an existing layout "
                 "so you start with the right set of overlays and only have to place them.") \
            .classes("text-xs opacity-60")
        name_input = ui.input("Layout name", placeholder="livingroom_panel").classes("w-full") \
            .mark("layout-create-name")
        _bg_names = list_backgrounds()
        background_select = ui.select(list(_bg_names), value=(_bg_names[0] if _bg_names else ""),
                                      with_input=True, new_value_mode="add-unique",
                                      label="artwork (name or path)").classes("w-96") \
            .mark("layout-create-background")
        seed_select = ui.select(["none"] + list_layouts(), value="none", label="seed from") \
            .classes("w-72").mark("layout-create-seed")
        create_outcome = ui.label().classes("text-xs whitespace-pre-line") \
            .mark("layout-create-outcome")

        def do_create() -> None:
            result = create_freeform(name_input.value or "", background_select.value or "",
                                     None if seed_select.value in (None, "none")
                                     else seed_select.value)
            if not result["ok"]:
                create_outcome.classes(replace="text-xs whitespace-pre-line text-red-400")
                create_outcome.set_text(result["reason"])
                return
            create_outcome.classes(replace="text-xs whitespace-pre-line text-green-400")
            create_outcome.set_text(
                f"created {result['name']}.json over {result['background']} "
                f"({result['canvas'][0]}x{result['canvas'][1]}, {result['controls']} overlays"
                f"{result['seeded']}).\nPoint the mode at it: on the mode's params page set "
                f"layout_file to '{result['name']}'.")
            texture = "text-xs whitespace-pre-line text-green-400"

        with ui.row().classes("items-center gap-2"):
            ui.button("Create", on_click=do_create).props("color=primary") \
                .mark("layout-create-confirm")
            ui.button("Close", on_click=create_dialog.close).props("flat")

    with ui.row().classes("items-center gap-2 mt-2"):
        ui.button("New freeform layout over a PNG…", on_click=create_dialog.open) \
            .props("outline dense").mark("layout-create")
        ui.link("Back to the profile", f"/?profile={rel}").classes("text-xs")
    _footer()

    render_all()


def _register_layout_raw_route(app, ctx: PageContext) -> None:
    # A NiceGUI page, not a FastAPI route: a FastAPI route returns a response and has no slot to
    # build UI in (see _register_layout_route).
    @ui.page("/layout/raw")
    def layout_raw_page(layout: str | None = None, profile: str | None = None,
                        mode: int | None = None) -> None:
        """
        One layout file as JSON, editable.

        For what the boxes on the alignment page cannot express: paste a whole panel in, fix an id by
        hand, move three overlays one line each. It goes through the SAME writer as that page
        (core.layout_edit.LayoutEditor), so it is another view of one write path rather than a second
        one — validated by the package's own loader, written atomically with a timestamped backup, and
        refused if the file changed underneath.
        """
        if not _authorised(ctx, context.client.request):
            _render_refusal()
            return
        from controlpanel.layout import LayoutError            # on demand: it imports pygame

        rel = (profile or "").strip()
        back = "/layout?" + (f"profile={rel}&" if rel else "") + \
               (f"mode={mode}" if mode is not None else "")
        name = (layout or "").strip()
        _chrome(f"Raw JSON — layout {name or '(none given)'}")
        if not name:
            ui.label("No layout given. Open this page from a control panel's alignment page.") \
                .classes("text-sm")
            _footer()
            return

        try:
            editor = LayoutEditor(name)
            cw, ch = editor.canvas()
        except LayoutError as e:
            ui.label(f"Could not open layout {name!r}: {e}").classes("text-sm text-red-400")
            ui.link("Back to the alignment page", back).classes("text-xs")
            _footer()
            return

        shown = str(getattr(editor, "path", name))
        try:
            shown = os.path.relpath(shown, ctx.base_dir)
        except ValueError:
            pass

        with ui.card().classes("w-full mt-2 gap-1"):
            with ui.row().classes("items-center gap-2 w-full"):
                ui.label(editor.name).classes("text-base font-semibold")
                ui.badge(str(editor.mode)).props("outline").classes("text-xs")
                ui.label(f"{cw}x{ch} · {len(editor.controls())} overlays") \
                    .classes("text-xs opacity-60")
                ui.link("back to aligning →", back).classes("text-xs ml-auto")
            ui.label(f"{shown} — the whole layout document. Saving validates it with the package's "
                     f"own loader, writes atomically and keeps a backup; nothing is written unless "
                     f"every check passes.").classes("text-xs opacity-60")

        note = ui.label().classes("text-sm").mark("raw-layout-note")

        def say(text: str, kind: str = "info") -> None:
            colour = {"good": "text-green-400", "bad": "text-red-400"}.get(kind, "opacity-60")
            note.classes(replace=f"text-sm {colour}")
            note.set_text(text)

        area = ui.textarea(value=json.dumps(editor.document, indent=2, ensure_ascii=False) + "\n") \
            .props("rows=24").classes("w-full font-mono text-xs").mark("raw-layout-json")

        def parse() -> tuple:
            try:
                doc = json.loads(area.value)
            except json.JSONDecodeError as e:
                return None, f"not valid JSON: {e}"
            if not isinstance(doc, dict):
                return None, f"a layout must be a JSON object, not {type(doc).__name__}"
            return doc, ""

        def validate_box() -> tuple:
            """Try the box's document WITHOUT letting a look change what Save would write."""
            doc, err = parse()
            if err:
                return None, err, ()
            keep = editor.document
            editor.document = doc
            errors, warnings = editor.validate()
            editor.document = keep
            return doc, "", (errors, warnings)

        def do_validate() -> None:
            doc, err, checked = validate_box()
            if err:
                say(err, "bad")
                return
            errors, warnings = checked
            if errors:
                say("Not valid: " + " | ".join(errors), "bad")
                return
            say("Valid — the loader accepts it." + (f" Note: {warnings[0]}" if warnings else ""),
                "good")

        def do_save() -> None:
            doc, err, checked = validate_box()
            if err:
                say(err, "bad")
                return
            errors, _ = checked
            if errors:
                say("Not valid: " + " | ".join(errors), "bad")
                return
            editor.document = doc
            result = editor.save()
            if not result.ok:
                say(f"{result.reason}." + (f" {' | '.join(result.errors)}" if result.errors else ""),
                    "bad")
                return
            if result.reason == "nothing to save":
                say("Nothing differs — nothing was written.", "info")
                return
            live = ctx.bus.snapshot().get("layout_report")
            showing = isinstance(live, dict) and \
                _layout_key(live.get("layout_file")) == _layout_key(editor.name)
            if showing:
                # the same rebuild the alignment page does after an add or a removal: the geometry,
                # not just a nudge, may have changed
                ctx.bus.post({"cmd": "refresh_mode"})
            area.value = json.dumps(editor.document, indent=2, ensure_ascii=False) + "\n"
            area.update()
            backup = f" (backup: {os.path.basename(result.backup)})" if result.backup else ""
            say(f"Saved {result.rel}{backup}."
                + (" The display is rebuilding the mode so the change shows there." if showing
                   else " The display is not on this layout, so nothing was rebuilt."), "good")

        def do_reload() -> None:
            try:
                editor.reload()
            except LayoutError as e:
                say(f"could not reload: {e}", "bad")
                return
            area.value = json.dumps(editor.document, indent=2, ensure_ascii=False) + "\n"
            area.update()
            say("Re-read from disk — unsaved changes dropped.", "info")

        def do_format() -> None:
            doc, err = parse()
            if err:
                say(err, "bad")
                return
            area.value = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
            area.update()
            say("Re-indented (not saved).", "info")

        with ui.row().classes("gap-2 mt-2"):
            ui.button("Validate", on_click=do_validate).props("outline").mark("raw-layout-validate")
            ui.button("Save & rebuild", on_click=do_save).props("color=primary") \
                .mark("raw-layout-save")
            ui.button("Re-read from disk", on_click=do_reload).props("flat") \
                .mark("raw-layout-reload")
            ui.button("Re-indent", on_click=do_format).props("flat").mark("raw-layout-format")

        _footer()


def _register_layout_route(app, ctx: PageContext) -> None:
    # The page is a NiceGUI page (@ui.page), NOT a FastAPI route: a FastAPI route returns a response
    # and has no slot, so building UI inside one fails with "the slot stack for this task is empty".
    @ui.page("/layout")
    def layout_page(profile: str | None = None, mode: int | None = None):
        active_path, _ = profiles_mod.resolve_active_profile(ctx.base_dir, ctx.config_override)
        rel = profile or os.path.relpath(active_path, ctx.base_dir)
        _layout_page(ctx, rel, int(mode) if mode is not None else None)

    @app.get("/api/asset/background")
    def asset_background(name: str = "", layout: str = "", profile: str = "",
                         mode: int | None = None):
        """
        Serve the artwork the alignment page draws its boxes over.

        Two ways in, and neither can be turned into a reader of arbitrary files. A bare `name` stays
        restricted to the backgrounds directory. A `layout` is resolved EXACTLY as the page resolved
        it — through the same _artwork_in_use, including the mode parameter that overrides it — so
        the bytes handed back are the ones the app itself decided to draw rather than a path the
        caller invented. The extension check is stock: only files the renderer could load anyway.
        """
        from fastapi.responses import FileResponse

        if layout:
            editor = _open_layout(layout)
            if editor is None:
                return PlainTextResponse("no such layout", status_code=404)
            path, _canvas, _source = _artwork_in_use(ctx, profile, mode, editor)
        else:
            wanted = os.path.basename(str(name or ""))
            path = os.path.join(backgrounds_dir(), wanted) if wanted else ""
            if path and os.path.dirname(os.path.abspath(path)) != os.path.abspath(backgrounds_dir()):
                return PlainTextResponse("refused", status_code=403)
        if not path or not os.path.isfile(path):
            return PlainTextResponse("no such background", status_code=404)
        if os.path.splitext(path)[1].lower() not in (".png", ".jpg", ".jpeg", ".bmp", ".gif"):
            return PlainTextResponse("refused", status_code=403)
        return FileResponse(path, media_type="image/png")


def _align_link(ctx: PageContext, info, entry) -> None:
    """
    A way into the alignment page from the mode that needs it.

    Only for a control panel, and it says up front when the layout is the GRID flavour — that one has
    no pixel positions to nudge, and finding that out after the click is a poor welcome. Errors while
    reading the layout are shown rather than swallowed, because a broken layout_file is exactly the
    kind of thing this link should help you find.
    """
    if normalize_type(entry.type) != "controlpanel":
        return
    params = entry.params if isinstance(entry.params, dict) else {}
    layout_name = str(params.get("layout_file") or "").strip()
    flavour, note = "", ""
    if not layout_name:
        note = "This mode has no layout_file set, so there is nothing to align yet."
    else:
        try:
            flavour = LayoutEditor(layout_name).mode
        except Exception as e:                                  # unreadable/absent layout
            note = f"'{layout_name}' could not be read: {e}"

    with ui.card().classes("w-full mt-2 gap-1"):
        ui.label("Overlay alignment").classes("text-base font-semibold")
        if note:
            ui.label(note).classes("text-xs text-orange-300")
        elif flavour == "grid":
            ui.label(f"'{layout_name}' is a grid layout: its controls sit in whole 128px cells "
                     f"inside panels, so there is no pixel position to nudge. Point layout_file at a "
                     f"freeform layout — or create one over your own PNG — to align overlays on the "
                     f"artwork.").classes("text-xs text-orange-300")
        else:
            ui.label(f"Put each overlay of '{layout_name}' where it belongs on the artwork: nudge it "
                     f"live on the display, then save.").classes("text-xs opacity-60")
        ui.link("position overlays →", f"/layout?profile={info.rel}&mode={entry.number}") \
            .classes("text-sm").mark("align-overlays")


def _load_registry(base_dir: str) -> dict:
    """The registry's type specs. Re-read per page build so a hand edit shows up on reload."""
    registry = load_json(os.path.join(base_dir, "modes_registry.json"), {})
    return registry.get("types", {}) if isinstance(registry, dict) else {}


def _hex_from_rgb(value) -> str:
    if not (isinstance(value, (list, tuple)) and len(value) == 3):
        return "#000000"
    try:
        return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in value)
    except (TypeError, ValueError):
        return "#000000"


def _swatch(color_hex: str) -> None:
    ui.element("div").style(
        f"background:{color_hex};width:44px;height:22px;border-radius:4px;"
        "border:1px solid rgba(255,255,255,0.25)")


def _display_value(p):
    """What to show: the profile's value, else the mode code's default, else nothing."""
    if p.present:
        return p.value
    return p.default if p.has_default else None


def _mode_header(ctx: PageContext, info, entry, active_source: str) -> None:
    snap = ctx.bus.snapshot()
    live = bool(info.active and snap.get("mode_index") == entry.number)
    with ui.card().classes("w-full mt-2"):
        with ui.row().classes("items-baseline gap-3"):
            ui.label(f"Mode {entry.number}").classes("text-lg font-semibold")
            ui.label(entry.label or "—").classes("text-base")
            ui.label(entry.type).classes("text-sm opacity-60")
            if live:
                ui.badge("LIVE NOW").props("color=green").classes("text-xs").mark("live-badge")
        ui.label(
            f"profile {info.rel}" + (f" (on the display, chosen via {active_source})"
                                     if info.active else
                                     " (PREVIEW — not on the display; the profile card on the "
                                     "Modes page can switch to it)")
        ).classes("text-xs opacity-60")
        if entry.override_keys:
            ui.badge(f"modes_config.local.json supplies: {', '.join(entry.override_keys)}") \
                .props("outline color=orange").classes("text-xs")


# ---------------------------------------------------------------- editing (Phase 3)
#
# The page is a FORM over one profile FILE. Three things are deliberately separate, because
# confusing them is how this kind of panel goes wrong:
#
#   * the FILE (what ProfileEditor stages and writes) — the truth for editing
#   * the running APP (ctx.bus status) — the truth for what is on the wall
#   * what the two disagree about — which is exactly what the status line on this page reports
#
# Nothing is written until Save; the enable switch is the one exception (a switch that silently
# waits for a Save button is worse than one that acts, and it says so on the page).


def _rgb_from_hex(text: str):
    """'#ff8000' -> [255, 128, 0]. Returns None when it is not a colour."""
    if not isinstance(text, str):
        return None
    body = text.strip().lstrip("#")
    if len(body) == 3:
        body = "".join(ch * 2 for ch in body)
    if len(body) != 6:
        return None
    try:
        return [int(body[i:i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        return None


def _loads(text):
    """Parse a JSON box. Returns (ok, value_or_message)."""
    try:
        return True, json.loads(text)
    except (TypeError, ValueError) as e:
        return False, f"not valid JSON: {e}"


def _apply_payload(ctx: PageContext, profile_path: str, *, refresh: bool = False) -> dict:
    """
    The command that tells the running app to use the file's fresh state.

    The panel does the reading and posts finished dicts — the render thread never touches disk
    (AGENTS.md). Built through load_payload, i.e. the same loader the app runs at startup, so
    "applied" and "what a restart would show" cannot drift apart.
    """
    payload = load_payload(ctx.base_dir, profile_path)
    modes_config = payload["modes_config"]
    payload.update({
        "cmd": "apply_config",
        "refresh": bool(refresh),
        "config_path": profile_path,
        "config_sha256": sha256_file(profile_path) if os.path.exists(profile_path) else "",
        "max_modes": infer_max_modes_from_config(modes_config),
        "enabled": enabled_mode_indices(modes_config)[0],
    })
    return payload


class _ModeEditor:
    """Editing state for ONE mode page in ONE browser session."""

    def __init__(self, ctx: PageContext, info, entry, registry, overridden):
        self.ctx = ctx
        self.info = info
        self.entry = entry
        self.registry = registry
        self.params, self.warnings = resolve_params(
            entry.params, registry.get(entry.type_key, {}), entry.override_keys)
        self.editor = ProfileEditor(
            ctx.base_dir, info.path, registry,
            overridden={str(entry.number): tuple(entry.override_keys or ())})
        self.headline = ""
        self.headline_kind = "info"        # info | good | bad
        self.details: list = []
        self.last_backup = ""
        self.last_sha = ""
        # Set by _editable_mode_form so a field change can update the staged summary without
        # rebuilding every field (which would throw away focus mid-typing).
        self.refresh_actions = None

    # -- staging -------------------------------------------------------------------------

    def stage(self, key: str, value) -> str:
        try:
            self.editor.stage_set(self.entry.number, key, value)
        except EditorRefused as e:
            return str(e)
        return ""

    def unstage(self, key: str) -> str:
        try:
            self.editor.stage_remove(self.entry.number, key)
        except EditorRefused as e:
            return str(e)
        return ""

    def revert(self) -> None:
        self.editor.revert_all()
        self.say("Changes dropped — nothing was written.", "info")

    def reload_from_disk(self) -> None:
        self.editor.reload()
        self.say("Re-read from disk; staged changes dropped.", "info")

    def say(self, headline: str, kind: str = "info", details=()) -> None:
        self.headline, self.headline_kind = headline, kind
        self.details = [str(d) for d in details]

    # -- saving --------------------------------------------------------------------------

    def save(self, *, apply: bool, refresh: bool) -> bool:
        result = self.editor.save()
        if not result.ok:
            if result.conflict:
                self.say(f"{result.reason}. On disk now: {self.editor.conflict_detail()}", "bad")
            else:
                self.say(result.reason, "bad", result.errors)
            return False

        self.last_backup = result.backup
        self.last_sha = result.sha256
        wrote = result.reason
        extra = []
        if result.warnings:
            extra = list(result.warnings)
        if not result.wrote_anything:
            self.say("Nothing staged — nothing written.", "info")
            return True

        if apply:
            self.ctx.bus.post(_apply_payload(self.ctx, self.info.path, refresh=refresh))
            self.say(f"Saved ({wrote}). "
                     + ("Applied, and the mode on the wall was rebuilt."
                        if refresh else "Applied to the running app.")
                     + (f" Backup: {os.path.basename(self.last_backup)}" if self.last_backup
                        else ""), "good", extra)
        else:
            self.say(f"Saved ({wrote}) without telling the running app — it keeps the config it "
                     f"loaded until you press Apply or restart."
                     + (f" Backup: {os.path.basename(self.last_backup)}" if self.last_backup
                        else ""), "good", extra)
        return True

    def toggle_enabled(self, enabled: bool) -> None:
        """The one immediate action: a switch that waits for a Save button is a lie."""
        try:
            self.editor.stage_enabled(self.entry.number, bool(enabled))
        except EditorRefused as e:
            self.say(str(e), "bad")
            return
        if self.save(apply=True, refresh=False):
            word = "enabled" if enabled else "disabled"
            self.say(f"Mode {self.entry.number} {word} and the rotation updated — no restart.",
                     "good")
        else:
            # put the editor back in step with the file so the switch re-renders truthfully
            self.editor.reload()

    def refresh_mode(self) -> None:
        self.ctx.bus.post({"cmd": "refresh_mode"})
        self.say("Refresh queued — the mode is rebuilt on the next frame that is not mid-fade.",
                 "info")

    # -- facts shown on the page ---------------------------------------------------------

    def file_mode(self) -> dict:
        return self.editor.mode_config(self.entry.number)

    def staged_here(self) -> bool:
        return self.editor.is_dirty(self.entry.number)

    def staged_keys(self) -> dict:
        state = self.editor.staged.get(self.entry.number)
        if state is None:
            return {"sets": {}, "removes": [], "enabled": None}
        return {"sets": dict(state.sets), "removes": list(state.removes), "enabled": state.enabled}

    def live_note(self) -> tuple:
        """(text, colour) describing whether the wall is showing what this file says."""
        snap = self.ctx.bus.snapshot()
        if not self.info.active:
            return ("This profile is not on the display, so applying it updates the config in "
                    "memory only — use the profile card on the Modes page to switch the display "
                    "to it.", "opacity-60")
        if snap.get("display") == "off":
            return ("No display process is attached to this panel, so nothing is on the wall to "
                    "refresh.", "text-orange-300")
        if snap.get("mode_index") != self.entry.number:
            return (f"Mode {snap.get('mode_index')} is on the wall right now, not this one — "
                    f"edits apply immediately, and you see them after the rotation gets here "
                    f"(or press Refresh when it is showing).", "opacity-60")
        applied = snap.get("mode_config_digest")
        if applied and applied == config_digest(self.file_mode()):
            return ("The wall is showing this config.", "text-green-400")
        return ("The wall is showing an OLDER version of this mode — press Refresh to rebuild it "
                "with the saved values.", "text-orange-300")


def _enable_card(state: _ModeEditor) -> None:
    """
    Where the mode's own param --enable switch lives, and the honest line about what the wall is
    showing.

    The switch acts immediately (see _ModeEditor.toggle_enabled). A switch that silently waits for
    a Save button teaches you the wrong thing about the state of the config, and disabling a mode
    is a one-key change with nothing to stage.
    """
    def file_enabled() -> bool:
        state.editor.reload_if_changed()          # cheap: only re-reads when the file moved
        return state.editor.mode_config(state.entry.number).get("enabled") is not False

    note = ui.label().classes("text-xs").mark("live-note")
    box = {"switch": None, "syncing": False}

    def tick() -> None:
        """Update the note (and the switch, if the file says something else now)."""
        disabled = not file_enabled()
        head = ("This mode has \"enabled\": false in this profile, so the rotation skips it. "
                if disabled else "")
        text, colour = state.live_note()
        note.set_text(head + text)
        note.classes(replace=f"text-xs {colour}")
        switch = box["switch"]
        if switch is not None and bool(switch.value) == disabled:
            # guard against a switch/programmatic-write loop
            box["syncing"] = True
            switch.value = not disabled
            switch.update()
            box["syncing"] = False

    def on_toggle(e) -> None:
        if box["syncing"]:
            return
        state.toggle_enabled(bool(e.value))
        tick()
        if state.refresh_actions is not None:
            state.refresh_actions()

    with ui.card().classes("w-full mt-2 gap-2").mark("enable-card"):
        with ui.row().classes("items-center gap-3"):
            ui.label("Enabled in the rotation").classes("text-sm")
            box["switch"] = ui.switch(value=file_enabled(), on_change=on_toggle) \
                .mark("enable-switch")
            ui.label("writes immediately — no Save needed for this one") \
                .classes("text-xs opacity-50")
        note

    tick()
    ui.timer(REFRESH_SECONDS, tick)


def _readonly_mode_form(entry, params, warnings) -> None:
    """The read-only rendering, kept for modes this page cannot edit (e.g. override-only)."""
    with ui.card().classes("w-full mt-4 gap-1"):
        ui.label("Parameters").classes("text-base font-semibold")
        ui.label(
            f"{len(params)} field(s): every key this mode sets in this profile, plus every key "
            f"the registry declares for the type (including ones this profile does not set)."
        ).classes("text-xs opacity-60")
    for warning in warnings:
        ui.label(f"warning: {warning}").classes("text-xs text-orange-300").mark("form-warning")
    for group, items in group_params(params):
        with ui.card().classes("w-full mt-2"):
            ui.label(group.capitalize()).classes("text-sm font-semibold")
            for p in items:
                _param_field(p)
    with ui.expansion("Raw JSON for this mode").classes("w-full mt-2"):
        ui.textarea(value=json.dumps(entry.params, indent=2)) \
            .props("readonly rows=14").classes("w-full font-mono text-xs").mark("raw-json")


def _editable_mode_form(state: _ModeEditor) -> None:
    """The form, rebuildable, so Revert/Reload/Save re-render the fields from the file."""

    @ui.refreshable
    def fields() -> None:
        staged = state.staged_keys()
        for group, items in group_params(state.params):
            with ui.card().classes("w-full mt-2"):
                ui.label(group.capitalize()).classes("text-sm font-semibold")
                for p in items:
                    _editable_field(state, p, staged)

    with ui.card().classes("w-full mt-4 gap-1"):
        ui.label("Parameters — edit, then Save").classes("text-base font-semibold")
        ui.label(
            f"{len(state.params)} field(s), generated from the registry and this profile. "
            f"Nothing is written until you press Save; Revert costs nothing."
        ).classes("text-xs opacity-60")
        ui.label(
            "A field badged \"not set in this profile\" is declared by the registry but absent "
            "from this file — editing it ADDS the key. \"unset\" removes a key from the file. "
            "New modes need no work here: their fields come from the registry."
        ).classes("text-xs opacity-50").mark("form-help")
        ui.label("Secrets are never shown or written here; a value marked "
                 "'derived at runtime' is computed by the mode and only kept as a hint.") \
            .classes("text-xs opacity-50")
    for warning in state.warnings:
        ui.label(f"warning: {warning}").classes("text-xs text-orange-300").mark("form-warning")

    fields()

    # ---- the action bar: what has been staged, and what to do with it ----
    @ui.refreshable
    def actions() -> None:
        staged = state.staged_keys()
        editor = state.editor
        with ui.card().classes("w-full mt-3 gap-2").mark("editor-actions"):
            if state.headline:
                colour = {"good": "text-green-400", "bad": "text-red-400"} \
                    .get(state.headline_kind, "opacity-70")
                ui.label(state.headline).classes(f"text-sm {colour}").mark("editor-headline")
            for detail in state.details:
                ui.label(f"· {detail}").classes("text-xs text-red-300").mark("editor-detail")

            if not editor.is_dirty():
                ui.label("No staged changes.").classes("text-xs opacity-60") \
                    .mark("staged-summary")
            else:
                ui.label("Staged: " + editor.staged_summary()).classes("text-xs text-amber-300") \
                    .mark("staged-summary")

            if editor.is_stale():
                ui.label("This file changed on disk since this form was loaded. Saving is refused "
                         "until you Reload from disk (that is how a second tab or an ssh edit "
                         "cannot be silently overwritten).") \
                    .classes("text-xs text-orange-300").mark("stale-warning")

            def do_save(apply: bool, refresh: bool):
                def _run():
                    state.save(apply=apply, refresh=refresh)
                    fields.refresh()
                    actions.refresh()
                return _run

            with ui.row().classes("gap-2 items-center"):
                ui.button("Save & Apply", on_click=do_save(True, True)) \
                    .props("color=primary").mark("save-apply")
                ui.button("Save only", on_click=do_save(False, False)) \
                    .props("outline").mark("save-only")

                def do_revert():
                    state.revert()
                    fields.refresh()
                    actions.refresh()

                ui.button("Revert changes", on_click=do_revert).props("flat").mark("revert")

                def do_reload():
                    state.reload_from_disk()
                    fields.refresh()
                    actions.refresh()

                ui.button("Reload from disk", on_click=do_reload).props("flat").mark("reload")

                def do_refresh():
                    state.refresh_mode()
                    actions.refresh()

                ui.button("Refresh this mode now", on_click=do_refresh).props("outline") \
                    .mark("refresh-mode")

            ui.label("Save & Apply writes the file, then tells the running app to reload and "
                     "rebuild the mode — so a parameter change shows up on the wall without a "
                     "restart. Save only writes the file and leaves the app alone.") \
                .classes("text-xs opacity-50")

    actions()
    state.refresh_actions = actions.refresh


def _blank_for(p):
    """A sensible starting value for a parameter that is not set anywhere yet."""
    return {"switch": False, "number": 0, "range": [0, 0], "stringlist": [], "palette": [],
            "color": [255, 255, 255], "json": {}}.get(p.widget, "")


def _editable_field(state: _ModeEditor, p, staged: dict) -> None:
    with ui.row().classes("w-full items-start gap-4 py-2 border-b border-white/5") \
            .mark(f"param-{p.key}"):
        _param_labels(p)
        with ui.column().classes("grow gap-1"):
            notice = ui.label().classes("text-[11px] text-orange-300").mark(f"field-note-{p.key}")
            can_edit, why = _editable_why(state, p)
            if not can_edit:
                _param_widget(p)
                ui.label(why).classes("text-[11px] opacity-60")
                _help_line(p)
                return

            def on_change(value, key=p.key, box=notice):
                message = state.stage(key, value)
                problems = validate_param_value(p, value)
                box.set_text(" ".join([m for m in ([message] if message else []) + problems]))
                _mark_staged(state)

            current = staged["sets"].get(p.key, None)
            initial = current if p.key in staged["sets"] else _display_value(p)
            if p.key in staged["removes"]:
                initial = _blank_for(p)
                notice.set_text("staged for removal — Save to write that")
            _editable_widget(state, p, notice, on_change=on_change, initial=initial)
            _help_line(p)

            # numeric feedback for a value the schema bounds
            if p.widget == "number" and (p.min is not None or p.max is not None):
                bound = []
                if p.min is not None:
                    bound.append(f"min {p.min}")
                if p.max is not None:
                    bound.append(f"max {p.max}")
                ui.label(", ".join(bound)).classes("text-[10px] opacity-40")

            with ui.row().classes("gap-2 items-center"):
                if p.key in staged["removes"]:
                    def undo_remove(key=p.key):
                        state.editor.cancel_remove(state.entry.number, key)
                        _mark_staged(state)

                    ui.button("keep it after all", on_click=undo_remove).props("flat dense")
                elif p.present and not p.required:
                    def do_remove(key=p.key):
                        message = state.unstage(key)
                        if message:
                            notice.set_text(message)
                        _mark_staged(state)

                    ui.button("unset (remove the key)", on_click=do_remove) \
                        .props("flat dense").mark(f"unset-{p.key}")


def _editable_why(state: _ModeEditor, p) -> tuple:
    """Can this field be edited from this page? If not, why not — said plainly."""
    if p.secret:
        return False, "secret: supplied from secrets.json, never shown or written here"
    if p.derived:
        return False, "the mode computes this at runtime; edit it in the mode's code"
    if p.origin == "local override":
        return False, "modes_config.local.json supplies this value and wins over the profile"
    if not state.editor.mode_in_file(state.entry.number):
        return False, "this mode exists only in modes_config.local.json, so this profile has " \
                      "nothing to edit"
    return True, ""


def _mark_staged(state: _ModeEditor) -> None:
    """Cheap feedback that something is staged, without rebuilding every field (focus matters)."""
    if state.editor.is_dirty():
        state.say("Changes staged — press Save & Apply to write them.", "info")
    if state.refresh_actions is not None:
        state.refresh_actions()


def _editable_widget(state: _ModeEditor, p, notice, on_change, initial) -> None:
    """The editing version of one field. Read-only cases never reach here."""
    marker = f"param-widget-{p.key}"
    value = initial

    if p.widget == "switch":
        ui.switch(value=bool(value), on_change=lambda e: on_change(bool(e.value))) \
            .mark(marker)
        return

    if p.widget == "number":
        numeric = value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        ui.number(value=numeric, step=p.step,
                  on_change=lambda e: on_change(e.value)).classes("w-40").mark(marker)
        return

    if p.widget == "choice":
        options = list(p.choices) or [""]
        ui.select(options=options, value=value if value in options else None,
                  on_change=lambda e: on_change(e.value)).classes("w-full max-w-md").mark(marker)
        if p.suggestions:
            ui.label("known values: " + ", ".join(p.suggestions)).classes("text-[10px] opacity-50")
        return

    if p.widget == "text":
        options = _suggestions_for(p, extra=(value,))
        if options:
            # A dropdown you can type into. The known values are offered and a path stays a legal
            # answer, because "what is on disk" is not the whole set — and a closed set would hide
            # every layout that lives outside the assets tree.
            ui.select(options=list(options), value=value if value in options else None,
                      with_input=True, new_value_mode="add-unique",
                      on_change=lambda e: on_change(e.value)) \
                .classes("w-full max-w-md").mark(marker)
            return
        ui.input(value="" if value is None else str(value),
                 on_change=lambda e: on_change(e.value)).classes("w-full text-sm").mark(marker)
        if p.suggestions:
            ui.label("known values: " + ", ".join(p.suggestions)).classes("text-[10px] opacity-50")
        return

    if p.widget == "path":
        ui.input(value="" if value is None else str(value),
                 on_change=lambda e: on_change(e.value)) \
            .classes("w-full font-mono text-xs").mark(marker)
        if isinstance(value, str) and value:
            if os.path.isdir(value):
                ui.label("exists: directory").classes("text-[10px] text-green-400")
            elif os.path.isfile(value):
                ui.label("exists: file").classes("text-[10px] text-green-400")
            else:
                ui.label("not found on this machine").classes("text-[10px] text-orange-300")
        return

    if p.widget == "color":
        hex_value = _hex_from_rgb(value)
        with ui.row().classes("items-center gap-2"):
            _swatch(hex_value)

            def on_hex(e):
                rgb = _rgb_from_hex(e.value)
                if rgb is None:
                    notice.set_text("not a colour — use #rrggbb")
                    return
                on_change(rgb)

            ui.input(value=hex_value, on_change=on_hex).classes("w-32 font-mono text-xs") \
                .mark(marker)
        return

    if p.widget == "range":
        low, high = value if isinstance(value, list) and len(value) == 2 else (None, None)

        def on_edge(e, index):
            current = list(value) if isinstance(value, list) and len(value) == 2 else [None, None]
            current[index] = e.value
            if current[0] is None or current[1] is None:
                notice.set_text("both bounds are needed")
                return
            on_change([current[0], current[1]])

        with ui.row().classes("items-center gap-2"):
            ui.number(value=low, on_change=lambda e: on_edge(e, 0)).classes("w-28") \
                .mark(f"param-widget-{p.key}-min")
            ui.number(value=high, on_change=lambda e: on_edge(e, 1)).classes("w-28") \
                .mark(f"param-widget-{p.key}-max")
            ui.label(f"[min, max] of {p.item or 'number'}").classes("text-[10px] opacity-50")
        return

    if p.widget == "stringlist":
        text = "\n".join(str(v) for v in (value or []))
        ui.textarea(value=text,
                    on_change=lambda e: on_change([ln for ln in e.value.splitlines()
                                                   if ln.strip()])) \
            .classes("w-full font-mono text-xs").mark(marker)
        ui.label("one entry per line").classes("text-[10px] opacity-50")
        return

    if p.widget in ("palette", "json"):
        text = json.dumps(value, indent=2, default=str)

        def on_json(e, widget=p.widget):
            ok, parsed = _loads(e.value)
            if not ok:
                notice.set_text(parsed)
                return
            on_change(parsed)

        ui.textarea(value=text, on_change=on_json) \
            .classes("w-full font-mono text-xs").mark(marker)
        if p.widget == "palette":
            entries = value if isinstance(value, list) else []
            with ui.row().classes("items-center gap-1"):
                for colour in entries:
                    _swatch(_hex_from_rgb(colour))
        return

    # Anything unmodelled: offer the JSON box rather than pretending to understand it.
    ui.textarea(value=json.dumps(value, indent=2, default=str),
                on_change=lambda e: (_loads(e.value)[0] and on_change(_loads(e.value)[1])
                                     or notice.set_text(_loads(e.value)[1]))) \
        .classes("w-full font-mono text-xs").mark(marker)


def _suggestions_for(p, extra=()) -> tuple:
    """
    The values a field should offer: what the schema knows, plus a NAMED source resolved here.

    The name-to-values step lives in the panel rather than in core.params because this is where
    the asset paths are known — the schema module must not read the disk. A source that cannot be
    read yields nothing instead of failing the page: the controlpanel package may not be present at
    all (the test sandboxes copy core/ without it), and a missing picker is not an error.

    The CURRENT value is always included. A layout named by path, or a file deleted since it was
    chosen, must stay selectable — otherwise merely opening the page would change what is set.
    """
    values = [str(v) for v in (getattr(p, "suggestions", ()) or ())]
    source = getattr(p, "suggestions_from", "")
    try:
        if source == "layouts":
            values += [str(v) for v in list_layouts()]
        elif source == "backgrounds":
            values += [os.path.basename(str(v)) for v in list_backgrounds()]
    except Exception:                                      # no package, no assets, no picker
        pass
    for value in extra:
        if value not in (None, "") and str(value) not in values:
            values.append(str(value))
    return tuple(values)


def _help_line(p) -> None:
    """
    The registry's own words about a field.

    Shared by both renderings for one reason: the editable rows used to draw the widget and skip
    the help, so the only place a key's meaning is written down was invisible on the page you
    actually edit in.
    """
    if p.help:
        ui.label(p.help).classes("text-[11px] opacity-50").mark(f"param-help-{p.key}")


def _param_field(p) -> None:
    with ui.row().classes("w-full items-start gap-4 py-2 border-b border-white/5") \
            .mark(f"param-{p.key}"):
        _param_labels(p)
        with ui.column().classes("grow gap-1"):
            _param_widget(p)
            _help_line(p)


def _param_labels(p) -> None:
    """The left column: label, key, badges, type/widget note. Shared by both renderings."""
    with ui.column().classes("w-72 shrink-0 gap-0"):
        ui.label(p.label).classes("text-sm").mark(f"param-label-{p.key}")
        with ui.row().classes("gap-1 items-center"):
            ui.label(p.key).classes("text-[10px] opacity-40 font-mono")
            if p.required:
                ui.badge("required").props("outline").classes("text-[10px]")
            if p.derived:
                ui.badge("derived at runtime").props("outline color=purple") \
                    .classes("text-[10px]")
            if p.secret:
                ui.badge("secret").props("outline color=red").classes("text-[10px]")
            if not p.present:
                ui.badge("not set in this profile").props("outline color=blue") \
                    .classes("text-[10px]")
            elif p.origin == "local override":
                ui.badge("local override").props("outline color=orange").classes("text-[10px]")
        note = f"{p.type_name} · {p.widget}"
        if p.has_default:
            note += f" · code default {p.default!r}"
        ui.label(note).classes("text-[10px] opacity-40")


def _param_widget(p) -> None:
    """Render one field. Phase 2: always read-only, never a secret value."""
    value = _display_value(p)
    marker = f"param-widget-{p.key}"

    if p.widget == "secret":
        ui.label("•••••••• supplied from secrets.json — never sent to the browser") \
            .classes("text-sm opacity-60 font-mono").mark(f"param-secret-{p.key}")
        return

    if p.widget == "switch":
        ui.switch(value=bool(value)).disable().mark(marker)
        return

    if p.widget == "number":
        # A number field must never be able to take the page down: a value whose shape
        # disagrees with the widget (a string in a numeric field) shows as a note instead.
        numeric = value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        ui.number(value=numeric, step=p.step, min=p.min, max=p.max).disable().mark(marker)
        if numeric is None and value is not None:
            ui.label(f"value {value!r} is not a number — the widget and the value disagree; "
                     f"check the schema for '{p.key}'") \
                .classes("text-[10px] text-orange-300")
        return

    if p.widget == "choice":
        ui.select(options=list(p.choices), value=value).disable().mark(marker)
        if p.suggestions:
            ui.label("known values: " + ", ".join(p.suggestions)).classes("text-[10px] opacity-50")
        return

    if p.widget == "text":
        # NOTE: this branch must exist explicitly. Without it a plain string fell through to
        # the JSON fallback below, so `folder` rendered as a raw-JSON textarea.
        ui.input(value="" if value is None else str(value)).props("readonly") \
            .classes("w-full text-sm").mark(marker)
        if p.suggestions:
            ui.label("known values: " + ", ".join(p.suggestions)).classes("text-[10px] opacity-50")
        return

    if p.widget == "path":
        ui.input(value="" if value is None else str(value)).props("readonly") \
            .classes("w-full font-mono text-xs").mark(marker)
        if isinstance(value, str) and value:
            if os.path.isdir(value):
                ui.label("exists: directory").classes("text-[10px] text-green-400")
            elif os.path.isfile(value):
                ui.label("exists: file").classes("text-[10px] text-green-400")
            else:
                ui.label("not found on this machine (paths are usually per-host — see "
                         "modes_config.local.json)").classes("text-[10px] text-orange-300")
        return

    if p.widget == "color":
        with ui.row().classes("items-center gap-2"):
            _swatch(_hex_from_rgb(value))
            ui.input(value=_hex_from_rgb(value)).props("readonly") \
                .classes("w-28 font-mono text-xs").mark(marker)
            ui.label(str(value)).classes("text-[10px] opacity-50")
        return

    if p.widget == "range":
        low, high = (value if isinstance(value, list) and len(value) == 2 else (None, None))
        with ui.row().classes("items-center gap-2"):
            ui.number(value=low).disable().classes("w-28").mark(f"{marker}-min")
            ui.number(value=high).disable().classes("w-28").mark(f"{marker}-max")
            ui.label(f"[min, max] of {p.item or 'number'}").classes("text-[10px] opacity-50")
        return

    if p.widget == "stringlist":
        ui.textarea(value="\n".join(str(v) for v in (value or []))).props("readonly") \
            .classes("w-full font-mono text-xs").mark(marker)
        ui.label("one entry per line").classes("text-[10px] opacity-50")
        return

    if p.widget == "palette":
        entries = value if isinstance(value, list) else []
        with ui.row().classes("items-center gap-1"):
            for colour in entries:
                _swatch(_hex_from_rgb(colour))
        ui.textarea(value=json.dumps(entries)).props("readonly") \
            .classes("w-full font-mono text-xs").mark(marker)
        return

    # json (and anything unmodelled): show it, do not pretend to understand it
    ui.textarea(value=json.dumps(value, indent=2, default=str)) \
        .props("readonly rows=4").classes("w-full font-mono text-xs").mark(marker)


def _profile_rows(ctx: PageContext) -> list:
    """Profiles as plain dicts, for /api/status."""
    active_path, _ = profiles_mod.resolve_active_profile(ctx.base_dir, ctx.config_override)
    return [
        {"rel": p.rel, "label": p.label, "modes": p.mode_count, "active": p.active,
         "error": p.error}
        for p in profiles_mod.discover_profiles(ctx.base_dir, active_path)
    ]


def _install_token_gate(ctx: PageContext) -> None:
    """
    Refuse every HTTP request that carries no valid token, at the edge.

    The page builder checks the token too (defence in depth), but a page-level check can only
    render a refusal page — it still answers HTTP 200, which reads as "served" to a script and
    to anyone auditing the panel's exposure. This middleware is what makes an unauthenticated
    request a real 403 on every route.
    """

    @app.middleware("http")
    async def token_gate(request, call_next):
        if request.url.path == AUTH_PATH:
            return await call_next(request)
        if not _authorised(ctx, request):
            return PlainTextResponse(
                "token required: open " + AUTH_PATH + "?token=<panel_token> once, "
                "or send an X-Panel-Token header\n",
                status_code=403,
            )
        response = await call_next(request)
        # A valid token that arrived in the URL is REMEMBERED, so the very next click (which
        # carries no token) still works. Without this, "?token=..." authorised exactly one
        # request and every follow-up 403'd — which is not what the instructions say, and
        # clicking through the panel is the whole point.
        # A header is deliberately NOT remembered: that form is a per-request credential for
        # scripts, and it should not quietly install a cookie in whatever made the request.
        if request.query_params.get("token") and not request.cookies.get(COOKIE_NAME):
            response.set_cookie(COOKIE_NAME, ctx.token, httponly=True, samesite="lax",
                                max_age=COOKIE_MAX_AGE_SECONDS)
        return response


def _register_auth_route(ctx: PageContext) -> None:
    """GET /_panel/auth?token=... sets the access cookie (network bindings only)."""

    @app.get(AUTH_PATH)
    def panel_auth(token: str = "", redirect: str = "/"):
        if not ctx.token or not _secrets.compare_digest(token, ctx.token):
            return PlainTextResponse("invalid token", status_code=403)
        target = redirect if redirect.startswith("/") else "/"
        response = RedirectResponse(target, status_code=303)
        response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax",
                            max_age=COOKIE_MAX_AGE_SECONDS)
        return response
