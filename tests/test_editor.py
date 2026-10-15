"""
core/editor.py — the rules for changing a config on disk.

This is the one operation in the project that can leave a kiosk dead, so the tests are about
refusals as much as about writes: a staged change must not touch the disk, an invalid one must be
blocked with a reason, and a file that moved under us must not be clobbered.

Two fixtures: a small synthetic project whose types have deliberate numbers/ranges/choices (so the
field rules can be tested exactly), and a COPY of the real tree (so the same rules are exercised
against the configs the panel actually edits).
"""

from __future__ import annotations

import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import load_project_config               # noqa: E402
from core.editor import (                                 # noqa: E402
    EditorRefused,
    ProfileEditor,
    load_payload,
)
from core.store import sha256_file                        # noqa: E402

REAL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REGISTRY = {
    "types": {
        "gauge": {
            "entrypoint": "modes.system_information_mode:SystemInformationMode",
            "required": ["title", "folder"],
            "optional": ["refresh_hz", "scale_mode", "bg_color", "bounds", "lines"],
        },
        "ticker": {
            "entrypoint": "modes.status_ticker_mode:StatusTickerMode",
            "required": [],
            "optional": ["font_size"],
        },
    }
}

PROFILE = {
    "profile": {"label": "Test wall", "resolution": [1080, 1920], "notes": "keep me"},
    "modes": {
        "0": {"type": "Gauge", "title": "Gauge", "folder": "/x", "refresh_hz": 30,
              "scale_mode": "cover"},
        "1": {"type": "Ticker", "font_size": 48},
    },
}


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


@pytest.fixture
def project(tmp_path):
    """A small project: registry, one profile, no local override."""
    _write(str(tmp_path / "modes_registry.json"), REGISTRY)
    _write(str(tmp_path / "modes_config.json"), PROFILE)
    return tmp_path


def _editor(root, **kwargs):
    registry = json.load(open(os.path.join(root, "modes_registry.json")))["types"]
    return ProfileEditor(str(root), os.path.join(root, "modes_config.json"), registry, **kwargs)


def _on_disk(root):
    return json.load(open(os.path.join(root, "modes_config.json")))


def _backups(root):
    d = os.path.join(root, ".backups")
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


# ---------------------------------------------------------------- staging is free

def test_staging_does_not_touch_the_disk(project):
    path = os.path.join(project, "modes_config.json")
    before = sha256_file(path)
    ed = _editor(project)
    ed.stage_set(0, "refresh_hz", 45)
    ed.stage_enabled(1, False)
    assert ed.is_dirty()
    assert sha256_file(path) == before, "staging wrote to the file"
    assert not _backups(project)
    assert _on_disk(project)["modes"]["0"]["refresh_hz"] == 30


def test_revert_and_unstage_are_free(project):
    ed = _editor(project)
    ed.stage_set(0, "refresh_hz", 45)
    ed.stage_set(1, "font_size", 12)
    assert ed.changed_modes() == [0, 1]
    ed.unstage(0)
    assert ed.changed_modes() == [1]
    ed.revert_all()
    assert not ed.is_dirty()
    assert ed.save().reason.startswith("nothing to save")


# ---------------------------------------------------------------- the write

def test_save_writes_only_what_was_staged(project):
    ed = _editor(project)
    ed.stage_set(0, "refresh_hz", 45)
    result = ed.save()

    assert result.ok and result.sha256 and result.modes == (0,)
    after = _on_disk(project)
    assert after["modes"]["0"]["refresh_hz"] == 45
    assert after["modes"]["0"]["scale_mode"] == "cover", "an untouched key changed"
    assert after["modes"]["1"] == PROFILE["modes"]["1"], "an untouched mode changed"
    assert after["profile"] == PROFILE["profile"], "the profile metadata block was lost"
    assert len(_backups(project)) == 1, "a save must leave a backup"
    # and the JSON is re-readable
    assert json.load(open(os.path.join(project, "modes_config.json")))["modes"]["0"]["refresh_hz"] == 45


def test_a_save_with_nothing_staged_writes_nothing(project):
    ed = _editor(project)
    path = os.path.join(project, "modes_config.json")
    before = sha256_file(path)
    result = ed.save()
    assert result.ok and not result.wrote_anything
    assert sha256_file(path) == before and not _backups(project)


def test_a_second_save_is_not_a_conflict_with_our_own_write(project):
    ed = _editor(project)
    ed.stage_set(0, "refresh_hz", 45)
    assert ed.save().ok
    ed.stage_set(0, "refresh_hz", 60)
    second = ed.save()
    assert second.ok and not second.conflict
    assert _on_disk(project)["modes"]["0"]["refresh_hz"] == 60
    assert len(_backups(project)) == 2


