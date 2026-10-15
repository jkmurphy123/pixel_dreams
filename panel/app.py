# panel/app.py
#
# The control panel's NiceGUI pages.
#
# Phase 1 is deliberately READ-ONLY: it shows which profile the display is using, that
# profile's modes, and the render loop's live status. Editing (Save/Refresh/enable toggles)
# arrives in Phase 3; nothing on these pages writes a file.
#
# Everything here runs on the panel thread. It may read files and the ControlBus; it must
# never touch pygame, ModeManager or a mode object. See AGENTS.md.
#
# Two shapes are used deliberately:
#   * status labels are built ONCE and updated in place through a dict of element references
#     (never a timed page rebuild), so a poll cannot destroy anything a client is using;
#   * the mode list is rebuilt only when the user changes the inspected profile or clicks
#     Reload from disk.

from __future__ import annotations

import os
import secrets as _secrets
import time
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from nicegui import app, context, ui

from core import profiles as profiles_mod
from core.bus import APP_NAME, APP_VERSION, ControlBus, is_loopback

#: How often the status labels are refreshed (a poll, never a page rebuild).
REFRESH_SECONDS = 1.0

#: Cookie the auth route sets, so the token is not needed in every URL.
COOKIE_NAME = "pd_panel_token"

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
        ui.row().classes("gap-4 text-sm")
    with ui.column().classes("w-full max-w-5xl mx-auto px-4 py-2 gap-1"):
        ui.label(subtitle).classes("text-sm opacity-70")


def _footer() -> None:
    ui.label(
        "Phase 1: read-only preview — this page writes nothing. Saving, mode enable/disable, "
        "refresh and profile switching arrive in Phases 3-4."
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

        _chrome("Live tuning for the kiosk display — no restart needed once editing lands.")
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
                                 ("commands", "Commands")):
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
                if e.override_keys:
                    ui.badge(f"local override: {', '.join(e.override_keys)}") \
                        .props("outline color=orange").classes("text-xs")
                else:
                    ui.label(f"{len(e.params)} params").classes("text-xs opacity-50")


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
        if request.url.path == AUTH_PATH or _authorised(ctx, request):
            return await call_next(request)
        return PlainTextResponse(
            "token required: open " + AUTH_PATH + "?token=<panel_token> once, "
            "or send an X-Panel-Token header\n",
            status_code=403,
        )


def _register_auth_route(ctx: PageContext) -> None:
    """GET /_panel/auth?token=... sets the access cookie (network bindings only)."""

    @app.get(AUTH_PATH)
    def panel_auth(token: str = "", redirect: str = "/"):
        if not ctx.token or not _secrets.compare_digest(token, ctx.token):
            return PlainTextResponse("invalid token", status_code=403)
        target = redirect if redirect.startswith("/") else "/"
        response = RedirectResponse(target, status_code=303)
        response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax")
        return response
