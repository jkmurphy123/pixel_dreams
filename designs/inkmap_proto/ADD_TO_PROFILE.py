#!/usr/bin/env python3
"""Phase 1: land the ink-map mode in the ACTIVE profile, DISABLED, through the app's own writer.

Writes nothing unless the editor's own validation passes, and every write keeps a timestamped
backup. Run from the repo root:

  SDL_VIDEODRIVER=dummy .venv/bin/python designs/inkmap_proto/ADD_TO_PROFILE.py [--profile REL]

Defaults to the profile named by runtime/active_profile.json -- the one on the wall -- and only
ever ADDS a disabled slot, so nothing already playing changes.
"""
import argparse
import copy
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from core.config import load_json                     # noqa: E402
from core.editor import ProfileEditor                 # noqa: E402


def active_profile() -> str:
    record = load_json(os.path.join(BASE, "runtime", "active_profile.json"), {})
    return str(record.get("profile") or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None)
    args = ap.parse_args()

    rel = args.profile or active_profile()
    if not rel:
        print("no active profile recorded and none given; nothing written")
        return 1
    path = os.path.join(BASE, rel)
    print(f"profile: {rel}")

    registry = load_json(os.path.join(BASE, "modes_registry.json"), {})["types"]
    editor = ProfileEditor(BASE, path, registry)
    doc = copy.deepcopy(editor.document)
    modes = doc.setdefault("modes", {})

    already = [k for k, v in modes.items() if isinstance(v, dict) and v.get("type") == "inkmap"]
    if already:
        print(f"already present in slot(s) {already}; nothing written")
        return 0

    used = {int(k) for k in modes if str(k).isdigit()}
    slot = next(n for n in range(0, (max(used) if used else -1) + 2) if n not in used)
    modes[str(slot)] = {"type": "inkmap", "name": "Ink Map", "enabled": False, "seed": 0}
    print(f"adding slot {slot} ({len(modes)} modes total), disabled")

    editor.stage_document(doc)
    check = editor.validate()
    if not check.ok:
        print("REFUSED by the editor's validation:")
        for line in check.messages(limit=20):
            print("   ", line)
        return 1

    result = editor.save()
    if not result.ok:
        print(f"NOT WRITTEN: {result.reason}")
        return 1
    print(f"written: {result.reason}")
    if editor.last_backup:
        print(f"backup: {editor.last_backup}")

    after = load_json(path, {})
    entry = after.get("modes", {}).get(str(slot), {})
    print(f"read back from disk: {json.dumps(entry)}")
    assert entry.get("type") == "inkmap"
    assert entry.get("enabled") is False, "it must land DISABLED"
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
