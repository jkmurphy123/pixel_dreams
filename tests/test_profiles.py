# tests/test_profiles.py
#
# Profile discovery + override merging: the read-only backend the panel lists from.
# No display, no pygame, no NiceGUI needed.

import json
import os
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.profiles import (  # noqa: E402
    ModeEntry,
    derive_label,
    discover_profiles,
    load_local_overrides,
    merge_local_override,
    mode_entries,
    profile_modes,
    resolve_active_profile,
)


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


# ---------------------------------------------------------------- label derivation

@pytest.mark.parametrize("filename,expected", [
    ("modes_config.json", "default"),
    ("modes_config_portrait.json", "portrait"),
    ("modes_config.basic.json", "basic"),
    ("modes_config_narrow_horz.json", "narrow horz"),
    ("modes_config_narrow_vert.json", "narrow vert"),
    ("modes_config_jetson.json", "jetson"),
])
def test_label_derivation(filename, expected):
    assert derive_label(filename) == expected


# ---------------------------------------------------------------- discovery (real project)

def test_real_project_profiles_discovered():
    """The live tree: root profile + every configs/*.json, all parseable."""
    active_path, source = resolve_active_profile(BASE_DIR)
    profiles = discover_profiles(BASE_DIR, active_path)

    assert len(profiles) >= 8, [p.name for p in profiles]
    names = [p.name for p in profiles]
    assert "modes_config.json" in names
    for expected in ("modes_config_portrait.json", "modes_config_landscape.json",
                     "modes_config_narrow_horz.json", "modes_config_narrow_vert.json",
                     "modes_config_jetson.json", "modes_config_windows.json",
                     "modes_config.basic.json"):
        assert expected in names, f"{expected} missing from {names}"

    for p in profiles:
        assert os.path.isabs(p.path)
        assert p.mode_count > 0, f"{p.name} reported no modes"
        assert p.error == "", f"{p.name} reported an error: {p.error}"
        assert p.rel == os.path.relpath(p.path, BASE_DIR)

    # Exactly one profile is flagged active, and it is the one the app would use.
    actives = [p for p in profiles if p.active]
    assert len(actives) == 1, [p.name for p in actives]
    assert os.path.realpath(actives[0].path) == os.path.realpath(active_path)
    assert source in ("cli", "registry", "default")


def test_real_profiles_have_distinct_mode_sets():
    """
    Mode numbers are slot numbers per profile, not global identities — the panel must
    never assume a mode number exists in another profile. Measured on the real tree.
    """
    landscape, _ = profile_modes(os.path.join(BASE_DIR, "configs", "modes_config_landscape.json"))
    portrait, _ = profile_modes(os.path.join(BASE_DIR, "configs", "modes_config_portrait.json"))
    assert set(landscape) & set(portrait), "expected overlapping slot numbers"
    assert set(landscape) != set(portrait), "expected different mode SETS between profiles"


# ---------------------------------------------------------------- discovery (synthetic)

def test_malformed_profile_is_reported_not_raised(tmp_path):
    _write(tmp_path / "modes_config.json", {"modes": {"0": {"type": "a"}}})
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "modes_config_broken.json").write_text("{ this is not json")

    profiles = {p.name: p for p in discover_profiles(str(tmp_path))}
    assert profiles["modes_config.json"].mode_count == 1
    assert profiles["modes_config.json"].error == ""
    assert profiles["modes_config_broken.json"].error != ""
    assert profiles["modes_config_broken.json"].mode_count == 0


def test_profile_metadata_block_is_display_only(tmp_path):
    _write(tmp_path / "configs" / "modes_config_portrait.json", {
        "profile": {"label": "Portrait 1080x1920 wall", "resolution": [1080, 1920],
                    "notes": "kitchen"},
        "modes": {"3": {"type": "slideshow"}},
    })
    info = next(p for p in discover_profiles(str(tmp_path)) if p.name.endswith("portrait.json"))
    assert info.label == "Portrait 1080x1920 wall"
    assert info.resolution == "1080x1920"
    assert info.notes == "kitchen"

    # The block must not leak into the mode list.
    entries = mode_entries(profile_modes(info.path)[0])
    assert [e.number for e in entries] == [3]


