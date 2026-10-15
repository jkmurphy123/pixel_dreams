"""
The config-truth rules: validation (shared by the validator and the panel) and the "enabled"
flag (shared by the controller and the panel).

These are the rules that decide whether a config is allowed to be written, so they are tested
against the REAL tree as well as synthetic cases — the real tree is what the panel edits.
"""

from __future__ import annotations

import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import validate_configs                                # noqa: E402
from core.config import (                               # noqa: E402
    COMMON_INSTANCE_KEYS,
    NON_PARAM_KEYS,
    enabled_mode_indices,
    load_json,
)
from core.playlist import Playlist                      # noqa: E402
from core.validation import (                           # noqa: E402
    ERROR,
    Issue,
    errors,
    validate_instance,
    validate_profile,
    validate_registry,
    warnings,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {}).get("types", {})


@pytest.fixture(scope="module")
def registry():
    return {
        "slideshow": {
            "entrypoint": "modes.slideshow_mode:SlideshowMode",
            "required": ["folder"],
            "optional": ["interval"],
        },
        "statusticker": {
            "entrypoint": "modes.status_ticker_mode:StatusTickerMode",
            "required": [],
            "optional": ["file"],
        },
    }


# ---------------------------------------------------------------- registry rules

def test_registry_without_types_is_an_error():
    assert errors(validate_registry({"types": {}}))
    assert errors(validate_registry({}))


def test_entrypoint_problems_are_errors(registry):
    broken = {"a": {"entrypoint": "modes.slideshow_mode"},                  # no colon
              "b": {"entrypoint": "modes.nope:Missing"},                    # no such module
              "c": {"entrypoint": "modes.slideshow_mode:NoSuchClass"},      # no such class
              "d": {}}                                                     # no entrypoint
    found = validate_registry({"types": broken}, check_imports=True)
    assert len(errors(found)) == 4, [i.render() for i in found]


def test_a_normalised_key_round_trips_and_secrets_are_flagged():
    found = validate_registry({"types": {
        "StatusTicker": {"entrypoint": "modes.status_ticker_mode:StatusTickerMode"},
        "x": {"entrypoint": "modes.status_ticker_mode:StatusTickerMode",
              "type_config": {"api_key": "oops"}},
    }}, check_imports=True)
    messages = [i.message for i in warnings(found)]
    assert any("normalized form" in m for m in messages), messages
    assert any("secrets belong in secrets.json" in m for m in messages), messages


# ---------------------------------------------------------------- instance rules

def test_missing_type_and_unknown_type_are_errors(registry):
    assert errors(validate_instance(2, {}, registry))
    found = validate_instance(2, {"type": "Nonesuch"}, registry)
    assert errors(found) and "unknown type" in errors(found)[0].message


def test_missing_required_and_unknown_key(registry):
    found = validate_instance(3, {"type": "Slideshow", "interval": 10, "led_collor": 1}, registry)
    assert "missing required keys: ['folder']" in [i.message for i in errors(found)]
    assert "unknown key 'led_collor' (not in required/optional for this type)" in \
        [i.message for i in warnings(found)]


def test_structural_keys_are_never_unknown_keys(registry):
    """type/name/title/duration/enabled are the slot's own keys, not per-type parameters."""
    found = validate_instance(3, {"type": "Slideshow", "folder": "x", "name": "Art",
                                  "duration": 120, "enabled": False}, registry)
    assert not warnings(found), [i.render() for i in warnings(found)]


def test_a_non_boolean_enabled_is_a_warning_not_silence(registry):
    """`"enabled": "false"` must be surfaced, because the app treats it as ENABLED."""
    found = validate_instance(3, {"type": "Slideshow", "folder": "x", "enabled": "false"}, registry)
    assert any(i.key == "enabled" for i in warnings(found))


def test_missing_relative_data_file_warns(registry, tmp_path):
    found = validate_instance(1, {"type": "StatusTicker", "file": "nope.txt"}, registry,
                              base_dir=str(tmp_path))
    assert any("not found relative to project root" in i.message for i in warnings(found))
    # an absolute path is the operator's business, so it is not checked
    assert not validate_instance(1, {"type": "StatusTicker", "file": "/elsewhere/nope.txt"},
                                 registry, base_dir=str(tmp_path))


