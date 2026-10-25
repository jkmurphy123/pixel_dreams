#!/usr/bin/env python3
"""Design-time probe: does the registry entry drafted in the design doc pass the
application's OWN validator?

The point is to test the schema against the real rules (core/validation.py,
core/params.py) rather than against my reading of them. The mode class does not
exist yet, so this runs with check_imports=False; it also runs once with
check_imports=True to prove that check is actually live and that the only thing
still failing is the missing entrypoint.

Run from the repo root:
  SDL_VIDEODRIVER=dummy .venv/bin/python designs/inkmap_proto/REGISTRY_CHECK.py
"""
import io
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from core.validation import errors, validate_profile, validate_registry, warnings  # noqa: E402
from core.params import resolve_params, validate_param_value  # noqa: E402
from core.config import COMMON_INSTANCE_KEYS  # noqa: E402
from core.config import load_json  # noqa: E402

DOC = os.path.join(BASE, "designs", "INK_FANTASY_MAP_DESIGN.md")


def draft_entry():
    """Pull the ```json block out of section 6 and parse it."""
    text = io.open(DOC, encoding="utf-8").read()
    sec = text[text.index("## 6. Registry entry"):text.index("## 7. Phases")]
    a = sec.index("```json") + len("```json")
    b = sec.index("```", a)
    return json.loads("{" + sec[a:b] + "}")


def main():
    registry_json = load_json(os.path.join(BASE, "modes_registry.json"), {})
    draft = draft_entry()
    assert list(draft) == ["inkmap"], f"expected one type, got {list(draft)}"

    augmented = dict(registry_json)
    augmented["types"] = dict(registry_json["types"])
    augmented["types"]["inkmap"] = draft["inkmap"]
    print(f"registry: {len(registry_json['types'])} types -> {len(augmented['types'])} with the draft")

    # 1. the app's registry validator, schema only
    issues = validate_registry(augmented, check_imports=False)
    errs, warns = errors(issues), warnings(issues)
    print(f"\nvalidate_registry(check_imports=False): {len(errs)} errors, {len(warns)} warnings")
    for i in errs + warns:
        print("   ", i.render())

    # 2. the same call WITH imports - it must fail, and only about the missing class
    issues_imp = validate_registry(augmented, check_imports=True)
    errs_imp = errors(issues_imp)
    print(f"\nvalidate_registry(check_imports=True): {len(errs_imp)} errors (expected >0)")
    for i in errs_imp:
        print("   ", i.render())
    mentions_missing = all("inkmap" in i.render() or "ink_map_mode" in i.render()
                           for i in errs_imp) if errs_imp else False
    print(f"   every error is about the not-yet-written mode: {mentions_missing}")

    # 3. a representative instance through the panel's own param resolver
    inst = {
        "type": "inkmap",
        "seed": 12345,
        "draw_minutes": 4.0,
        "water_style": "squiggle",
        "road_style": "double",
        "compass_placement": "top_left",
        "map_title": "The Shattered Reach",
        "settlements": 9,
        "rock_detail": 1.4,
    }
    # The panel resolves the mode's OWN param keys; `type` is the instance's
    # discriminator (a COMMON_INSTANCE_KEY), not a param, so it is not passed here.
    param_keys = {k: v for k, v in inst.items() if k != "type"}
    params, pwarn = resolve_params(param_keys, draft["inkmap"])
    print(f"\nresolve_params: {len(params)} fields, {len(pwarn)} warnings")
    for w in pwarn:
        print("   ", w)
    unset = [p.key for p in params if not p.has_default and p.key not in param_keys]
    print(f"   fields with no default and not set here: {unset}")
    clash = sorted(set(draft["inkmap"]["optional"]) & COMMON_INSTANCE_KEYS)
    print(f"   optional keys that collide with common instance keys: {clash}")

    # 4. a whole profile holding it. validate_profile takes the INNER
    #    {"<number>": {...}} mapping, not the whole document.
    profile = {"0": inst}
    # validate_configs.py passes the TYPES mapping here, not the whole registry doc.
    pissues = validate_profile(profile, augmented["types"], base_dir=BASE)
    perrs, pwarns = errors(pissues), warnings(pissues)
    print(f"\nvalidate_profile: {len(perrs)} errors, {len(pwarns)} warnings")
    for i in perrs + pwarns:
        print("   ", i.render())

    # 5. the panel's own value check must actually have teeth. Controls:
    #    a closed set violated, and a number out of range.
    bykey = {p.key: p for p in params}
    c1 = validate_param_value(bykey["water_style"], "not-a-style")
    c2 = validate_param_value(bykey["draw_minutes"], -1)
    c3 = validate_param_value(bykey["draw_minutes"], 4.0)
    c4 = validate_param_value(bykey["compass_placement"], "middle")
    c5 = validate_param_value(bykey["paper_tone"], [232, 217, 184])
    print("\nCONTROLS (validate_param_value):")
    print("   water_style='not-a-style' ->", c1)
    print("   draw_minutes=-1           ->", c2)
    print("   draw_minutes=4.0          ->", c3, "(must be empty)")
    print("   compass_placement='middle'->", c4)
    print("   paper_tone=[232,217,184]  ->", c5, "(must be empty)")

    ok = (not errs and not pwarn and not perrs and not pwarns and not unset
          and not clash and errs_imp and mentions_missing
          and c1 and c2 and not c3 and c4 and not c5)
    print(f"\nVERDICT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
