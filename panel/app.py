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
from core.config import config_digest, enabled_mode_indices, infer_max_modes_from_config
from core.editor import EditorRefused, ProfileEditor, load_payload
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
            ui.link("Modes", "/").classes("text-inherit")
    with ui.column().classes("w-full max-w-5xl mx-auto px-4 py-2 gap-1"):
        ui.label(subtitle).classes("text-sm opacity-70")


def _footer() -> None:
    ui.label(
        "Phase 2: the parameter form is generated and READ-ONLY — nothing on this page writes a "
        "file. Saving, mode enable/disable, Refresh and profile switching arrive in Phases 3-4."
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

        with ui.card().classes("w-full mt-4"):
            ui.label("Profiles").classes("text-base font-semibold")
            ui.label(
                "Mode numbers are slots within a profile, so the same number is a different mode "
                "in another profile. Exactly one profile is active on the display at a time."
            ).classes("text-xs opacity-60")

            select = ui.select(options={}, value=None, label="Profile to inspect") \
                .classes("w-full max-w-2xl").mark("profile-select")
            notice = ui.label().classes("text-sm").mark("profile-notice")
            rows = ui.column().classes("w-full gap-0 mt-2")

            def render_rows() -> None:
                """Rebuild the mode list for the profile currently selected."""
                infos = profiles_mod.discover_profiles(ctx.base_dir, active_path)
                info = next((p for p in infos if p.rel == state["view"]), None)
                is_active = info is not None and info.active
                notice.set_text(
                    f"This is the profile on the display now (chosen via {active_source})."
                    if is_active else
                    "PREVIEW only — this is not the profile on the display "
                    "(profile switching arrives in Phase 4)."
                )
                _render_mode_rows(rows, info, ctx.base_dir)

            def reload_from_disk() -> None:
                infos = profiles_mod.discover_profiles(ctx.base_dir, active_path)
                options = {p.rel: _profile_option_label(p) for p in infos}
                if state["view"] not in options:
                    state["view"] = _initial_view(ctx.base_dir, active_path, infos)
                select.options = options
                select.value = state["view"]
                select.update()
                render_rows()

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

        ui.timer(REFRESH_SECONDS, lambda: _refresh_status(ctx, labels))
        _refresh_status(ctx, labels)
        _footer()

    @ui.page("/mode/{number}")
    def mode_page(number: str) -> None:
        """
        The generated form for one mode in one profile.

        Phase 2 renders it READ-ONLY: every field shows its current value so you can see what
        the panel understands, and nothing on this page writes a file. Phase 3 turns the same
        fields into editors with Save & Apply.
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


# ---------------------------------------------------------------- data for pages

def _render_mode_rows(container, info, base_dir: str) -> None:
    """Rebuild the mode list for the profile being inspected."""
    container.clear()
    with container:
        if info is None:
            ui.label("Profile not found.").classes("text-sm")
            return
        if info.error:
            ui.label(f"{info.rel}: {info.error}").classes("text-sm")

        local_modes = profiles_mod.load_local_overrides(base_dir)
        modes, _meta = profiles_mod.profile_modes(info.path)
        merged, overridden = profiles_mod.merge_local_override(modes, local_modes)
        entries = profiles_mod.mode_entries(merged, overridden)

        if not entries:
            ui.label("No modes in this profile.").classes("text-sm")
            return

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


def _load_registry(base_dir: str) -> dict:
    """The registry's type specs. Re-read per page build so a hand edit shows up on reload."""
    from core.config import load_json

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
                                     if info.active else " (PREVIEW — not on the display)")
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
            return ("This profile is not on the display, so applying it will only update the "
                    "config in memory (profile switching arrives in Phase 4).", "opacity-60")
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


def _param_field(p) -> None:
    with ui.row().classes("w-full items-start gap-4 py-2 border-b border-white/5") \
            .mark(f"param-{p.key}"):
        _param_labels(p)
        with ui.column().classes("grow gap-1"):
            _param_widget(p)
            if p.help:
                ui.label(p.help).classes("text-xs opacity-50")


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
