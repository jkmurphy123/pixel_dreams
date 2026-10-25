# tests/test_panel_ui.py
#
# The panel's pages, rendered for real in-process (no browser, no server): the page
# builders actually execute, so a crash in a page fails the test instead of hiding behind
# an HTTP 200. NiceGUI ships `user_simulation` for this; we inline the same shape so the
# pages can be registered inside the reset window (nicegui_reset_globals wipes routes).
#
# Run this file standalone first when it fails:
#   timeout 90 python -m pytest tests/test_panel_ui.py -q

import json
import os
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from nicegui import core, ui
from nicegui.testing.general import nicegui_reset_globals, prepare_simulation
from nicegui.testing.user import User

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core import profiles as profiles_mod          # noqa: E402
from core.bus import ControlBus                     # noqa: E402
from panel.app import (                             # noqa: E402
    COOKIE_MAX_AGE_SECONDS,
    COOKIE_NAME,
    PageContext,
    _authorised,
    _presented_token,
    register_pages,
)


# ---------------------------------------------------------------- fixtures

def _project(tmp_path, active="modes_config.json"):
    """A two-profile project so the page has something real to list."""
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "modes_registry.json").write_text(json.dumps({
        "settings": {"modes_config_file": active},
        "types": {},
    }))
    (tmp_path / "modes_config.json").write_text(json.dumps({
        "modes": {
            "0": {"type": "SystemInformation", "refresh_hz": 2.0},
            "1": {"type": "StatusTicker", "name": "Ticker", "pause": 3.5},
        }
    }, indent=2))
    (tmp_path / "configs" / "modes_config_portrait.json").write_text(json.dumps({
        "profile": {"label": "Portrait wall", "resolution": [1080, 1920]},
        "modes": {
            "7": {"type": "Slideshow", "name": "Cyberart", "folder": "/x", "duration": 120},
        }
    }, indent=2))
    return str(tmp_path)


def _ctx(tmp_path, *, bind="127.0.0.1", token=None, bus=None, ungated=False):
    return PageContext(base_dir=_project(tmp_path), bus=bus or ControlBus(),
                       bind=bind, port=8090, token=token, ungated=ungated)


@asynccontextmanager
async def _panel(ctx):
    """Register the real pages and hand back a simulated User + a raw httpx client."""
    with nicegui_reset_globals():
        os.environ["NICEGUI_USER_SIMULATION"] = "true"
        try:
            prepare_simulation()
            register_pages(ctx)
            ui.run(lambda: ui.label("root"), storage_secret="test storage secret")
            async with core.app.router.lifespan_context(core.app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(core.app), base_url="http://test"
                ) as client:
                    yield SimpleNamespace(user=User(client), client=client)
        finally:
            os.environ.pop("NICEGUI_USER_SIMULATION", None)


# ---------------------------------------------------------------- the page renders

async def test_page_lists_the_active_profile_and_its_modes(tmp_path):
    ctx = _ctx(tmp_path)
    async with _panel(ctx) as p:
        await p.user.open("/")
        await p.user.should_see("control panel")
        await p.user.should_see("Profiles")
        await p.user.should_see("SystemInformation")
        await p.user.should_see("StatusTicker")
        await p.user.should_see("Ticker")
        # and the page says which one the display is actually on
        await p.user.should_see("This is the profile on the display now")

        # Profile options are offered in the selector. They are not rendered page text
        # (a select's options only exist once the dropdown opens), so assert on the
        # element's own options rather than with should_see.
        selects = list(p.user.find(marker="profile-select").elements)
        assert len(selects) == 1, "profile selector not rendered"
        options = selects[0].options
        assert set(options) == {"modes_config.json", "configs/modes_config_portrait.json"}
        assert "ACTIVE" in options["modes_config.json"]
        assert "Portrait wall" in options["configs/modes_config_portrait.json"]
        assert "1080x1920" in options["configs/modes_config_portrait.json"]


async def test_page_shows_live_status_from_the_bus(tmp_path):
    """No render loop in this test: we stamp the bus and the page must report it."""
    bus = ControlBus()
    bus.update_status(display="windowed", fps=59.5, frame=1234, mode_index=1,
                      mode_type="StatusTickerMode", mode_name="Ticker",
                      profile_rel="modes_config.json", pong_count=7)
    ctx = _ctx(tmp_path, bus=bus)

    async with _panel(ctx) as p:
        await p.user.open("/")
        await p.user.should_see("1 — StatusTickerMode — Ticker")
        await p.user.should_see("windowed")
        await p.user.should_see("frame 1234")