def test_issue_render_keeps_the_format_the_cli_has_always_printed():
    assert Issue(ERROR, "boom", mode_key="2", type_key="slideshow").render() == \
        "  ERROR: mode 2 (slideshow): boom"
    assert Issue("warning", "hmm", mode_key="2", type_key="slideshow").render() == \
        "  warn:  mode 2 (slideshow): hmm"
    assert Issue(ERROR, "registry level").render() == "  ERROR: registry level"
    assert Issue(ERROR, "type level", type_key="slideshow").render() == \
        "  ERROR: type 'slideshow': type level"


# ---------------------------------------------------------------- whole profile

def test_profile_with_no_modes_is_an_error():
    assert errors(validate_profile({}, REGISTRY))


def test_the_real_tree_validates_with_zero_errors():
    """The tree the panel edits. Warnings are allowed; errors are not."""
    for rel in ["modes_config.json"] + [
            os.path.join("configs", f) for f in sorted(os.listdir(os.path.join(BASE_DIR,
                                                                              "configs")))
            if f.endswith(".json")]:
        modes = load_json(os.path.join(BASE_DIR, rel), {}).get("modes", {})
        found = validate_profile(modes, REGISTRY, base_dir=BASE_DIR)
        assert not errors(found), [i.render() for i in errors(found)]


def test_the_cli_has_no_second_copy_of_the_rules():
    """
    Guard against drift: the panel and the validator must agree about what is valid, which is
    only true while there is exactly one implementation. This fails if the check messages get
    copied back into validate_configs.py.
    """
    source = inspect.getsource(validate_configs)
    for phrase in ("not in required/optional", "secrets belong in secrets.json",
                   "will never be loaded", "not found relative to project root"):
        assert phrase not in source, f"validate_configs.py has its own copy of: {phrase!r}"
    assert "core.validation" in source


# ---------------------------------------------------------------- the enabled flag

def test_enabled_indices_defaults_to_everything():
    indices, fell_back = enabled_mode_indices({"0": {}, "1": {}, "5": {}})
    assert indices == [0, 1, 5] and fell_back is False


def test_enabled_indices_drops_explicit_false_only():
    cfg = {"0": {}, "1": {"enabled": False}, "2": {"enabled": True}, "3": {"enabled": "false"}}
    indices, fell_back = enabled_mode_indices(cfg)
    # the string "false" is NOT a disable — it is a mistake, surfaced by validation instead
    assert indices == [0, 2, 3] and fell_back is False


def test_all_disabled_falls_back_to_everything_and_says_so():
    cfg = {"0": {"enabled": False}, "1": {"enabled": False}}
    indices, fell_back = enabled_mode_indices(cfg)
    assert indices == [0, 1] and fell_back is True


def test_enabled_indices_ignores_junk_keys():
    assert enabled_mode_indices({"0": {}, "notes": "hi"})[0] == [0]


def test_structural_and_non_param_key_sets_agree_where_they_should():
    # duration is a legitimate instance key AND a real parameter; enabled is legitimate but not
    assert "duration" in COMMON_INSTANCE_KEYS and "duration" not in NON_PARAM_KEYS
    assert "enabled" in COMMON_INSTANCE_KEYS and "enabled" in NON_PARAM_KEYS
    assert NON_PARAM_KEYS <= COMMON_INSTANCE_KEYS


# ---------------------------------------------------------------- playlist honours it

def test_playlist_skips_disabled_modes_and_wraps_within_them():
    pl = Playlist(6, shuffle=False, start_index=1, allowed=[1, 3, 5])
    assert pl.entries == [1, 3, 5]
    assert [pl.advance(1) for _ in range(4)] == [3, 5, 1, 3]


def test_playlist_starts_at_the_next_allowed_mode_when_the_start_is_disabled():
    pl = Playlist(6, shuffle=False, start_index=2, allowed=[1, 3, 5])
    assert pl.entries == [3, 5, 1]


def test_playlist_shuffle_keeps_the_requested_start_first():
    pl = Playlist(6, shuffle=True, start_index=3, allowed=[1, 3, 5])
    assert pl.entries[0] == 3 and sorted(pl.entries) == [1, 3, 5]


def test_playlist_with_no_allowed_candidates_still_serves_something():
    """A rotation that would IndexError kills the render loop; serving the start is safer."""
    assert Playlist(6, start_index=4, allowed=[]).entries == [4]


def test_playlist_allowed_none_is_the_old_behaviour():
    assert Playlist(4, start_index=0).entries == [0, 1, 2, 3]
    assert Playlist(4, start_index=2).entries == [2, 3, 0, 1]


def test_single_playlist_ignores_the_enabled_flag():
    """--play N is an explicit request: a disabled mode still plays when asked for by name."""
    pl = Playlist.single(7)
    assert pl.entries == [7] and pl.current == 7
