#!/usr/bin/env python3
# scripts/audit_params.py
#
# The parameter exposure audit (design §10 Phase 5): find appearance values that are not parameters
# yet, so they can be reviewed before anything changes.
#
#   python scripts/audit_params.py                    # human summary
#   python scripts/audit_params.py --json out.json    # machine-readable candidates
#   python scripts/audit_params.py --mode statusticker --all
#
# Read-only: it opens mode modules and profiles, and writes nothing but the file you ask for.

import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core import profiles as profiles_mod            # noqa: E402
from core.config import load_json                    # noqa: E402
from core.param_audit import audit, group_candidates, render_report   # noqa: E402


def load_profiles(base_dir: str) -> dict:
    """{profile rel: modes dict} for every profile on disk."""
    out = {}
    root = profiles_mod.DEFAULT_PROFILE_NAME
    if os.path.exists(os.path.join(base_dir, root)):
        modes, _meta = profiles_mod.profile_modes(os.path.join(base_dir, root))
        out[root] = modes
    variants = os.path.join(base_dir, profiles_mod.PROFILES_DIRNAME)
    if os.path.isdir(variants):
        for name in sorted(os.listdir(variants)):
            if not name.endswith(".json"):
                continue
            rel = f"{profiles_mod.PROFILES_DIRNAME}/{name}"
            modes, _meta = profiles_mod.profile_modes(os.path.join(base_dir, rel))
            out[rel] = modes
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Audit parameter exposure across mode modules")
    parser.add_argument("--json", default=None, help="write the candidate list as JSON here")
    parser.add_argument("--report", default=None,
                        help="write the machine-generated markdown section here")
    parser.add_argument("--top", type=int, default=40, help="how many to show (default 40)")
    parser.add_argument("--mode", default=None, help="only this mode module (substring match)")
    parser.add_argument("--all", action="store_true",
                        help="include candidates in modes no profile uses")
    args = parser.parse_args((argv or sys.argv)[1:])

    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {}).get("types", {})
    result = audit(BASE_DIR, registry, load_profiles(BASE_DIR))

    if args.mode:
        keep = [a for a in result["modes"] if args.mode in a.mode]
        result = {**result, "modes": keep,
                  "candidates": [c for a in keep for c in a.candidates]}
        result["totals"] = {**result["totals"], "modules": len(keep)}

    totals = result["totals"]
    print(f"[Audit] {totals['modules']} mode module(s) scanned")
    print(f"[Audit] {totals['candidates']} candidate(s): {totals['operative']} operative, "
          f"{totals['placeholder']} placeholders the mode overwrites itself")
    print(f"[Audit] {totals['operative_in_used_modes']} operative inside modes a profile uses")
    print(f"[Audit] by kind: {totals['by_kind']}")
    print()
    for g in group_candidates(result, used_only=not args.all, limit=args.top):
        values = ", ".join(g["values"][:3]) + (" +more" if len(g["values"]) > 3 else "")
        print(f"  {g['mode']:34} {g['attr']:22} {g['kind']:10} "
              f"literals=[{values}] profiles={len(g['profiles'])}")
        print(f"      as written: {g['code'][:88]}")
        print(f"      suggestion: {g['suggestion']}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"totals": totals,
                       "candidates": [c.__dict__ for c in result["candidates"]]}, fh, indent=2)
        print(f"\n[Audit] wrote {args.json}")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(render_report(result, top=args.top))
        print(f"[Audit] wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