async def test_previewing_another_profile_is_labelled_as_not_active(tmp_path):
    """
    The inspected profile is chosen by URL (?profile=...). Driving the select widget itself
    is not simulated: NiceGUI 3.18's select handler reads front-end props that only exist in
    a browser, so firing its event from the harness raises inside the framework. The query
    parameter exercises the same rendering path (discovery, override merge, rows, notice).
    """
    ctx = _ctx(tmp_path)
    async with _panel(ctx) as p:
        await p.user.open("/?profile=configs/modes_config_portrait.json")
        await p.user.should_see("PREVIEW")
        await p.user.should_see("Switching to it")
        await p.user.should_see("Cyberart")
        await p.user.should_not_see("SystemInformation")


async def test_unknown_profile_falls_back_to_the_active_one(tmp_path):
    ctx = _ctx(tmp_path)
    async with _panel(ctx) as p:
        await p.user.open("/?profile=configs/does_not_exist.json")
        await p.user.should_see("SystemInformation")
        await p.user.should_see("This is the profile on the display now")


async def test_profile_selector_is_wired_and_lists_every_profile(tmp_path):
    """The dropdown must exist, carry every profile, and have a value-change listener."""
    ctx = _ctx(tmp_path)
    async with _panel(ctx) as p:
        await p.user.open("/")
        interaction = p.user.find(marker="profile-select")
        el = list(interaction.elements)[0]
        assert set(el.options) == {"modes_config.json", "configs/modes_config_portrait.json"}
        listeners = [listener.type for listener in el._event_listeners.values()]  # noqa: SLF001
        assert any("modelValue" in t for t in listeners), listeners
        assert el.value == "modes_config.json"          # starts on the active profile


async def test_ping_button_posts_a_command_to_the_bus(tmp_path):
    """The panel->loop direction, at the UI level: the click must reach the bus."""
    bus = ControlBus()
    ctx = _ctx(tmp_path, bus=bus)

    async with _panel(ctx) as p:
        await p.user.open("/")
        assert bus.pending() == 0
        p.user.find("Ping the render loop").click()      # click() is sync: no await
        assert bus.pending() == 1
        assert bus.drain()[0]["cmd"] == "ping"


async def test_broken_profile_is_reported_not_fatal(tmp_path):
    ctx = _ctx(tmp_path)
    (tmp_path / "configs" / "modes_config_broken.json").write_text("{ not json at all")

    async with _panel(ctx) as p:
        await p.user.open("/")
        await p.user.should_see("Profiles")             # page still stands
        await p.user.should_see("SystemInformation")


# ---------------------------------------------------------------- token gate

async def test_network_bound_page_requires_a_token(tmp_path):
    """A network-bound panel answers 403 (not a rendered page) for every route."""
    ctx = _ctx(tmp_path, bind="0.0.0.0", token="s3cret-token")
    async with _panel(ctx) as p:
        r = await p.client.get("/")
        assert r.status_code == 403
        assert "SystemInformation" not in r.text        # nothing leaked
        assert "token required" in r.text               # and it says how to get one


async def test_loopback_bound_panel_is_open(tmp_path):
    """The default binding is loopback, which needs no token."""
    ctx = _ctx(tmp_path, bind="127.0.0.1", token=None)
    async with _panel(ctx) as p:
        assert (await p.client.get("/")).status_code == 200


async def test_token_in_query_string_opens_the_page(tmp_path):
    ctx = _ctx(tmp_path, bind="0.0.0.0", token="s3cret-token")
    async with _panel(ctx) as p:
        await p.user.open("/?token=s3cret-token")
        await p.user.should_see("Profiles")
        await p.user.should_see("SystemInformation")


async def test_a_token_in_the_url_is_remembered_for_the_next_click(tmp_path):
    """
    Regression: "?token=..." used to authorise exactly ONE request, so the first click after it
    403'd — which is not what the panel's own instructions tell the user will happen.
    """
    ctx = _ctx(tmp_path, bind="0.0.0.0", token="s3cret-token")
    async with _panel(ctx) as p:
        first = await p.client.get("/?token=s3cret-token")
        assert first.status_code == 200
        assert COOKIE_NAME in first.headers.get("set-cookie", ""), "token was not remembered"

        p.client.cookies.set(COOKIE_NAME, "s3cret-token")
        second = await p.client.get("/mode/0")            # no token in the URL this time
        assert second.status_code == 200


async def test_a_header_token_is_not_remembered(tmp_path):
    """The header form is a deliberate per-request credential; it must not install a cookie."""
    ctx = _ctx(tmp_path, bind="0.0.0.0", token="s3cret-token")
    async with _panel(ctx) as p:
        r = await p.client.get("/api/status", headers={"x-panel-token": "s3cret-token"})
        assert r.status_code == 200
        assert COOKIE_NAME not in r.headers.get("set-cookie", "")


