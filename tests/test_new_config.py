"""
New config: create a profile holding every mode the registry knows.

Two halves. The first drives `build_full_profile` / `create_profile` directly, because the RULES are
the deliverable here — which types appear, what each one is seeded with, and what happens to a mode
the registry declares but cannot be filled. The second drives the page and the endpoint, because a
button that names a file for you is exactly the kind of thing that quietly writes somewhere you did
not mean.
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
from nicegui import ui

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.editor import build_full_profile, create_profile, safe_profile_name   # noqa: E402
from core.profiles import discover_profiles                                     # noqa: E402
from core.validation import validate_profile                                    # noqa: E402
from panel.app import PageContext, register_pages                               # noqa: E402

from test_panel_wiring import _env, _read, _sandbox, _spawn, _stop, _wait_ready  # noqa: E402
from test_transport import _bus, _click, _marked, _panel                        # noqa: E402

TOKEN = "new-config-token"

#: A registry with one type per interesting case: nothing required, required keys with usable
#: defaults, a required key whose default is empty, and a required key with no schema at all.
REGISTRY = {
    "settings": {"modes_config_file": "modes_config.json"},
    "types": {
        "alpha": {"entrypoint": "modes.system_information_mode:SystemInformationMode",
                  "required": [], "optional": ["font_size"],
                  "params": {"font_size": {"widget": "number", "default": 24}}},
        "beta": {"entrypoint": "modes.system_information_mode:SystemInformationMode",
                 "required": ["folder", "duration"], "optional": [],
                 "params": {"folder": {"default": "/mnt/ssd/projects/images"},
                            "duration": {"default": 30}}},
        "gamma": {"entrypoint": "modes.system_information_mode:SystemInformationMode",
                  "required": ["file"], "optional": [],
                  "params": {"file": {"default": ""}}},
        "delta": {"entrypoint": "modes.system_information_mode:SystemInformationMode",
                  "required": ["thing"], "optional": [], "params": {}},
    },
}

SEED = {
    "0": {"type": "Alpha", "font_size": 40, "name": "tuned alpha"},
    "1": {"type": "beta", "folder": "/home/ubuntu/pics", "duration": 99},
}


def _project(tmp_path, registry=None, seed=None):
    """A sandbox project: no modes/ modules needed, only the registry and the profiles."""
    root = tmp_path / "proj"
    (root / "configs").mkdir(parents=True, exist_ok=True)
    (root / "modes_registry.json").write_text(json.dumps(registry or REGISTRY, indent=2) + "\n")
    (root / "modes_config.json").write_text(
        json.dumps({"modes": seed if seed is not None else SEED}, indent=2) + "\n")
    return str(root)


# ---------------------------------------------------------------- the rules

def test_a_new_config_contains_every_type_the_registry_knows():
    modes, report = build_full_profile(REGISTRY, SEED)
    assert list(modes) == ["0", "1", "2"], "slots are contiguous from 0"
    assert [m["type"] for m in modes.values()] == ["Alpha", "beta", "gamma"], \
        "registry order, with the seed's own spelling kept for the types it defines"
    assert report["types"] == ("alpha", "beta", "gamma")
    assert report["left_out"] == (("delta", ("thing",)),), \
        "the one type that could not be filled is named, not silently dropped"


def test_the_seeds_tuned_values_are_carried_over_verbatim():
    """
    This is what makes a new orientation start from the work already done. Copied as it stands —
    including the seed's capitalisation and any extra keys (`name` here), not normalised to the
    registry's spelling.
    """
    modes, report = build_full_profile(REGISTRY, SEED)
    assert modes["0"] == {"type": "Alpha", "font_size": 40, "name": "tuned alpha"}
    assert modes["1"]["folder"] == "/home/ubuntu/pics" and modes["1"]["duration"] == 99
    assert report["inherited"] == ("alpha", "beta")
    assert report["at_defaults"] == ("gamma",)


def test_the_types_mapping_and_the_registry_document_give_the_same_answer():
    """The panel hands out `types`, the file on disk is the document; both must work."""
    mapping = build_full_profile(REGISTRY["types"], SEED)[0]
    document = build_full_profile(REGISTRY, SEED)[0]
    assert mapping == document


def test_required_keys_are_filled_from_the_recorded_defaults():
    modes, _ = build_full_profile(REGISTRY, None)          # no seed at all
    assert modes["1"] == {"type": "beta", "folder": "/mnt/ssd/projects/images", "duration": 30}
    assert modes["0"] == {"type": "alpha"}, \
        "a type with nothing required is written bare — optional keys stay unset"
    assert "font_size" not in modes["0"], "unset means the mode decides, not us"


def test_a_required_key_with_no_default_leaves_its_type_out_and_names_it():
    """
    `delta.thing` cannot be filled honestly: there is no recorded default and guessing one from the
    key's name is exactly what the parameter layer refuses to do. So the type is not written, and
    the report says which type and which keys — a silent omission would be the worse answer.
    """
    modes, report = build_full_profile(REGISTRY, None)
    assert "delta" not in [m["type"] for m in modes.values()]
    assert report["left_out"] == (("delta", ("thing",)),)
    assert [m["type"] for m in modes.values()] == ["alpha", "beta", "gamma"]


def test_an_empty_default_is_written_but_flagged_as_needing_a_value():
    modes, report = build_full_profile(REGISTRY, None)
    assert modes["2"] == {"type": "gamma", "file": ""}, \
        "the key must be present or the profile does not validate"
    assert report["placeholders"] == ("gamma.file",)


def test_a_left_out_type_does_not_contribute_a_placeholder():
    """
    Regression: the first version collected placeholders while building an entry, so
    'headlinesnews.feed_url is empty' could be reported for a type that was then dropped from the
    file — pointing at something that does not exist.
    """
    registry = {
        "settings": {"modes_config_file": "modes_config.json"},
        "types": {
            "alpha": {"entrypoint": "e", "required": [], "optional": [], "params": {}},
            "beta": {"entrypoint": "e", "required": ["empty_one", "no_default"], "optional": [],
                     "params": {"empty_one": {"default": ""}}},
        },
    }
    modes, report = build_full_profile(registry, None)
    assert report["left_out"] == (("beta", ("no_default",)),)
    assert report["placeholders"] == (), "beta was left out, so its empty key is not in the file"
    assert [m["type"] for m in modes.values()] == ["alpha"]


def test_the_tuned_value_the_seed_has_for_a_required_key_is_used_not_the_default():
    modes, _ = build_full_profile(REGISTRY, SEED)
    assert modes["1"]["folder"] == "/home/ubuntu/pics"
    assert modes["1"]["duration"] == 99


@pytest.mark.parametrize("name", ["../evil.json", "a/b.json", "", "   ", ".hidden", "new config.json",
                                 "tilde~.json", "x" * 120])
def test_unsafe_names_are_refused_with_the_reason(name):
    filename, problem = safe_profile_name(name)
    assert filename == "" and problem, f"{name!r} should have been refused"


@pytest.mark.parametrize("name,expected", [
    ("livingroom", "livingroom.json"),
    ("modes_config_livingroom", "modes_config_livingroom.json"),
    ("modes_config_livingroom.json", "modes_config_livingroom.json"),
    ("  spaced  ", "spaced.json"),
])
def test_acceptable_names_are_normalised(name, expected):
    assert safe_profile_name(name) == (expected, "")


# ---------------------------------------------------------------- the create itself

def test_create_writes_a_file_that_validates(tmp_path):
    root = _project(tmp_path)
    result = create_profile(root, "modes_config_all", REGISTRY, inherit_from="modes_config.json")
    assert result.ok and result.rel == os.path.join("configs", "modes_config_all.json")
    assert result.modes == 3 and result.seed == "modes_config.json"

    doc = json.loads(open(result.path).read())
    assert list(doc) == ["modes"], "a minimal profile document, like every other one here"
    assert not [i for i in validate_profile(doc["modes"], REGISTRY["types"], base_dir=root)
                if i.is_error]
    assert discover_profiles(root), "the new file must be discovered by the panel's list"


def test_create_is_deterministic(tmp_path):
    root = _project(tmp_path)
    a = create_profile(root, "one", REGISTRY, inherit_from="modes_config.json")
    b = create_profile(root, "two", REGISTRY, inherit_from="modes_config.json")
    assert a.ok and b.ok
    assert open(a.path, "rb").read() == open(b.path, "rb").read()
    assert a.sha256 == b.sha256


def test_create_refuses_to_overwrite_and_writes_nothing(tmp_path):
    root = _project(tmp_path)
    first = create_profile(root, "keepme", REGISTRY)
    before = open(first.path, "rb").read()
    again = create_profile(root, "keepme", REGISTRY, inherit_from="modes_config.json")
    assert again.ok is False and "already exists" in again.reason
    assert open(first.path, "rb").read() == before, "the existing file was touched"


def test_create_refuses_an_unsafe_name_without_touching_the_tree(tmp_path):
    root = _project(tmp_path)
    result = create_profile(root, "../../modes_registry.json", REGISTRY)
    assert result.ok is False and not result.path
    assert json.load(open(os.path.join(root, "modes_registry.json"))).get("types"), \
        "the registry is still there"


def test_create_without_a_seed_gives_registry_defaults(tmp_path):
    root = _project(tmp_path)
    result = create_profile(root, "bare", REGISTRY)
    modes = json.load(open(result.path))["modes"]
    assert modes["1"] == {"type": "beta", "folder": "/mnt/ssd/projects/images", "duration": 30}
    assert result.inherited == () and result.seed == ""


def test_create_with_switch_records_the_new_profile(tmp_path):
    root = _project(tmp_path)
    result = create_profile(root, "switched", REGISTRY, switch=True)
    assert result.ok and result.switched is not None and result.switched.ok
    record = json.load(open(os.path.join(root, "runtime", "active_profile.json")))
    assert record["profile"] == os.path.join("configs", "switched.json"), record


def test_create_succeeds_but_reports_a_refused_switch_when_the_app_is_pinned(tmp_path):
    """
    --config outranks the recorded profile at every restart. The FILE is still created (that is
    what was asked for); only the switch is refused, and the result says so rather than claiming
    success.
    """
    root = _project(tmp_path)
    result = create_profile(root, "pinned", REGISTRY, switch=True,
                            config_override="modes_config.json")
    assert result.ok is True
    assert os.path.exists(result.path)
    assert result.switched is not None and result.switched.ok is False
    assert "--config" in result.switched.reason


# ---------------------------------------------------------------- the real registry

def test_the_real_registry_yields_a_valid_profile_with_the_leftovers_named(tmp_path):
    """
    The real thing: 53 types, one real profile as the seed. Asserts the shape of the answer and,
    importantly, that every type is either IN the file or NAMED in the report — nothing vanishes
    quietly.
    """
    real = os.path.dirname(BASE_DIR)
    registry = json.load(open(os.path.join(BASE_DIR, "modes_registry.json")))
    seed = json.load(open(os.path.join(BASE_DIR, "modes_config.json")))["modes"]

    modes, report = build_full_profile(registry, seed)
    assert len(modes) == 49 and len(registry["types"]) == 53
    assert len(report["left_out"]) == 4
    assert {t for t, _ in report["left_out"]} == {"headlinesnews", "animatedcityrain",
                                                  "chatreplay", "antfarm"}
    assert not [i for i in validate_profile(modes, registry["types"], base_dir=BASE_DIR) if i.is_error]
    assert set(report["types"]) | {t for t, _ in report["left_out"]} == set(registry["types"]), \
        "every registry type is either included or explained"

    # and it can actually be created somewhere harmless
    result = create_profile(root := _project(tmp_path, registry=registry, seed=seed),
                            "modes_config_all_orientations", registry,
                            inherit_from=os.path.join(BASE_DIR, "modes_config.json"))
    assert result.ok and result.modes == 49
    assert os.path.exists(result.path), root


# ---------------------------------------------------------------- the page and the endpoint

def _ui_project(tmp_path):
    return _project(tmp_path)


async def test_clicking_create_writes_the_file_reports_it_and_lists_it(tmp_path):
    root = _ui_project(tmp_path)
    ctx = PageContext(base_dir=root, bus=_bus(display="fullscreen", mode_index=0, single_mode=False,
                                             applied_rotation=[0], pending_steps=0),
                      bind="127.0.0.1")
    async with _panel(ctx) as p:
        await p.user.open("/")
        await p.user.should_see("New config")
        name = _marked(p, "new-config-name")
        name.value = "modes_config_livingroom"
        _click(_marked(p, "new-config-create"))

        created = os.path.join(root, "configs", "modes_config_livingroom.json")
        assert os.path.exists(created), "the button did not write the file"
        outcome = _marked(p, "new-config-outcome")
        assert "Created" in outcome.text and "3 modes" in outcome.text.replace("\n", " ")
        assert "carried over from modes_config.json" in outcome.text
        assert "gamma.file" in outcome.text, "the empty value must be called out"
        assert "delta" in outcome.text, "and the type that could not be created"
        assert "configs/modes_config_livingroom.json" in str(
            _marked(p, "profile-select").options), "the list must contain the new file"


async def test_clicking_create_twice_refuses_the_second_time(tmp_path):
    root = _ui_project(tmp_path)
    ctx = PageContext(base_dir=root, bus=_bus(display="fullscreen", mode_index=0, single_mode=False,
                                             applied_rotation=[0], pending_steps=0),
                      bind="127.0.0.1")
    async with _panel(ctx) as p:
        await p.user.open("/")
        _marked(p, "new-config-name").value = "twice"
        _click(_marked(p, "new-config-create"))
        path = os.path.join(root, "configs", "twice.json")
        before = open(path, "rb").read()

        _click(_marked(p, "new-config-create"))
        outcome = _marked(p, "new-config-outcome")
        assert "Refused" in outcome.text and "already exists" in outcome.text
        assert open(path, "rb").read() == before


async def test_the_switch_checkbox_switches_the_display(tmp_path):
    root = _ui_project(tmp_path)
    bus = _bus(display="fullscreen", mode_index=0, single_mode=False, applied_rotation=[0],
               pending_steps=0)
    ctx = PageContext(base_dir=root, bus=bus, bind="127.0.0.1")
    async with _panel(ctx) as p:
        await p.user.open("/")
        _marked(p, "new-config-name").value = "switchme"
        _marked(p, "new-config-switch").value = True
        _click(_marked(p, "new-config-create"))

    assert os.path.exists(os.path.join(root, "configs", "switchme.json"))
    commands = [c for c in bus.drain() if c.get("cmd") == "apply_config"]
    assert commands, "a checked 'switch to it' must tell the render loop about the new profile"


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
        return e.code, json.loads(e.read() or b"{}")


def test_the_endpoint_creates_and_can_switch(tmp_path):
    """
    Process-level, with the real controller.

    The sandbox's own registry is used (its mode class is a real, importable one) extended with a
    second type pointing at the same class, so the generated profile contains a mode the app can
    actually build — and one whose required key is empty, which is the placeholder path. Then the app
    is made to PLAY the new profile: a generated config whose modes it cannot build would be a poor
    deliverable, and "the file exists" would not have caught that.
    """
    root = _sandbox(tmp_path, secrets={"panel_token": TOKEN})
    registry = json.loads((root / "modes_registry.json").read_text())
    registry["types"]["tiny2"] = {"entrypoint": "modes.tiny_mode:TinyMode",
                                  "required": ["folder"], "optional": ["font_size"],
                                  "params": {"folder": {"default": ""}}}
    (root / "modes_registry.json").write_text(json.dumps(registry, indent=2) + "\n")

    port = _free_port()
    proc, log = _spawn(root, tmp_path, "newcfg.log", "--panel-port", str(port),
                       "--panel-bind", "127.0.0.1", env=_env())
    url = f"http://127.0.0.1:{port}"
    try:
        assert _wait_ready(url + "/api/status", proc, log), _read(log)

        code, body = _post(url, "/api/profile/new", {"name": "modes_config_all", "inherit": True,
                                                     "switch": True})
        assert code == 200 and body["ok"], body
        assert body["modes"] == 2, body
        assert body["carried_over"] == ["tiny"], "the profile's own mode came across"
        assert body["at_registry_defaults"] == ["tiny2"]
        assert body["needs_a_value"] == ["tiny2.folder"], "an empty default is reported, not hidden"
        assert body["left_out"] == []
        assert body["switched"] is True
        assert os.path.exists(os.path.join(root, "configs", "modes_config_all.json"))

        # the running app was switched to it and can build both modes. Polled, because the loop
        # applies a bus payload on its next frame: reading once here measures the OLD rotation (the
        # same trap as reading mode_index straight after /api/step).
        req = urllib.request.Request(url + "/api/status")
        req.add_header("X-Panel-Token", TOKEN)
        deadline = time.time() + 10
        status = {}
        while time.time() < deadline:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = json.loads(resp.read())["status"]
            if status.get("applied_rotation") == [0, 1]:
                break
            time.sleep(0.2)
        assert status["applied_rotation"] == [0, 1], status.get("applied_rotation")
        assert "modes_config_all.json" in status["applied_config_path"]

        # and it actually plays them
        _post(url, "/api/step", {"delta": 1})
        deadline = time.time() + 10
        while time.time() < deadline:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if json.loads(resp.read())["status"]["mode_index"] == 1:
                    break
            time.sleep(0.2)
        assert proc.poll() is None, "the app died playing a generated config"

        # refuse the same name a second time, and stay alive
        code2, body2 = _post(url, "/api/profile/new", {"name": "modes_config_all"})
        assert code2 == 409 and "already exists" in body2["reason"]
        assert proc.poll() is None
    finally:
        _stop(proc)
