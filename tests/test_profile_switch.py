"""
Phase 4 core: which profile is active (runtime/active_profile.json + its precedence), switching to
another one, whole-document staging, and restoring a backup.

The theme of this file: the RESOLUTION IS ONE FUNCTION. The startup loader, the panel's "active
profile" display and the switcher all read the same answer, because a switch that changes what the
panel reports but not what the app loads would be worse than no switch at all.
"""

from __future__ import annotations

import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import (                                    # noqa: E402
    active_profile_file,
    load_project_config,
    read_active_profile,
    resolve_active_profile,
    write_active_profile,
)
from core.editor import (                                    # noqa: E402
    EditorRefused,
    ProfileEditor,
    list_backups,
    restore_backup,
    switch_profile,
)
from core.store import sha256_file                            # noqa: E402

REAL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REGISTRY = {
    "settings": {"modes_config_file": "configs/from_registry.json"},
    "types": {
        "gauge": {
            "entrypoint": "modes.system_information_mode:SystemInformationMode",
            "required": ["title"],
            "optional": ["font_size", "refresh_hz"],
        },
    },
}

LANDSCAPE = {"profile": {"label": "Landscape", "resolution": [1920, 1080]},
             "modes": {"0": {"type": "Gauge", "title": "L", "font_size": 40}}}
PORTRAIT = {"profile": {"label": "Portrait", "resolution": [1080, 1920]},
            "modes": {"0": {"type": "Gauge", "title": "P", "font_size": 24},
                      "1": {"type": "Gauge", "title": "P2", "font_size": 28}}}
FROM_REGISTRY = {"profile": {"label": "Registry pick"},
                 "modes": {"0": {"type": "Gauge", "title": "R"}}}


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


@pytest.fixture
def project(tmp_path):
    _write(str(tmp_path / "modes_registry.json"), REGISTRY)
    _write(str(tmp_path / "modes_config.json"), LANDSCAPE)
    _write(str(tmp_path / "configs" / "from_registry.json"), FROM_REGISTRY)
    _write(str(tmp_path / "configs" / "modes_config_portrait.json"), PORTRAIT)
    return tmp_path


def _registry(root):
    return json.load(open(os.path.join(root, "modes_registry.json")))["types"]


def _rel(root, path):
    return os.path.relpath(str(path), str(root))


# ---------------------------------------------------------------- the runtime record

def test_no_recorded_profile_reads_as_empty(project):
    assert read_active_profile(str(project)) == ""
    assert not os.path.exists(active_profile_file(str(project)))


def test_recording_a_profile_writes_a_relative_path(project):
    report = write_active_profile(str(project), str(project / "configs" / "modes_config_portrait.json"))
    assert report["profile"] == "configs/modes_config_portrait.json"
    assert read_active_profile(str(project)) == "configs/modes_config_portrait.json"
    on_disk = json.load(open(active_profile_file(str(project))))
    assert on_disk["profile"] == "configs/modes_config_portrait.json"
    # and it is a real JSON file, one line of derived state, no backup clutter
    assert not os.path.exists(str(project / "runtime" / ".backups"))


def test_a_malformed_record_reads_as_empty_instead_of_raising(project):
    """Derived state must never be able to stop a kiosk from starting."""
    path = active_profile_file(str(project))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for junk in ("not json at all", "[1, 2]", "null", '{"profile": 42}', '{"other": "x"}'):
        with open(path, "w") as fh:
            fh.write(junk)
        assert read_active_profile(str(project)) == "", junk
    # a bare string is tolerated (a human may well have typed it)
    with open(path, "w") as fh:
        fh.write('"configs/modes_config_portrait.json"')
    assert read_active_profile(str(project)) == "configs/modes_config_portrait.json"


# ---------------------------------------------------------------- precedence

def test_precedence_cli_beats_runtime_beats_registry(project):
    # nothing recorded: the registry's setting wins over the default
    path, source = resolve_active_profile(str(project))
    assert source == "registry" and path.endswith("configs/from_registry.json")

    write_active_profile(str(project), "configs/modes_config_portrait.json")
    path, source = resolve_active_profile(str(project))
    assert source == "runtime" and path.endswith("configs/modes_config_portrait.json")

    path, source = resolve_active_profile(str(project), "modes_config.json")
    assert source == "cli" and path.endswith("modes_config.json")


def test_the_loader_obeys_the_recorded_profile(project):
    """The unification that matters: what the app LOADS is the same answer the panel reports."""
    # nothing recorded yet, so the registry's pick is what loads
    assert load_project_config(str(project))[2]["0"]["title"] == "R"

    write_active_profile(str(project), "configs/modes_config_portrait.json")
    _, _, modes, config_path = load_project_config(str(project))
    assert config_path.endswith("modes_config_portrait.json")
    assert sorted(modes) == ["0", "1"]
    assert modes["0"]["title"] == "P"