def test_enabled_false_is_written_and_enabling_removes_the_key(project):
    """Disabling writes a real boolean; enabling REMOVES the key so the round trip is exact."""
    path = os.path.join(project, "modes_config.json")
    original = sha256_file(path)

    ed = _editor(project)
    ed.stage_enabled(1, False)
    assert ed.save().ok
    assert _on_disk(project)["modes"]["1"]["enabled"] is False
    assert _editor(project).mode_config(1).get("enabled") is False

    ed2 = _editor(project)
    ed2.stage_enabled(1, True)
    assert ed2.save().ok
    after = _on_disk(project)["modes"]["1"]
    assert "enabled" not in after, f"enabling left the key behind: {after}"
    assert json.load(open(path)) == PROFILE, "the round trip changed the file"
    assert sha256_file(path) == original, "a disable -> enable round trip must be byte-identical"


def test_adding_a_declared_key_then_removing_it_is_a_no_op(project):
    ed = _editor(project)
    ed.stage_set(1, "font_size", 12)          # already present -> a change
    assert ed.is_dirty(1)
    ed.stage_set(1, "refresh_hz", 5)          # brand new key
    ed.stage_remove(1, "refresh_hz")
    assert ed.staged[1].sets == {"font_size": 12}   # the add/remove nets out; the real change stays
    assert ed.staged[1].removes == []
    ed.stage_remove(1, "font_size")           # a real removal
    assert ed.staged[1].removes == ["font_size"]


def test_removing_a_key_actually_removes_it(project):
    ed = _editor(project)
    ed.stage_remove(0, "scale_mode")
    assert ed.save().ok
    assert "scale_mode" not in _on_disk(project)["modes"]["0"]


def test_a_value_json_cannot_hold_is_refused_not_raised(project):
    """A free-form JSON field can hold anything the field rules allow — but not a set."""
    registry = json.load(open(os.path.join(project, "modes_registry.json")))
    registry["types"]["gauge"]["params"] = {"extras": {"widget": "json"}}
    registry["types"]["gauge"]["optional"].append("extras")
    _write(os.path.join(project, "modes_registry.json"), registry)
    ed = _editor(project)
    ed.stage_set(0, "extras", {1, 2, 3})      # a set: legal to stage, impossible to encode
    result = ed.save()
    assert not result.ok and "JSON" in result.reason, result.reason
    assert "extras" not in _on_disk(project)["modes"]["0"]


def test_a_none_for_a_number_field_is_refused_with_a_readable_reason(project):
    """Clearing a number box must not store null, and the message must say what is wrong."""
    registry = json.load(open(os.path.join(project, "modes_registry.json")))
    registry["types"]["gauge"]["params"] = {"refresh_hz": {"widget": "number", "type": "int"}}
    _write(os.path.join(project, "modes_registry.json"), registry)
    ed = _editor(project)
    ed.stage_set(0, "refresh_hz", None)
    result = ed.save()
    assert not result.ok and any("must be a number (got nothing)" in m for m in result.errors)


# ---------------------------------------------------------------- validation blocks writes

def test_an_out_of_range_number_is_blocked(project):
    registry = json.load(open(os.path.join(project, "modes_registry.json")))
    registry["types"]["gauge"]["params"] = {"refresh_hz": {"widget": "number", "type": "int",
                                                          "min": 1, "max": 60}}
    _write(os.path.join(project, "modes_registry.json"), registry)
    ed = _editor(project)
    ed.stage_set(0, "refresh_hz", 900)
    result = ed.save()
    assert not result.ok and not result.wrote_anything
    assert any("must be at most 60" in m for m in result.errors)
    assert _on_disk(project)["modes"]["0"]["refresh_hz"] == 30, "an invalid save modified the file"
    assert not _backups(project)


def test_a_fraction_for_an_integer_field_is_blocked(project):
    registry = json.load(open(os.path.join(project, "modes_registry.json")))
    registry["types"]["gauge"]["params"] = {"refresh_hz": {"widget": "number", "type": "int"}}
    _write(os.path.join(project, "modes_registry.json"), registry)
    ed = _editor(project)
    ed.stage_set(0, "refresh_hz", 2.5)
    result = ed.save()
    assert not result.ok and any("whole number" in m for m in result.errors)


