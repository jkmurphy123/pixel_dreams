"""
Duplicate a mode into a new slot.

The feature exists so a mode can have variations, which makes one property the whole point: after
duplicating and editing the copy, the ORIGINAL must be untouched — byte for byte, in the file. Most of
this file is about that plus the decisions a duplicate has to make (which slot, what name, is it
enabled), and about the two ways it must refuse rather than clobber something.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.editor import EditorRefused, ProfileEditor, _distinct_label     # noqa: E402
from core.validation import validate_profile                             # noqa: E402
from panel.app import PageContext                                        # noqa: E402

from test_panel_wiring import _env, _read, _sandbox, _spawn, _stop, _wait_ready   # noqa: E402
from test_transport import _bus, _click, _marked, _panel                          # noqa: E402

TOKEN = "duplicate-token"

REGISTRY = {
    "settings": {"modes_config_file": "modes_config.json"},
    "types": {
        "alpha": {"entrypoint": "modes.system_information_mode:SystemInformationMode",
                  "required": [], "optional": ["font_size"]},
        "beta": {"entrypoint": "modes.system_information_mode:SystemInformationMode",
                 "required": ["folder"], "optional": [],
                 "params": {"folder": {"default": "/tmp"}}},
    },
}

PROFILE = {
    "modes": {
        "0": {"type": "alpha", "name": "First", "font_size": 20},
        "1": {"type": "alpha", "name": "Second", "font_size": 30},
        "2": {"type": "beta", "folder": "/mnt/ssd/projects/images", "enabled": False},
    },
}


def _project(tmp_path, profile=None, registry=None):
    root = tmp_path / "proj"
    (root / "configs").mkdir(parents=True, exist_ok=True)
    (root / "modes_registry.json").write_text(json.dumps(registry or REGISTRY, indent=2) + "\n")
    (root / "modes_config.json").write_text(json.dumps(profile or PROFILE, indent=2) + "\n")
    return str(root)


def _editor(root, name="modes_config.json"):
    return ProfileEditor(root, os.path.join(root, name), REGISTRY["types"])


def _file_modes(root, name="modes_config.json"):
    return json.load(open(os.path.join(root, name)))["modes"]


# ---------------------------------------------------------------- the rules

def test_the_copy_lands_in_the_next_free_slot(tmp_path):
    root = _project(tmp_path, profile={"modes": {"0": {"type": "alpha"},
                                                 "1": {"type": "alpha"},
                                                 "5": {"type": "alpha"}}})
    result = _editor(root).duplicate_mode(1)
    assert result.ok and result.slot == 6, "the next FREE slot, and gaps are not filled in"
    assert "6" in _file_modes(root)
    assert len(_file_modes(root)) == 4


def test_the_copy_is_a_verbatim_copy_of_every_setting(tmp_path):
    root = _project(tmp_path)
    original = dict(_file_modes(root)["1"])
    result = _editor(root).duplicate_mode(1)
    assert result.ok
    copy = _file_modes(root)["3"]
    assert copy["type"] == original["type"]
    assert copy["font_size"] == original["font_size"] == 30
    assert copy["name"] == "Second copy", "the one deliberate difference"
    assert {k: v for k, v in copy.items() if k != "name"} == \
        {k: v for k, v in original.items() if k != "name"}


def test_a_disabled_mode_duplicates_as_disabled(tmp_path):
    root = _project(tmp_path)
    result = _editor(root).duplicate_mode(2)
    assert result.ok and result.enabled is False
    assert _file_modes(root)["3"]["enabled"] is False, "the copy is as dormant as its source"
    assert _file_modes(root)["3"]["folder"] == "/mnt/ssd/projects/images"


def test_the_copy_gets_a_name_that_cannot_be_confused_with_the_original(tmp_path):
    root = _project(tmp_path)
    editor = _editor(root)
    assert editor.duplicate_mode(1).label == "Second copy"
    assert _editor(root).duplicate_mode(1).label == "Second copy 2", "and again, without colliding"
    assert _editor(root).duplicate_mode(1).label == "Second copy 3"
    names = [m.get("name") for m in _file_modes(root).values()]
    assert len(names) == len(set(names)), f"labels must be unique: {names}"


def test_a_mode_with_no_name_is_not_renamed(tmp_path):
    root = _project(tmp_path, profile={"modes": {"0": {"type": "alpha", "font_size": 20}}})
    result = _editor(root).duplicate_mode(0)
    assert result.ok and result.label == "" and result.renamed is False
    assert "name" not in _file_modes(root)["1"], "no setting invented for a mode that had none"


def test_a_title_is_used_when_there_is_no_name():
    entry = {"title": "Board"}
    assert _distinct_label(entry, {"0": entry}) == "Board copy"
    assert entry["title"] == "Board copy"


def test_editing_the_copy_leaves_the_original_untouched(tmp_path):
    """
    The point of the feature. Duplicate, change the copy, save — then compare the ORIGINAL's entry
    with what it was before. This is the assertion that makes "variations" true rather than hopeful.
    """
    root = _project(tmp_path)
    before = json.dumps(_file_modes(root)["1"], sort_keys=True)

    assert _editor(root).duplicate_mode(1).ok
    editor = _editor(root)
    editor.stage_set(3, "font_size", 96)
    assert editor.save().ok

    after = _file_modes(root)
    assert json.dumps(after["1"], sort_keys=True) == before, "the original changed"
    assert after["3"]["font_size"] == 96
    assert after["3"]["name"] == "Second copy" and after["1"]["name"] == "Second", \
        "the names stay as they were: 'name' is slot metadata, not an editable parameter"


def test_the_duplicate_is_written_through_the_normal_path(tmp_path):
    """Validation, a backup, and a file that still validates: it is a save, not a special case."""
    root = _project(tmp_path)
    result = _editor(root).duplicate_mode(0)
    assert result.ok
    assert result.saved is not None and result.saved.sha256
    assert result.saved.backup, "a duplicate keeps a backup like any other write"
    assert os.path.exists(result.saved.backup)
    issues = validate_profile(_file_modes(root), REGISTRY["types"], base_dir=root)
    assert not [i for i in issues if i.is_error], issues


def test_an_unknown_mode_is_refused(tmp_path):
    root = _project(tmp_path)
    with pytest.raises(EditorRefused) as e:
        _editor(root).duplicate_mode(9)
    assert "not in this profile" in str(e.value)
    assert len(_file_modes(root)) == 3, "nothing was written"


def test_a_copy_never_replaces_a_slot_that_appeared_on_disk(tmp_path):
    """
    The hazard: a pending copy is a slot number chosen when it was made ("the next free one"), and
    the file can gain that slot before the save lands — another tab, a hand edit, a reload. Writing
    then would silently REPLACE a mode instead of adding one, so the save refuses and says why.
    """
    root = _project(tmp_path)
    editor = _editor(root)
    editor.added["3"] = {"type": "alpha", "name": "Someone else's"}     # as duplicate_mode would
    other = json.load(open(os.path.join(root, "modes_config.json")))
    other["modes"]["3"] = {"type": "alpha", "name": "Written by someone else"}
    (tmp_path / "proj" / "modes_config.json").write_text(json.dumps(other, indent=2) + "\n")
    editor.reload_if_changed()                       # picks up the new file, keeps the pending copy

    saved = editor.save()
    assert saved.ok is False and saved.conflict is True
    assert "appeared in the file" in saved.reason
    assert _file_modes(root)["3"]["name"] == "Written by someone else", "it was replaced anyway"


def test_the_raw_document_session_refuses_to_duplicate(tmp_path):
    root = _project(tmp_path)
    editor = _editor(root)
    editor.stage_document({"modes": {"0": {"type": "alpha"}}})
    with pytest.raises(EditorRefused) as e:
        editor.duplicate_mode(0)
    assert "raw JSON editor" in str(e.value)


def test_a_real_mode_type_survives_duplication(tmp_path):
    """With the real registry: required keys, real widget values, and a profile that validates."""
    real_registry = json.load(open(os.path.join(BASE_DIR, "modes_registry.json")))["types"]
    root = _project(tmp_path, registry={"settings": {}, "types": real_registry},
                    profile={"modes": {"0": {"type": "slideshow", "name": "Cyberart",
                                             "folder": "/mnt/ssd/projects/images",
                                             "duration": 120}}})
    result = ProfileEditor(root, os.path.join(root, "modes_config.json"),
                           real_registry).duplicate_mode(0)
    assert result.ok and result.label == "Cyberart copy"
    copy = _file_modes(root)["1"]
    assert copy["folder"] == "/mnt/ssd/projects/images" and copy["duration"] == 120
    assert not [i for i in validate_profile(_file_modes(root), real_registry, base_dir=root)
                if i.is_error]


# ---------------------------------------------------------------- the page

def _ui_ctx(root, active=True, **extra):
    return PageContext(base_dir=root,
                       bus=_bus(display="fullscreen", mode_index=0, single_mode=False,
                                applied_rotation=[0, 1, 2], enabled_modes=[0, 1], max_modes=3,
                                pending_steps=0),
                       bind="127.0.0.1", **extra)


async def test_every_mode_row_offers_a_duplicate_button(tmp_path):
    root = _project(tmp_path)
    async with _panel(_ui_ctx(root)) as p:
        await p.user.open("/")
        await p.user.should_see("3 mode(s)")
        for number in (0, 1, 2):
            assert _marked(p, f"duplicate-mode-{number}") is not None


async def test_clicking_duplicate_adds_a_slot_and_reports_it(tmp_path):
    root = _project(tmp_path)
    ctx = _ui_ctx(root)
    async with _panel(ctx) as p:
        await p.user.open("/")
        _click(_marked(p, "duplicate-mode-1"))

        modes = _file_modes(root)
        assert len(modes) == 4 and modes["3"]["name"] == "Second copy"
        outcome = _marked(p, "duplicate-outcome")
        assert "Copied mode 1 to mode 3" in outcome.text
        assert "Second copy" in outcome.text
        assert "original is untouched" in outcome.text
        # the active profile was applied to the running display
        assert [c for c in ctx.bus.drain() if c.get("cmd") == "apply_config"], "not applied"


async def test_duplicating_in_a_previewed_profile_leaves_the_display_alone(tmp_path):
    """PREVIEW means another profile is the one on the display: write the file, do not touch it."""
    root = _project(tmp_path)
    ctx = _ui_ctx(root)
    async with _panel(ctx) as p:
        # inspect a DIFFERENT profile, so the duplicated one is not the active one
        other = tmp_path / "proj" / "configs" / "modes_config_other.json"
        other.write_text(json.dumps({"modes": {"0": {"type": "alpha", "name": "Only"}}}) + "\n")
        await p.user.open("/?profile=configs/modes_config_other.json")
        _click(_marked(p, "duplicate-mode-0"))

        assert json.load(open(other))["modes"]["1"]["name"] == "Only copy"
    assert not [c for c in ctx.bus.drain() if c.get("cmd") == "apply_config"], \
        "a preview must not change what the display plays"


# ---------------------------------------------------------------- the endpoint

def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _post(url, path, payload, token=TOKEN):
    req = urllib.request.Request(url + path, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Panel-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except ValueError:
            # a 403 is a plain-text body ("token required"), not JSON
            return e.code, {"raw": raw.decode("utf-8", "replace")}


def _status(url):
    req = urllib.request.Request(url + "/api/status")
    req.add_header("X-Panel-Token", TOKEN)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["status"]


def test_the_endpoint_duplicates_and_puts_the_copy_in_the_rotation(tmp_path):
    """
    Process-level: the copy must become a mode the app actually plays, and a duplicate of a DISABLED
    mode must not. Both matter — one is the feature, the other is that it does not quietly change what
    is on the wall.
    """
    root = _sandbox(tmp_path, secrets={"panel_token": TOKEN})
    (root / "modes_config.json").write_text(json.dumps({"modes": {
        "0": {"type": "tiny", "font_size": 20},
        "1": {"type": "tiny", "font_size": 28},
        "2": {"type": "tiny", "font_size": 34, "enabled": False},
    }}, indent=2) + "\n")

    port = _free_port()
    proc, log = _spawn(root, tmp_path, "dup.log", "--panel-port", str(port),
                       "--panel-bind", "127.0.0.1", env=_env())
    url = f"http://127.0.0.1:{port}"
    try:
        assert _wait_ready(url + "/api/status", proc, log), _read(log)
        assert _status(url)["applied_rotation"] == [0, 1]

        code, body = _post(url, "/api/duplicate", {"index": 1})
        assert code == 200 and body["ok"], body
        assert body["slot"] == 3 and body["enabled"] is True and body["applied"] is True

        deadline = time.time() + 10
        while time.time() < deadline and _status(url)["applied_rotation"] != [0, 1, 3]:
            time.sleep(0.2)
        assert _status(url)["applied_rotation"] == [0, 1, 3], "the copy did not join the rotation"
        assert proc.poll() is None

        # a duplicate of the disabled mode is written but stays out of the rotation
        code, body = _post(url, "/api/duplicate", {"index": 2})
        assert code == 200 and body["slot"] == 4 and body["enabled"] is False
        time.sleep(1.0)
        assert _status(url)["applied_rotation"] == [0, 1, 3], "a disabled copy changed the wall"

        file_modes = json.load(open(os.path.join(root, "modes_config.json")))["modes"]
        assert set(file_modes) == {"0", "1", "2", "3", "4"}
        assert file_modes["2"]["font_size"] == file_modes["4"]["font_size"] == 34
    finally:
        _stop(proc)


def test_the_endpoint_refuses_junk_and_absent_modes(tmp_path):
    root = _sandbox(tmp_path, secrets={"panel_token": TOKEN})
    port = _free_port()
    # Bound to the LAN so the token gate is actually in force (loopback needs no token at all).
    proc, log = _spawn(root, tmp_path, "dup2.log", "--panel-port", str(port),
                       "--panel-bind", "0.0.0.0", env=_env())
    url = f"http://127.0.0.1:{port}"
    try:
        assert _wait_ready(url + "/api/status", proc, log), _read(log)
        before = json.load(open(os.path.join(root, "modes_config.json")))

        assert _post(url, "/api/duplicate", {"index": "seven"})[0] == 400
        assert _post(url, "/api/duplicate", {})[0] == 400
        code, body = _post(url, "/api/duplicate", {"index": 42})
        assert code == 409 and "not in this profile" in body["reason"]
        assert _post(url, "/api/duplicate", {"index": 0}, token=None)[0] == 403
        assert json.load(open(os.path.join(root, "modes_config.json"))) == before, "wrote anyway"
        assert proc.poll() is None
    finally:
        _stop(proc)