def test_a_recorded_profile_that_vanished_falls_through(project):
    """Deleting the profile a kiosk was switched to must not stop it starting."""
    write_active_profile(str(project), "configs/modes_config_portrait.json")
    os.remove(str(project / "configs" / "modes_config_portrait.json"))
    path, source = resolve_active_profile(str(project))
    assert source == "registry" and path.endswith("configs/from_registry.json")
    assert load_project_config(str(project))[2]["0"]["title"] == "R"


def test_no_registry_setting_falls_back_to_the_root_profile(tmp_path):
    _write(str(tmp_path / "modes_registry.json"), {"types": {}})
    _write(str(tmp_path / "modes_config.json"), LANDSCAPE)
    path, source = resolve_active_profile(str(tmp_path))
    assert source == "default" and path.endswith("modes_config.json")


# ---------------------------------------------------------------- switching

def test_switching_records_the_profile_and_returns_the_payload(project):
    result = switch_profile(str(project), "configs/modes_config_portrait.json", _registry(project))
    assert result.ok, (result.reason, result.errors)
    assert result.profile == "configs/modes_config_portrait.json"
    assert read_active_profile(str(project)) == "configs/modes_config_portrait.json"
    # the payload is what a restart would load, so the loop can switch over immediately
    assert sorted(result.payload["modes_config"]) == ["0", "1"]
    assert result.payload["modes_config"]["0"]["title"] == "P"
    assert result.payload["config_path"].endswith("modes_config_portrait.json")


def test_switching_is_refused_when_config_was_pinned_on_the_command_line(project):
    """--config outranks the record at every restart: say so instead of pretending."""
    result = switch_profile(str(project), "configs/modes_config_portrait.json", _registry(project),
                            config_override="modes_config.json")
    assert not result.ok
    assert "--config" in result.reason and "restart" in result.reason
    assert read_active_profile(str(project)) == "", "a refused switch must write nothing"


def test_switching_refuses_a_missing_or_non_profile_file(project):
    result = switch_profile(str(project), "configs/nope.json", _registry(project))
    assert not result.ok and "no such profile" in result.reason

    _write(str(project / "configs" / "not_a_profile.json"), {"something": "else"})
    result = switch_profile(str(project), "configs/not_a_profile.json", _registry(project))
    assert not result.ok and "no 'modes'" in result.reason
    assert read_active_profile(str(project)) == ""


def test_switching_refuses_a_profile_that_does_not_validate(project):
    """A broken profile must not be able to reach the wall through a switch."""
    broken = {"profile": {"label": "Broken"},
              "modes": {"0": {"type": "Gauge"}}}          # missing the required 'title'
    _write(str(project / "configs" / "broken.json"), broken)
    result = switch_profile(str(project), "configs/broken.json", _registry(project))
    assert not result.ok
    assert "does not validate" in result.reason
    assert any("missing required keys" in e for e in result.errors)
    assert read_active_profile(str(project)) == ""


def test_switching_warns_about_a_profile_with_warnings_but_still_switches(project):
    noisy = {"profile": {"label": "Noisy"},
             "modes": {"0": {"type": "Gauge", "title": "N", "typo_key": 1}}}
    _write(str(project / "configs" / "noisy.json"), noisy)
    result = switch_profile(str(project), "configs/noisy.json", _registry(project))
    assert result.ok, result.reason
    assert any("unknown key 'typo_key'" in w for w in result.warnings)
    assert read_active_profile(str(project)) == "configs/noisy.json"


def test_switching_back_to_the_registry_pick_is_possible(project):
    switch_profile(str(project), "configs/modes_config_portrait.json", _registry(project))
    result = switch_profile(str(project), "configs/from_registry.json", _registry(project))
    assert result.ok
    assert load_project_config(str(project))[2]["0"]["title"] == "R"


# ---------------------------------------------------------------- backups

def test_list_backups_is_newest_first_and_only_this_target(project):
    path = str(project / "modes_config.json")
    for value in (1, 2, 3):
        doc = json.loads(json.dumps(LANDSCAPE))
        doc["modes"]["0"]["font_size"] = value
        _write(path, doc)                                   # not through the editor: no backup yet
        from core.store import atomic_write_json
        atomic_write_json(path, doc, backup=True)

    other = str(project / "configs" / "modes_config_portrait.json")
    from core.store import atomic_write_json
    atomic_write_json(other, PORTRAIT, backup=True)

    backups = list_backups(path)
    assert len(backups) == 3, [b["name"] for b in backups]
    assert [b["stamp"] for b in backups] == sorted((b["stamp"] for b in backups), reverse=True)
    assert all("modes_config.json." in b["name"] and "portrait" not in b["name"] for b in backups)
    assert all(b["when"].count("-") == 2 for b in backups), "the stamp is rendered for a human"
    assert len(list_backups(other)) == 1