def test_a_value_outside_a_closed_choice_set_is_blocked(project):
    registry = json.load(open(os.path.join(project, "modes_registry.json")))
    registry["types"]["gauge"]["params"] = {"scale_mode": {"widget": "choice",
                                                          "choices": ["cover", "contain"]}}
    _write(os.path.join(project, "modes_registry.json"), registry)
    ed = _editor(project)
    ed.stage_set(0, "scale_mode", "stretch")
    result = ed.save()
    assert not result.ok and any("must be one of: cover, contain" in m for m in result.errors)

    ed2 = _editor(project)
    ed2.stage_set(0, "scale_mode", "contain")
    assert ed2.save().ok
    assert _on_disk(project)["modes"]["0"]["scale_mode"] == "contain"


def test_the_widget_is_not_inferred_from_the_value_just_typed(project):
    """
    The circularity guard: `scale_mode` is a string in the profile. Staging a number into it must
    FAIL, not silently redefine the field as numeric because that is what the value looks like.
    """
    registry = json.load(open(os.path.join(project, "modes_registry.json")))
    registry["types"]["gauge"]["params"] = {"scale_mode": {"widget": "text"}}
    _write(os.path.join(project, "modes_registry.json"), registry)
    ed = _editor(project)
    ed.stage_set(0, "scale_mode", 5)
    result = ed.save()
    assert not result.ok and any("must be text" in m for m in result.errors), result.errors


def test_removing_a_required_key_is_blocked(project):
    ed = _editor(project)
    ed.stage_remove(0, "folder")              # required by the gauge type
    result = ed.save()
    assert not result.ok
    assert any("missing required keys" in m for m in result.errors)
    assert "folder" in _on_disk(project)["modes"]["0"]


def test_an_unknown_key_is_a_warning_that_does_not_block(project):
    ed = _editor(project)
    ed.stage_set(0, "led_collor", 3)          # a typo
    result = ed.save()
    assert result.ok, result.reason
    assert any("unknown key 'led_collor'" in w for w in result.warnings)
    assert _on_disk(project)["modes"]["0"]["led_collor"] == 3


def test_validation_error_messages_name_their_mode(project):
    ed = _editor(project)
    ed.stage_remove(0, "folder")
    ed.stage_set(1, "font_size", "big")
    v = ed.validate()
    assert not v.ok
    assert set(v.by_mode) >= {"0", "1"}


# ---------------------------------------------------------------- conflicts

def test_a_file_changed_underneath_us_is_not_clobbered(project):
    ed = _editor(project)
    ed.stage_set(0, "refresh_hz", 45)

    # someone else (an ssh session, another browser) edits the file
    other = _on_disk(project)
    other["modes"]["1"]["font_size"] = 99
    _write(os.path.join(project, "modes_config.json"), other)

    result = ed.save()
    assert not result.ok and result.conflict
    assert "changed on disk" in result.reason
    assert "mode 1" in ed.conflict_detail()
    after = _on_disk(project)
    assert after["modes"]["0"]["refresh_hz"] == 30, "the other change was overwritten"
    assert after["modes"]["1"]["font_size"] == 99


def test_reload_clears_the_conflict_and_drops_staged_changes(project):
    ed = _editor(project)
    ed.stage_set(0, "refresh_hz", 45)
    other = _on_disk(project)
    other["modes"]["1"]["font_size"] = 99
    _write(os.path.join(project, "modes_config.json"), other)

    ed.reload()
    assert not ed.is_dirty() and not ed.is_stale()
    ed.stage_set(0, "refresh_hz", 45)
    assert ed.save().ok
    assert _on_disk(project)["modes"]["1"]["font_size"] == 99


def test_force_saves_over_a_conflict(project):
    ed = _editor(project)
    ed.stage_set(0, "refresh_hz", 45)
    other = _on_disk(project)
    other["modes"]["1"]["font_size"] = 99
    _write(os.path.join(project, "modes_config.json"), other)
    assert ed.save(force=True).ok
    assert _on_disk(project)["modes"]["0"]["refresh_hz"] == 45


def test_conflict_detail_says_something_useful_when_only_whitespace_moved(project):
    path = os.path.join(project, "modes_config.json")
    ed = _editor(project)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n")
    assert ed.is_stale()
    assert "whitespace" in ed.conflict_detail()


# ---------------------------------------------------------------- what is not editable here

def test_a_key_from_the_local_override_cannot_be_staged_here(project):
    _write(os.path.join(project, "modes_config.local.json"),
           {"modes": {"0": {"refresh_hz": 12}}})
    ed = _editor(project, overridden={"0": ("refresh_hz",)})
    with pytest.raises(EditorRefused) as caught:
        ed.stage_set(0, "refresh_hz", 45)
    assert "modes_config.local.json" in str(caught.value)
    assert not ed.is_dirty()


