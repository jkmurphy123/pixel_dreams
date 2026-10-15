#!/usr/bin/env python3
# validate_configs.py
#
# Static validation of modes_registry.json + modes config files.
# Catches config typos at dev time instead of at kiosk runtime.
#
# Usage:
#   python3 validate_configs.py              # validate the active config
#   python3 validate_configs.py --all        # also validate every configs/*.json variant
#   python3 validate_configs.py --config configs/modes_config_windows.json
#
# Exit code 0 = no errors (warnings allowed), 1 = errors found.
#
# The RULES live in core/validation.py, because the web panel applies the same ones before it
# writes a file. This script owns the CLI, the report format and the exit code; it must not grow
# its own copy of the checks, or the panel and the validator would disagree about what is valid.

import argparse
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.config import load_json, load_project_config
from core.validation import errors, validate_profile, validate_registry, warnings


def report(name: str, issues) -> None:
    for issue in issues:
        print(issue.render())


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate pixel_dreams configs")
    parser.add_argument("--config", default=None,
                        help="Specific modes config file to validate")
    parser.add_argument("--all", action="store_true",
                        help="Also validate every configs/*.json variant")
    args = parser.parse_args((argv or sys.argv)[1:])

    all_issues = []

    # Registry
    print("[Validate] Registry: modes_registry.json")
    registry_json = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    registry_issues = validate_registry(registry_json)
    all_issues.extend(registry_issues)
    report("modes_registry.json", registry_issues)
    types = registry_json.get("types")
    types = types if isinstance(types, dict) else {}
    if types:
        print(f"[Validate] Registry OK: {len(types)} type(s)")

    # Active config (respects registry settings / --config / local override)
    _, _, modes_config, config_path = load_project_config(BASE_DIR, config_override=args.config)
    name = os.path.basename(config_path)
    print(f"[Validate] Config: {name}")
    issues = validate_profile(modes_config, types, base_dir=BASE_DIR)
    all_issues.extend(issues)
    report(name, issues)
    if modes_config and not errors(issues):
        from core.config import infer_max_modes_from_config
        print(f"[Validate] Config OK: {len(modes_config)} mode(s), "
              f"max_modes={infer_max_modes_from_config(modes_config)}")

    # All variants on request
    if args.all:
        variants_dir = os.path.join(BASE_DIR, "configs")
        if os.path.isdir(variants_dir):
            for fname in sorted(os.listdir(variants_dir)):
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(variants_dir, fname)
                cfg = load_json(path, {}).get("modes", {})
                label = f"configs/{fname}"
                print(f"[Validate] Config: {label}")
                variant_issues = validate_profile(cfg, types, base_dir=BASE_DIR)
                all_issues.extend(variant_issues)
                report(label, variant_issues)

    print()
    print(f"[Validate] Done: {len(errors(all_issues))} error(s), "
          f"{len(warnings(all_issues))} warning(s)")
    return 1 if errors(all_issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