def test_restoring_a_backup_is_itself_undoable(project):
    path = str(project / "modes_config.json")
    from core.store import atomic_write_json
    atomic_write_json(path, {"profile": {"label": "OLD"}, "modes": {"0": {"type": "Gauge",
                                                                         "title": "old"}}},
                      backup=True)
    before_restore = sha256_file(path)
    backups = list_backups(path)
    assert len(backups) == 1

    result = restore_backup(path, backups[0]["path"], registry=_registry(project),
                            base_dir=str(project))
    assert result.ok, (result.reason, result.errors)
    assert json.load(open(path))["modes"]["0"]["title"] == "L", "the backup holds the older file"
    # the restore backed up the version it replaced, so it can be undone
    assert result.backup and os.path.exists(result.backup)
    assert sha256_file(result.backup) == before_restore
    assert len(list_backups(path)) == 2


def test_a_backup_that_no_longer_validates_is_not_restored(project):
    """A backup can predate a type change, so it is validated BEFORE it replaces anything."""
    path = str(project / "modes_config.json")
    before = sha256_file(path)
    stale = os.path.join(str(project), ".backups",
                         "modes_config.json.20200101T000000_000000Z.bak")
    _write(stale, {"profile": {}, "modes": {"0": {"type": "Gauge"}}})   # no 'title'

    result = restore_backup(path, stale, registry=_registry(project), base_dir=str(project))
    assert not result.ok and "does not validate" in result.reason
    assert any("missing required keys" in e for e in result.errors)
    assert sha256_file(path) == before, "a refused restore modified the file"


def test_restoring_something_that_is_not_a_profile_is_refused(project):
    path = str(project / "modes_config.json")
    junk = str(project / "junk.bak")
    _write(junk, {"hello": "world"})
    result = restore_backup(path, junk, registry=_registry(project), base_dir=str(project))
    assert not result.ok and "not a profile document" in result.reason
    assert not restore_backup(path, str(project / "missing.bak"), registry=_registry(project)).ok


# ---------------------------------------------------------------- raw document staging

def test_staging_a_whole_document_supersedes_per_mode_staging(project):
    editor = ProfileEditor(str(project), str(project / "modes_config.json"), _registry(project))
    editor.stage_set(0, "font_size", 99)
    assert editor.changed_modes() == [0]

    new_doc = json.loads(json.dumps(LANDSCAPE))
    new_doc["modes"]["0"]["font_size"] = 12
    new_doc["modes"]["5"] = {"type": "Gauge", "title": "added"}
    editor.stage_document(new_doc)

    assert editor.staged == {}, "the raw document replaces per-mode staging"
    assert editor.changed_modes() == [0, 5]
    assert "whole document was replaced" in editor.staged_summary()
    assert editor.is_dirty()


def test_a_staged_document_writes_through_the_same_validation(project):
    path = str(project / "modes_config.json")
    editor = ProfileEditor(str(project), path, _registry(project))
    broken = json.loads(json.dumps(LANDSCAPE))
    del broken["modes"]["0"]["title"]                       # required
    editor.stage_document(broken)
    result = editor.save()
    assert not result.ok and any("missing required keys" in e for e in result.errors)
    assert json.load(open(path))["modes"]["0"]["title"] == "L"

    editor2 = ProfileEditor(str(project), path, _registry(project))
    good = json.loads(json.dumps(LANDSCAPE))
    good["modes"]["0"]["font_size"] = 12
    editor2.stage_document(good)
    assert editor2.save().ok
    assert json.load(open(path))["modes"]["0"]["font_size"] == 12


def test_reverting_clears_a_staged_document(project):
    editor = ProfileEditor(str(project), str(project / "modes_config.json"), _registry(project))
    editor.stage_document({"modes": {"9": {"type": "Gauge", "title": "x"}}})
    assert editor.is_dirty()
    editor.revert_all()
    assert not editor.is_dirty() and editor.document_override is None
    assert editor.save().reason.startswith("nothing to save")


def test_staging_a_non_object_document_is_refused(project):
    editor = ProfileEditor(str(project), str(project / "modes_config.json"), _registry(project))
    with pytest.raises(EditorRefused):
        editor.stage_document([1, 2, 3])


# ---------------------------------------------------------------- the real tree

def test_the_real_project_can_switch_between_its_own_profiles(tmp_path):
    """Same code, the real configs: switch to portrait, then back, and the loader agrees."""
    root = tmp_path / "real"
    root.mkdir()
    for name in ("modes_registry.json", "modes_config.json"):
        shutil.copy2(os.path.join(REAL_ROOT, name), root / name)
    shutil.copytree(os.path.join(REAL_ROOT, "configs"), root / "configs")
    registry = json.load(open(root / "modes_registry.json"))["types"]

    landscape = load_project_config(str(root))
    assert len(landscape[2]) >= 9

    result = switch_profile(str(root), "configs/modes_config_portrait.json", registry)
    assert result.ok, (result.reason, result.errors)
    _, _, modes, path = load_project_config(str(root))
    assert path.endswith("modes_config_portrait.json")
    assert len(modes) == 26, f"portrait has 26 modes in the real project, got {len(modes)}"
    assert modes != landscape[2]

    back = switch_profile(str(root), "modes_config.json", registry)
    assert back.ok
    _, _, modes2, path2 = load_project_config(str(root))
    assert path2.endswith("modes_config.json") and modes2 == landscape[2]