async def test_status_endpoint_is_gated_too(tmp_path):
    """A page guard is not protection for a route someone can call directly."""
    ctx = _ctx(tmp_path, bind="0.0.0.0", token="s3cret-token")
    async with _panel(ctx) as p:
        assert (await p.client.get("/api/status")).status_code == 403
        assert (await p.client.get("/api/status?token=wrong")).status_code == 403
        headers = {"x-panel-token": "s3cret-token"}
        r = await p.client.get("/api/status", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["status"]["app"] == "pixel_dreams"
        assert any(pr["active"] for pr in body["profiles"])


async def test_auth_route_sets_the_cookie_and_rejects_a_bad_token(tmp_path):
    ctx = _ctx(tmp_path, bind="0.0.0.0", token="s3cret-token")
    async with _panel(ctx) as p:
        assert (await p.client.get("/_panel/auth?token=nope")).status_code == 403

        r = await p.client.get("/_panel/auth?token=s3cret-token", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/"
        cookie = r.headers.get("set-cookie", "")
        assert COOKIE_NAME in cookie
        # it must be httpOnly (no script access) and last 60 days, not just the browser session
        assert "httponly" in cookie.lower(), cookie
        assert f"max-age={COOKIE_MAX_AGE_SECONDS}" in cookie.lower(), cookie

        # the cookie the route just set is what opens the page
        p.client.cookies.set(COOKIE_NAME, "s3cret-token")
        r2 = await p.client.get("/")
        assert r2.status_code == 200


async def test_the_cookie_lifetime_is_sixty_days(tmp_path):
    """60 days, stated once as a constant and asserted on both paths that set the cookie."""
    assert COOKIE_MAX_AGE_SECONDS == 60 * 24 * 60 * 60, COOKIE_MAX_AGE_SECONDS

    ctx = _ctx(tmp_path, bind="0.0.0.0", token="s3cret-token")
    async with _panel(ctx) as p:
        from_query = await p.client.get("/?token=s3cret-token")
        assert f"max-age={COOKIE_MAX_AGE_SECONDS}" in from_query.headers.get("set-cookie", "").lower()

        from_route = await p.client.get("/_panel/auth?token=s3cret-token",
                                        follow_redirects=False)
        assert f"max-age={COOKIE_MAX_AGE_SECONDS}" in from_route.headers.get("set-cookie", "").lower()


async def test_loopback_binding_needs_no_token(tmp_path):
    ctx = _ctx(tmp_path, bind="127.0.0.1", token=None)
    async with _panel(ctx) as p:
        await p.user.open("/")
        await p.user.should_see("Profiles")
        assert (await p.client.get("/api/status")).status_code == 200


async def test_an_ungated_panel_bounces_the_old_auth_url_to_the_page(tmp_path):
    """--panel-open: the stale /_panel/auth?token=... bookmark redirects instead of 404ing."""
    ctx = _ctx(tmp_path, bind="0.0.0.0", token="s3cret-token", ungated=True)
    async with _panel(ctx) as p:
        r = await p.client.get("/_panel/auth?token=s3cret-token", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/"
        assert (await p.client.get("/api/status")).status_code == 200
        assert (await p.client.get("/?token=s3cret-token")).status_code == 200


# ---------------------------------------------------------------- access rule (pure)

def test_authorised_matrix():
    loop = _ctx_light(bind="127.0.0.1", token=None)
    net = _ctx_light(bind="0.0.0.0", token="good")

    assert _authorised(loop, None) is True                    # loopback: open
    assert _authorised(net, None) is False
    assert _authorised(net, _req()) is False                  # no token offered
    assert _authorised(net, _req(header="wrong")) is False
    assert _authorised(net, _req(header="good")) is True
    assert _authorised(net, _req(cookie="good")) is True
    assert _authorised(net, _req(query="good")) is True
    assert _authorised(_ctx_light(bind="0.0.0.0", token=None), _req(query="")) is False


def test_presented_token_prefers_header_over_query():
    req = _req(header="from-header", cookie="from-cookie", query="from-query")
    assert _presented_token(req) == "from-header"
    assert _presented_token(None) == ""


def test_ungated_context_authorises_a_network_bind():
    """--panel-open (ctx.ungated) drops the gate even on 0.0.0.0, token or not."""
    open_ctx = PageContext(base_dir=".", bus=ControlBus(), bind="0.0.0.0", token="a-token",
                           ungated=True)
    assert open_ctx.token_required is False
    assert _authorised(open_ctx, None) is True
    assert _authorised(open_ctx, _req()) is True


class _Req:
    def __init__(self, header=None, cookie=None, query=""):
        self.headers = {"x-panel-token": header} if header else {}
        self.cookies = {COOKIE_NAME: cookie} if cookie else {}
        self.query_params = {"token": query} if query else {}


def _req(header=None, cookie=None, query=""):
    return _Req(header=header, cookie=cookie, query=query)


def _ctx_light(bind, token):
    return PageContext(base_dir=".", bus=ControlBus(), bind=bind, token=token)
