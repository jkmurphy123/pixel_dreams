"""
Aligning controlpanel overlays: the live mechanism (design Phase 6A).

Three levels, in the order the phase is built:

  * the MECHANISM — including a contract test over every class in the control catalogue, because
    reading the code missed six of them: they cached their drawing window instead of a centre, and
    a rect assignment left them drawing in the old place while everything looked correct.
  * the MODE's edit API — edit_rect / select / freeze / marker / report, driven on a real layout.
  * the ENDPOINT — a real controller process, headless on its own port, a nudge over HTTP and the
    refusal cases, so the whole path from command to wall is exercised.

Off-display throughout (SDL dummy): the kiosk's screen belongs to whatever is already on it.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame                                                              # noqa: E402
import pytest                                                              # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from controlpanel.controls import CONTROL_CLASSES, ControlContext, make_control   # noqa: E402
from controlpanel.layout import PlacedControl, load_layout                        # noqa: E402
from modes.control_panel_mode import ControlPanelMode                             # noqa: E402

from test_panel_wiring import _env                                                # noqa: E402

pygame.init()

BLACK = (0, 0, 0)


class _Cache:
    def get_font(self, name=None, size=20, bold=False):
        return pygame.font.Font(None, int(size))


class _Manager:
    """The minimum a mode needs: a screen, a font cache, an index."""

    def __init__(self, size=(1920, 1088)):
        self.screen = pygame.display.set_mode(size)
        self.cache = _Cache()
        self.mode_index = 0
        self.registry = {}
        self.modes_config = {}


def _ctx(seed=1234):
    return ControlContext(seed=seed, accent_rgb=(255, 176, 64), trace_rgb=(80, 255, 120),
                          lamp_rgb=None)


def _placed(ctype, rect, raw=None):
    x, y, w, h = rect
    return PlacedControl(ctype, "TEST_SPRITE", None, (x, y), (w, h),
                         dict(raw or {"type": ctype}), rect_px=rect)


def _extent(control, surface):
    """Where a control actually draws: alone on black, background colorkeyed away."""
    surface.fill(BLACK)
    surface.set_colorkey(BLACK)
    control.draw_overlay(surface)
    return surface.get_bounding_rect()


def _attrs(control):
    """
    Everything about a control EXCEPT its rect, for "did set_rect recompute anything?".

    Deliberately not a hand-written list of attribute names: my list missed six classes when I read
    the code and a seventh (keypad's entry_rect/grid_origin/grid_size) only showed up when this test
    ran. Snapshotting the whole __dict__ means a cache under ANY name is caught, so the contract
    cannot be half-kept by not knowing what to look for.
    """
    return {key: repr(value) for key, value in vars(control).items() if key != "rect"}


# ---------------------------------------------------------------- the contract

def test_every_control_class_survives_a_move():
    """
    The contract: EVERY type in the catalogue must actually move when set_rect() is used.

    This is the test that found the six classes reading their geometry through a cached
    `self.window` — proof that reviewing the code is not enough for this class of bug. A control is
    judged by what it DRAWS (containment in the new box and not the old one, the boxes deliberately
    non-overlapping) or, for a type that draws nothing in a frozen state, by its derived attributes
    changing. Anything else is a failure, not a shrug.
    """
    surface = pygame.Surface((1920, 1088))
    old_rect = (200, 200, 160, 160)
    new_rect = (900, 700, 160, 160)
    assert not pygame.Rect(*old_rect).colliderect(pygame.Rect(*new_rect)), "boxes must not overlap"

    drawn_ok, attrs_ok, drew_nothing, unverifiable = [], [], [], []
    for ctype in sorted(CONTROL_CLASSES):
        control = make_control(_placed(ctype, old_rect), _ctx())
        assert control is not None, f"{ctype} is in the catalogue but make_control returned None"
        for _ in range(20):                     # let animations produce something to draw
            control.update(0.35)

        before_extent = _extent(control, surface)
        before_attrs = _attrs(control)
        control.set_rect(new_rect)
        after_extent = _extent(control, surface)
        after_attrs = _attrs(control)

        moved = (after_extent.colliderect(pygame.Rect(*new_rect))
                 and not after_extent.colliderect(pygame.Rect(*old_rect)))
        if moved:
            drawn_ok.append(ctype)
        elif before_extent.width == 0 or before_extent.height == 0:
            drew_nothing.append(ctype)
            if before_attrs != after_attrs:
                attrs_ok.append(ctype)
            else:
                unverifiable.append(ctype)
        elif before_attrs != after_attrs:
            attrs_ok.append(ctype)              # draws, but the measurement could not see the move
        else:
            unverifiable.append(ctype)

    assert not unverifiable, (
        f"these types did not move and nothing about them changed: {unverifiable} — they cache "
        f"geometry derived from the rect that set_rect() is not recomputing")
    assert not drew_nothing or attrs_ok, "a type that draws nothing must still recompute its geometry"
    assert len(drawn_ok) + len(drew_nothing) == len(CONTROL_CLASSES), \
        f"unaccounted types: drawn={drawn_ok} blank={drew_nothing} attrs={attrs_ok}"


def test_control_classes_in_the_catalogue_all_construct():
    """A catalogue entry that cannot be built is a mode that cannot show it (no display needed)."""
    for ctype in sorted(CONTROL_CLASSES):
        control = make_control(_placed(ctype, (10, 10, 120, 120)), _ctx())
        assert control is not None, ctype
        assert tuple(control.rect) == (10, 10, 120, 120)


# ---------------------------------------------------------------- the mode

def _mode(layout="steampunk1", size=(1920, 1088)):
    mode = ControlPanelMode({"layout_file": layout})
    mode.enter(_Manager(size))
    assert mode.compositor is not None, f"{layout} failed to load: {mode._error}"
    return mode


def test_a_nudge_moves_the_overlay_and_only_where_it_should():
    """
    The end-to-end mechanism, measured on the rendered frame.

    Freeze first, so the only thing that can change the frame is the move — otherwise this would be
    the same mistake as my earlier spike, confounding "the animation moved" with "the control moved".
    """
    mode = _mode()
    assert mode.freeze(True)["frozen"] is True
    screen = pygame.display.set_mode((1920, 1088))
    mode.render(screen)
    before = pygame.image.tostring(screen, "RGB")

    index = sorted(mode._by_index)[0]
    old = tuple(mode._by_index[index].rect)
    new = (old[0] + 300, old[1] + 220, old[2], old[3])
    report = mode.edit_rect(index, new)
    assert report["ok"] is True and report["rect"] == new

    mode.render(screen)
    after = pygame.image.tostring(screen, "RGB")
    assert before != after, "the frame did not change at all after the nudge"

    old_box = pygame.Rect(*old)
    new_box = pygame.Rect(*new)
    assert not old_box.colliderect(new_box), "the test's own boxes overlap, so it proves nothing"
    # every changed pixel must lie in one of the two boxes: the overlay left the old place and
    # appeared in the new one, and nothing else on the panel moved
    width = screen.get_width()
    outside = 0
    for i in range(0, len(before), 3):
        if before[i:i + 3] != after[i:i + 3]:
            pixel = i // 3
            point = (pixel % width, pixel // width)
            if not (old_box.collidepoint(point) or new_box.collidepoint(point)):
                outside += 1
    assert outside == 0, f"{outside} pixels changed outside the two boxes"

    # and the live report says what the wall is showing
    live = mode.layout_report()
    assert live["rects"][str(index)] == list(new)
    assert live["frozen"] is True


def test_a_resize_is_a_move_with_different_numbers():
    mode = _mode()
    index = sorted(mode._by_index)[0]
    old = tuple(mode._by_index[index].rect)
    report = mode.edit_rect(index, (old[0], old[1], old[2] * 2, old[3] * 2))
    assert report["ok"] and report["rect"] == (old[0], old[1], old[2] * 2, old[3] * 2)


def test_an_index_this_layout_does_not_have_is_refused_with_the_reason():
    mode = _mode()
    report = mode.edit_rect(999, (0, 0, 10, 10))
    assert report["ok"] is False and "no control #999" in report["reason"]
    assert mode.select(999)["ok"] is False


def test_a_static_only_type_says_so_instead_of_doing_nothing(tmp_path):
    """
    In a freeform layout a type with no animated overlay draws NOTHING, so moving it changes nothing
    visible. The refusal has to say that, or the person pressing the button concludes the tool is
    broken. (Synthetic layout, so this does not depend on a shipped layout having such a type.)
    """
    layout_file = tmp_path / "static_test.json"
    layout_file.write_text(json.dumps({
        "name": "static_test", "mode": "freeform", "design_resolution": [800, 600],
        "controls": [
            {"type": "lamp", "sprite": "LED_LAMP_RED", "at": [100, 100], "size": [80, 80]},
            {"type": "plate", "sprite": "GAUGE_ROUND_SMALL_1", "at": [300, 100], "size": [120, 90]},
        ],
    }) + "\n")

    mode = ControlPanelMode({"layout_file": str(layout_file)})
    mode.enter(_Manager((800, 600)))
    assert mode.compositor is not None, mode._error
    assert mode._static_only == [1], mode._static_only

    report = mode.edit_rect(1, (10, 10, 20, 20))
    assert report["ok"] is False and "static-only" in report["reason"]
    assert mode.edit_rect(0, (10, 10, 20, 20))["ok"] is True, "the animated one still moves"
    # selecting a static-only control is allowed: it still gets a marker to align against
    assert mode.select(1)["ok"] is True
    markers = mode.marker_rects()
    assert markers and markers[0][1] == "#1"
    assert mode.layout_report()["static_only"] == [1]


def test_freeze_holds_the_overlays_still():
    """
    freeze() means "skip update()", because dt=0 does not hold every animation still — some advance
    off the wall clock or on randomness. Proved by the thing that matters: two renders with no
    intervening update are IDENTICAL.
    """
    mode = _mode()
    screen = pygame.display.set_mode((1920, 1088))
    for _ in range(20):
        mode.update(0.35)

    mode.freeze(True)
    mode.render(screen)
    first = pygame.image.tostring(screen, "RGB")
    for _ in range(10):
        mode.update(0.35)                       # would animate, if not frozen
    mode.render(screen)
    assert pygame.image.tostring(screen, "RGB") == first, "a frozen panel still animated"

    mode.freeze(False)
    for _ in range(10):
        mode.update(0.35)
    mode.render(screen)
    assert pygame.image.tostring(screen, "RGB") != first, "thawing did not bring the animation back"


def test_the_marker_is_drawn_on_the_wall_for_the_selected_control():
    mode = _mode()
    screen = pygame.display.set_mode((1920, 1088))
    mode.freeze(True)
    index = sorted(mode._by_index)[0]
    rect = tuple(mode._by_index[index].rect)

    mode.select(None)
    mode.render(screen)
    without = pygame.image.tostring(screen, "RGB")
    assert mode.marker_rects() == []

    mode.select(index)
    mode.render(screen)
    with_marker = pygame.image.tostring(screen, "RGB")
    assert without != with_marker, "selecting a control drew no marker"
    assert mode.marker_rects() == [(rect, f"#{index}")]

    # the marker's own colour appears somewhere in the selected rect
    assert mode.compositor._MARKER_RGB is not None
    assert mode.select(None)["selected"] is None


# ---------------------------------------------------------------- the endpoint, with a real process

def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _post(url, path, payload):
    req = urllib.request.Request(url + path, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _status(url):
    with urllib.request.urlopen(url + "/api/status", timeout=10) as resp:
        return json.loads(resp.read())["status"]


def _wait_for(url, predicate, timeout=25.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            stamp = _status(url)
        except Exception:
            time.sleep(0.2)
            continue
        if predicate(stamp):
            return stamp
        time.sleep(0.2)
    return None


@pytest.fixture
def control_panel_kiosk(tmp_path):
    """
    A real controller, headless, pinned to a throwaway profile whose only mode is a control panel.

    Started from the real project tree (the layout, its PNG and the controlpanel package all live
    there) but with its own port and no display, so the wall that is actually running is not touched.
    """
    profile = tmp_path / "layout_test_profile.json"
    profile.write_text(json.dumps({"modes": {"0": {"type": "controlpanel",
                                                   "layout_file": "steampunk1",
                                                   "scale_mode": "fit"}}}) + "\n")
    port = _free_port()
    # `_env()` strips the three things a child would otherwise inherit from the parent test run
    # (nicegui then takes the screen-test path and the panel never starts) — see test_panel_wiring.
    env = _env(SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    log = tmp_path / "layout.log"
    with open(log, "w") as handle:
        proc = subprocess.Popen(
            [sys.executable, "pixel_dreams.py", "--panel-port", str(port),
             "--panel-bind", "127.0.0.1", "--config", str(profile), "--start", "0"],
            cwd=BASE_DIR, env=env, stdout=handle, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    try:
        assert _wait_for(url, lambda s: isinstance(s.get("layout_report"), dict)), \
            f"the control panel never published a layout:\n{log.read_text()[-1500:]}"
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_the_endpoint_nudges_the_layout_on_screen(control_panel_kiosk):
    url = control_panel_kiosk
    before = _status(url)["layout_report"]
    assert before["controls"] == 17 and before["animated"] == 17, before
    index = sorted(int(k) for k in before["rects"])[0]
    old = before["rects"][str(index)]
    new = [old[0] + 40, old[1] + 30, old[2], old[3]]

    code, body = _post(url, "/api/layout", {"op": "set_rect", "layout": "steampunk1",
                                            "index": index, "rect": new})
    assert code == 202 and body["ok"] is True, body

    applied = _wait_for(url, lambda s: (s.get("layout_report") or {}).get("rects", {})
                        .get(str(index)) == new)
    assert applied is not None, "the loop never applied the nudge"
    assert "moved #%d" % index in applied["layout_edit"], applied["layout_edit"]

    # selection and freeze travel the same path
    assert _post(url, "/api/layout", {"op": "select", "index": index})[0] == 202
    assert _wait_for(url, lambda s: (s.get("layout_report") or {}).get("selected") == index)
    assert _post(url, "/api/layout", {"op": "freeze", "on": True})[0] == 202
    assert _wait_for(url, lambda s: (s.get("layout_report") or {}).get("frozen") is True)
    assert _post(url, "/api/layout", {"op": "select", "index": None})[0] == 202
    assert _wait_for(url, lambda s: (s.get("layout_report") or {}).get("selected") is None)


def test_the_endpoint_refuses_a_layout_that_is_not_on_screen(control_panel_kiosk):
    """
    The guard that matters most: a nudge aimed at the layout being edited must never move an overlay
    in whatever layout happens to be playing.
    """
    url = control_panel_kiosk
    code, body = _post(url, "/api/layout", {"op": "set_rect", "layout": "freeform_demo",
                                            "index": 0, "rect": [10, 10, 50, 50]})
    assert code == 409 and "not 'freeform_demo'" in body["reason"], body

    before = _status(url)["layout_report"]["rects"]["0"]
    assert before != [10, 10, 50, 50], "the refusal still moved something"


def test_the_endpoint_rejects_junk(control_panel_kiosk):
    url = control_panel_kiosk
    assert _post(url, "/api/layout", {"op": "sideways"})[0] == 400
    assert _post(url, "/api/layout", {"op": "set_rect", "index": 0, "rect": [1, 2, 3]})[0] == 400
    assert _post(url, "/api/layout", {"op": "set_rect", "rect": [1, 2, 3, 4]})[0] == 400
    assert _post(url, "/api/layout", {"op": "select", "index": "three"})[0] == 400
    assert _post(url, "/api/layout", {"op": "set_rect", "index": 999,
                                      "rect": [1, 2, 3, 4]})[0] == 202      # queued, refused there
    assert _wait_for(url, lambda s: "refused" in str(s.get("layout_edit", ""))) is not None


def test_the_endpoint_refuses_when_the_mode_is_not_a_control_panel(tmp_path):
    """A kiosk showing anything else has nothing to align, and says so rather than 500ing."""
    profile = tmp_path / "not_a_panel.json"
    profile.write_text(json.dumps({"modes": {"0": {"type": "systeminformation",
                                                   "refresh_hz": 1.0}}}) + "\n")
    port = _free_port()
    env = _env(SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    log = tmp_path / "plain.log"
    with open(log, "w") as handle:
        proc = subprocess.Popen(
            [sys.executable, "pixel_dreams.py", "--panel-port", str(port),
             "--panel-bind", "127.0.0.1", "--config", str(profile), "--start", "0"],
            cwd=BASE_DIR, env=env, stdout=handle, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    try:
        assert _wait_for(url, lambda s: s.get("mode_type") is not None), log.read_text()[-800:]
        code, body = _post(url, "/api/layout", {"op": "select", "index": 0})
        assert code == 409 and "not a control panel" in body["reason"], body
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
