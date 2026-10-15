#!/usr/bin/env python3
# scripts/scaffold_param_schema.py
#
# Draft the `params` schema for every mode type from the modes' own code, then (optionally)
# merge it into modes_registry.json.
#
# Usage:
#   python scripts/scaffold_param_schema.py                    # report only, writes nothing
#   python scripts/scaffold_param_schema.py --json draft.json  # dump the draft
#   python scripts/scaffold_param_schema.py --apply            # merge into the registry
#   python scripts/scaffold_param_schema.py --apply --fix-optional   # + declare drift keys
#   python scripts/scaffold_param_schema.py --check            # exit 1 if a type has no schema
#
# --apply is additive and idempotent: existing schema entries are never overwritten (your
# hand-written bounds/labels survive), and a second run changes nothing. Every write goes
# through core.store (temp + fsync + atomic replace + hash verify), with a backup.
#
# See designs/PIXEL_DREAMS_DESIGN.md §6.4 and designs/PHASE_02_*.md.

import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.config import load_json                                    # noqa: E402
from core.profiles import profile_modes                              # noqa: E402
from core.schema_scaffold import analyse, build_draft, merge_into_registry  # noqa: E402
from core.store import atomic_write_json                             # noqa: E402

REGISTRY_NAME = "modes_registry.json"
PROFILE_GLOBS = ("modes_config.json", "configs")


def load_all_profiles(base_dir: str) -> list:
    """Every profile's modes dict (root + configs/*.json), for the shape analysis."""
    paths = []
    root = os.path.join(base_dir, "modes_config.json")
    if os.path.exists(root):
        paths.append(root)
    configs = os.path.join(base_dir, PROFILE_GLOBS[1])
    if os.path.isdir(configs):
        paths.extend(sorted(os.path.join(configs, f) for f in os.listdir(configs)
                            if f.endswith(".json")))
    modes = []
    for path in paths:
        profile, _meta = profile_modes(path)
        if profile:
            modes.append(profile)
    return modes


def print_report(analysis: dict, draft: dict) -> None:
    totals = analysis["totals"]
    print("[Scaffold] Types analysed:", totals["types"])
    print("[Scaffold] Types whose module could not be read:", totals["types_without_module"])
    print("[Scaffold] Code-read keys missing from 'required'/'optional' (drift):",
          totals["drift_keys"])
    print("[Scaffold] Keys the mode computes at runtime (derived candidates):",
          totals["derived_candidates"])
    print("[Scaffold] Declared keys no profile sets (the form must still offer them):",
          totals["declared_absent_keys"])
    print("[Scaffold] Keys whose code type contradicts the name heuristic:",
          totals["widget_conflicts"])

    print("\n[Scaffold] Draft entries:", sum(len(v) for v in draft.values()), "across",
          len(draft), "types")

    print("\n[Scaffold] Drift detail (code reads it, registry never declares it):")
    for type_key, info in sorted(analysis["types"].items()):
        if info["drift"]:
            print(f"   {type_key}: {', '.join(info['drift'])}")

    print("\n[Scaffold] Derived candidates (config value is a hint, mode overrides it):")
    for type_key, info in sorted(analysis["types"].items()):
        if info["derived"]:
            print(f"   {type_key}: {', '.join(info['derived'])}")

    print("\n[Scaffold] Widget contradictions the code resolves:")
    for type_key, info in sorted(analysis["types"].items()):
        for key, conflict in sorted(info["absent_widget_conflicts"].items()):
            print(f"   {type_key}.{key}: name heuristic says {conflict['inferred']}, "
                  f"code says {conflict['from_code']}")

    choices, suggestions = [], []
    for type_key, entries in sorted(draft.items()):
        for key, piece in entries.items():
            if "choices" in piece:
                choices.append(f"{type_key}.{key} = {piece['choices']}")
            elif "suggestions" in piece:
                suggestions.append(f"{type_key}.{key} = {piece['suggestions']}")
    if choices:
        print(f"\n[Scaffold] Closed value sets recorded as drop-down choices ({len(choices)}):")
        for line in choices:
            print("   ", line)
    if suggestions:
        print(f"\n[Scaffold] Open-ended evidence recorded as suggestions ({len(suggestions)}) —")
        print("           the field stays free text; promote one to 'choices' by hand when you")
        print("           know the set is closed:")
        for line in suggestions:
            print("   ", line)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draft the params schema from mode code")
    parser.add_argument("--apply", action="store_true",
                        help="merge the draft into modes_registry.json (additive)")
    parser.add_argument("--fix-optional", action="store_true",
                        help="with --apply: add drift keys to each type's 'optional' list")
    parser.add_argument("--json", metavar="FILE", default=None,
                        help="write the draft to FILE for review")
    parser.add_argument("--all-keys", action="store_true",
                        help="emit an explicit entry for every key (freezes today's inference)")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if any type has no params schema at all")
    parser.add_argument("--registry", default=os.path.join(BASE_DIR, REGISTRY_NAME),
                        help="registry file to read (and to --apply to)")
    args = parser.parse_args((argv or sys.argv)[1:])

    registry_path = os.path.abspath(args.registry)
    registry_json = load_json(registry_path, {})
    if not registry_json.get("types"):
        print(f"[Scaffold] No types in {registry_path}")
        return 1

    profiles_modes = load_all_profiles(BASE_DIR)
    draft, analysis = build_draft(BASE_DIR, registry_json["types"], profiles_modes,
                                  include_all_keys=args.all_keys)
    print_report(analysis, draft)

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(draft, fh, indent=2)
            fh.write("\n")
        print(f"\n[Scaffold] Draft written to {args.json}")

    if args.apply:
        drift_keys = {t: i["drift"] for t, i in analysis["types"].items()}
        report = merge_into_registry(registry_json, draft, drift_keys=drift_keys,
                                     fix_optional=args.fix_optional)
        result = atomic_write_json(registry_path, registry_json, backup=True)
        added = sum(len(v) for v in report["added_params"].values())
        optional = sum(len(v) for v in report["added_optional"].values())
        print(f"\n[Scaffold] Merged: {added} schema keys, {optional} optional-list keys")
        print(f"[Scaffold] Wrote {result['path']} sha256={result['sha256'][:12]} "
              f"backup={os.path.basename(result['backup']) if result['backup'] else 'none'}")
        print("[Scaffold] Re-run validate_configs.py --all to confirm the configs still pass")

    if args.check:
        typed = set(draft)
        all_types = set(registry_json.get("types", {}))
        missing = sorted(all_types - typed)
        if missing:
            print(f"\n[Scaffold] CHECK FAILED: {len(missing)} type(s) have no schema entry:")
            for t in missing:
                print("   ", t)
            return 1
        print("\n[Scaffold] CHECK OK: every type has at least one schema entry")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