def test_absent_profiles_directory_is_not_an_error(tmp_path):
    _write(tmp_path / "modes_config.json", {"modes": {"0": {"type": "a"}}})
    profiles = discover_profiles(str(tmp_path))
    assert [p.name for p in profiles] == ["modes_config.json"]


# ---------------------------------------------------------------- mode entries

def test_mode_entries_are_sorted_and_carry_params():
    modes = {
        "10": {"type": "Slideshow", "name": "Cyberart", "folder": "/x", "duration": 120},
        "2": {"type": "StatusTicker", "title": "Ticker", "pause": 3.5},
    }
    entries = mode_entries(modes)
    assert [e.number for e in entries] == [2, 10]
    assert entries[0].type_key == "statusticker"
    assert entries[0].label == "Ticker"
    assert entries[1].params == {"folder": "/x", "duration": 120}   # 'name' is not a param
    assert all("type" not in e.params for e in entries)


def test_mode_entries_skip_non_numeric_and_non_dict():
    entries = mode_entries({"0": {"type": "a"}, "notes": {"type": "b"}, "7": "nope"})
    assert [e.number for e in entries] == [0]


# ---------------------------------------------------------------- local override layer

def test_merge_local_override_reports_shadowed_keys():
    modes = {"5": {"type": "slideshow", "folder": "/base", "duration": 60}}
    local = {"5": {"folder": "/host-specific", "font_size": 96}}
    merged, overridden = merge_local_override(modes, local)

    assert merged["5"]["folder"] == "/host-specific"       # override wins
    assert merged["5"]["duration"] == 60                   # untouched key preserved
    assert merged["5"]["font_size"] == 96                  # override can add a key
    assert overridden == {"5": ["folder", "font_size"]}     # and we can SAY which keys
    assert modes["5"]["folder"] == "/base"                 # input not mutated


def test_merge_local_override_can_add_a_whole_mode():
    merged, overridden = merge_local_override({}, {"9": {"type": "dungeon"}})
    assert merged["9"] == {"type": "dungeon"}
    assert overridden == {"9": ["type"]}


def test_load_local_overrides_missing_file(tmp_path):
    assert load_local_overrides(str(tmp_path)) == {}


def test_overridden_keys_reach_mode_entries(tmp_path):
    """A profile edit that the override shadows must be visible to the panel."""
    base = {"modes": {"4": {"type": "slideshow", "font_size": 192, "folder": "/base"}}}
    _write(tmp_path / "modes_config.json", base)
    _write(tmp_path / "modes_config.local.json", {"modes": {"4": {"folder": "/override"}}})

    modes, _ = profile_modes(str(tmp_path / "modes_config.json"))
    merged, overridden = merge_local_override(modes, load_local_overrides(str(tmp_path)))
    entries = mode_entries(merged, overridden)

    assert len(entries) == 1
    assert entries[0].override_keys == ("folder",)
    assert entries[0].params["folder"] == "/override"
    assert entries[0].params["font_size"] == 192


# ---------------------------------------------------------------- active resolution

def test_resolve_active_profile_precedence(tmp_path):
    _write(tmp_path / "configs" / "modes_config_portrait.json", {"modes": {"0": {"type": "a"}}})
    _write(tmp_path / "modes_config.json", {"modes": {"0": {"type": "b"}}})
    _write(tmp_path / "modes_registry.json", {"settings": {"modes_config_file": "configs/modes_config_portrait.json"}})

    path, source = resolve_active_profile(str(tmp_path))
    assert source == "registry"
    assert os.path.realpath(path) == os.path.realpath(str(tmp_path / "configs" / "modes_config_portrait.json"))

    # A CLI override outranks the registry setting (same precedence as the controller).
    path, source = resolve_active_profile(str(tmp_path), config_override="modes_config.json")
    assert source == "cli"
    assert path.endswith("modes_config.json")


def test_resolve_active_profile_default_without_registry_setting(tmp_path):
    _write(tmp_path / "modes_registry.json", {"types": {}})
    path, source = resolve_active_profile(str(tmp_path))
    assert source == "default"
    assert path.endswith("modes_config.json")