def test_structural_keys_are_not_editable_here(project):
    ed = _editor(project)
    for key in ("type", "name", "title"):
        with pytest.raises(EditorRefused):
            ed.stage_set(0, key, "x")


def test_removing_something_that_is_not_there_is_refused(project):
    ed = _editor(project)
    with pytest.raises(EditorRefused):
        ed.stage_remove(0, "never_set_here")


def test_a_mode_that_only_exists_in_the_override_cannot_be_toggled(project):
    _write(os.path.join(project, "modes_config.local.json"),
           {"modes": {"9": {"type": "Ticker"}}})
    ed = _editor(project)
    assert not ed.mode_in_file(9)
    with pytest.raises(EditorRefused):
        ed.stage_enabled(9, False)


def test_staged_summary_is_readable(project):
    ed = _editor(project)
    ed.stage_set(0, "refresh_hz", 45)
    ed.stage_enabled(1, False)
    summary = ed.staged_summary()
    assert "refresh_hz = 45" in summary and "disabled" in summary


# ---------------------------------------------------------------- the real tree

@pytest.fixture
def real_copy(tmp_path):
    """A copy of the REAL project: registry + every profile, so the real configs are edited here."""
    for name in ("modes_registry.json", "modes_config.json"):
        shutil.copy2(os.path.join(REAL_ROOT, name), tmp_path / name)
    shutil.copytree(os.path.join(REAL_ROOT, "configs"), tmp_path / "configs")
    return tmp_path


def test_a_real_profile_round_trips_through_the_editor(real_copy):
    registry = json.load(open(real_copy / "modes_registry.json"))["types"]
    path = str(real_copy / "modes_config.json")
    before = json.load(open(path))["modes"]

    ed = ProfileEditor(str(real_copy), path, registry)
    assert ed.validate().ok, ed.validate().messages()

    # a real, harmless change: the first mode's own duration
    target = sorted(before, key=int)[0]
    old_duration = before[target].get("duration")
    ed.stage_set(int(target), "duration", (old_duration or 60) + 30)
    result = ed.save()
    assert result.ok, (result.reason, result.errors)

    after = json.load(open(path))["modes"]
    assert after[target]["duration"] == (old_duration or 60) + 30
    for key, cfg in before.items():
        if key != target:
            assert after[key] == cfg, f"mode {key} changed"
    assert len(_backups(real_copy)) == 1


def test_every_real_profile_reports_a_clean_validation(real_copy):
    registry = json.load(open(real_copy / "modes_registry.json"))["types"]
    profiles = [real_copy / "modes_config.json"] + sorted((real_copy / "configs").glob("*.json"))
    assert len(profiles) >= 8
    for path in profiles:
        ed = ProfileEditor(str(real_copy), str(path), registry)
        assert ed.validate().ok, (path.name, ed.validate().messages())


def test_a_real_edit_only_touches_the_edited_profile(real_copy):
    registry = json.load(open(real_copy / "modes_registry.json"))["types"]
    portrait = real_copy / "configs" / "modes_config_portrait.json"
    other = real_copy / "modes_config.json"
    other_before = sha256_file(str(other))

    ed = ProfileEditor(str(real_copy), str(portrait), registry)
    number = sorted(ed.modes(), key=int)[0]
    ed.stage_enabled(int(number), False)
    assert ed.save().ok

    assert json.load(open(portrait))["modes"][number]["enabled"] is False
    assert sha256_file(str(other)) == other_before, "editing one profile touched another file"


# ---------------------------------------------------------------- the apply payload

def test_load_payload_matches_what_a_restart_would_load(real_copy):
    """'Save & Apply' must apply exactly what a restart of the app would read."""
    registry = json.load(open(real_copy / "modes_registry.json"))["types"]
    path = str(real_copy / "modes_config.json")
    ed = ProfileEditor(str(real_copy), path, registry)
    number = sorted(ed.modes(), key=int)[0]
    ed.stage_set(int(number), "duration", 4242)
    assert ed.save().ok

    payload = load_payload(str(real_copy), path)
    _, _, fresh_modes, fresh_path = load_project_config(str(real_copy), config_override=path)
    assert payload["modes_config"] == fresh_modes
    assert payload["registry"] == registry
    assert payload["config_path"] == fresh_path
    assert payload["modes_config"][str(int(number))]["duration"] == 4242


def test_load_payload_includes_the_local_override(real_copy):
    _write(str(real_copy / "modes_config.local.json"), {"modes": {"1": {"duration": 7}}})
    payload = load_payload(str(real_copy), str(real_copy / "modes_config.json"))
    assert payload["modes_config"]["1"]["duration"] == 7
