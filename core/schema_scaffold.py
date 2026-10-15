# core/schema_scaffold.py
#
# Builds a DRAFT `params` block for every mode type by reading the mode's own code.
#
# Why this exists (design §6.4): the panel can infer a widget from a config VALUE, but it
# cannot know three things that only the code knows —
#   * the type of a key no profile sets yet (bool/int/float/str),
#   * the choices a string key accepts ("imperial"/"metric", "auto"/"portrait"/"landscape"),
#   * which keys the mode OVERWRITES at runtime (a size computed from screen width), so the
#     configured value is a hint rather than the truth.
# Plus the drift: keys a mode reads that the registry never declared, which is why a form built
# from the registry alone silently hides real knobs.
#
# The draft is deliberately SMALL: it records only what inference cannot already get right.
# Re-emitting every key would also freeze today's inference into the schema, so a later
# improvement in core/params.py could never take effect. Entries are added, never overwritten,
# so a hand-edited bound or label survives a re-run.
#
# Pure analysis + merge: no file I/O here (see scripts/scaffold_param_schema.py), no pygame,
# no nicegui.

from __future__ import annotations

import os
import re
from collections import OrderedDict

from .config import normalize_type
from .params import infer_widget_for_absent, humanize

#: config.get("key") / config.get('key', default) / self.config.get(...)
_GET_RE = re.compile(
    r"""(?:self\.)?(?:config|cfg)\s*\.\s*get\(\s*['"]([A-Za-z0-9_]+)['"]"""
    r"""(?:\s*,\s*([^()]*?))?\s*\)""")
#: config["key"]
_SUBSCRIPT_RE = re.compile(r"""(?:self\.)?(?:config|cfg)\s*\[\s*['"]([A-Za-z0-9_]+)['"]\s*\]""")
#: bool(config.get("key", False)) and friends
_COERCION_RE = re.compile(
    r"""(bool|int|float|str|list|tuple)\s*\(\s*(?:self\.)?(?:config|cfg)\s*\.\s*get\(\s*"""
    r"""['"]([A-Za-z0-9_]+)['"]""")
#: comparisons that reveal an accepted value: x == "portrait"
_COMPARE_RE = re.compile(r"""\b([A-Za-z_][A-Za-z0-9_]*)\s*[=!]=\s*['"]([^'"]{1,40})['"]""")
#: a named set of accepted values: _VALID_SCALE_MODES = ("fit", "fill", ...) — including the
#: set-literal form {"stretch", "fit", "cover"}, which the shipped modes use
_VALUE_SET_RE = re.compile(
    r"""\b(?:self\.)?([A-Za-z_][A-Za-z0-9_]*(?:VALID|ALLOWED|CHOICES|OPTIONS|MODES)[A-Za-z0-9_]*)"""
    r"""\s*[:=]\s*[\(\[\{]([^\)\]\}]*)[\)\]\}]""")
#: membership tests that link a key's variable to one of those sets:
#:   if scale_mode not in self._VALID_SCALE_MODES:
_MEMBERSHIP_RE = re.compile(
    r"""\b([A-Za-z_][A-Za-z0-9_]*)\s+(?:not\s+)?in\s+(?:self\.)?([A-Za-z_][A-Za-z0-9_]*)""")
#: assignments to an attribute: self.font_size = <something>
_ASSIGN_RE = re.compile(r"""self\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$""", re.MULTILINE)
#: RHS that means "computed from the screen", i.e. the config value is overridden at runtime
_DERIVED_HINT_RE = re.compile(r"""\bself\.(w|h|width|height)\b|\bmax\(|\bmin\(|\bint\(.*\*""")

#: Structural instance keys: they are not parameters and must never enter the schema.
STRUCTURAL_KEYS = ("type", "name", "title")


def _literal(text: str):
    """A JSON-ish literal from source text, or None if it is not a plain literal."""
    text = (text or "").strip().rstrip(",")
    if not text:
        return None
    if text in ("True", "False"):
        return text == "True"
    if text in ("None", "null"):
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d*\.\d+([eE][-+]?\d+)?", text):
        return float(text)
    if re.fullmatch(r"""['"].*['"]""", text, re.DOTALL):
        return text[1:-1]
    if text.startswith(("[", "{")) and text.endswith(("]", "}")):
        import json
        try:
            return json.loads(text.replace("'", '"'))
        except Exception:
            return None
    return None


def _widget_for_literal(value) -> str | None:
    """
    The widget a code default implies — delegated to the panel's own inference, so a default
    like [255, 200, 120] reads as a colour and [0.2, 0.8] as a range instead of both being
    "json" (which is what a hand-rolled literal mapper concluded, and it would have made the
    schema WORSE than inference).
    """
    from .params import infer_widget

    if value is None:
        return None
    return infer_widget(value)


def _values_from_source(text: str) -> list:
    """String literals inside a source fragment ('"fit", "fill"') -> ['fit', 'fill']."""
    return re.findall(r"""['"]([^'"]{1,40})['"]""", text or "")


def scan_module(source: str) -> dict:
    """
    Everything the code tells us about its config keys.

    Returns {"keys": {key: {coercion, default, compares: [values]}},
             "derived": [key, ...],
             "module_compares": {var: [values]},
             "value_sets": {CONST: [values]}}
    """
    keys: dict = {}

    def entry_for(key: str) -> dict:
        return keys.setdefault(key, {"coercion": None, "default": None, "compares": []})

    for key, default in _GET_RE.findall(source):
        if key in STRUCTURAL_KEYS:
            continue
        entry = entry_for(key)
        if default:
            entry["default"] = _literal(default)
    for key in _SUBSCRIPT_RE.findall(source):
        if key not in STRUCTURAL_KEYS:
            entry_for(key)
    for coercion, key in _COERCION_RE.findall(source):
        if key in STRUCTURAL_KEYS:
            continue
        entry_for(key)["coercion"] = coercion

    # Named sets of accepted values, and the membership tests that tie a key's variable to one.
    value_sets = {name: _values_from_source(body)
                  for name, body in _VALUE_SET_RE.findall(source)}
    memberships = {}
    for var, const in _MEMBERSHIP_RE.findall(source):
        if const in value_sets:
            memberships.setdefault(var.lower(), set()).update(value_sets[const])

    compares: dict = {}
    for var, value in _COMPARE_RE.findall(source):
        compares.setdefault(var.lower(), []).append(value)

    for key, entry in keys.items():
        # A key's accepted values may show up as comparisons on a variable of the same name,
        # or as a membership test against a VALID_* set (the idiomatic form in this codebase).
        # The two are kept apart: a declared set is CLOSED (safe as a dropdown), comparisons
        # alone are open-ended evidence (only a suggestion list — a one-option dropdown would
        # trap the user).
        found = set(compares.get(key.lower(), []))
        closed = set(memberships.get(key.lower(), set()))
        entry["compares"] = sorted(found | closed)
        entry["from_set"] = sorted(closed)

    derived = []
    for attr, rhs in _ASSIGN_RE.findall(source):
        rhs = rhs.strip()
        if attr not in keys or "config" in rhs or "cfg" in rhs:
            continue
        if _DERIVED_HINT_RE.search(rhs):
            derived.append(attr)
    return {"keys": keys, "derived": sorted(set(derived)), "module_compares": compares,
            "value_sets": value_sets}


def _candidate_widget(entry: dict) -> "str | None":
    """
    The widget the code implies for a key.

    A `list(...)`/`tuple(...)` coercion is NOT evidence of a list of strings — the shipped modes
    use it to copy an RGB triple — so it yields no widget and the value/default shape decides.
    "choice" requires a CLOSED set (>=2 values from a declared set); comparison-only evidence
    leaves it a text field with suggestions.
    """
    coercion = entry.get("coercion")
    if coercion == "bool":
        return "switch"
    if coercion in ("int", "float"):
        return "number"
    if coercion == "str":
        return "choice" if len(_clean_choices(entry.get("from_set", []))) >= 2 else "text"
    widget = _widget_for_literal(entry.get("default"))
    if widget in (None, "text") and len(_clean_choices(entry.get("from_set", []))) >= 2:
        return "choice"
    return widget


def _is_meaningful_correction(inferred: str, candidate: "str | None") -> bool:
    """
    Should the schema carry this correction?

    Evidence strength, weakest to strongest: a key's NAME is a guess, a code default's shape is
    better, an explicit coercion is best. So a code candidate normally wins — with one exception:
    when the code says "str" but the name reveals the string is a PATH or a COLOUR, the name is a
    refinement (both are strings), not a contradiction, and the better widget should stay.

    Everything else is a real contradiction, and the code wins: a `str(...)` coercion must beat a
    numeric-looking name, or a string like "cover" ends up in a number field.
    """
    if not candidate or candidate == inferred:
        return False
    if candidate == "text" and inferred in ("path", "color"):
        return False
    return True


def _clean_choices(values) -> list:
    """
    Drop comparisons that are clearly not options. A value with a separator in it ("a/b.png")
    is a path the code happened to compare against, not something to offer in a dropdown.
    """
    out = []
    for value in values or []:
        if not isinstance(value, str) or not value or len(value) > 24:
            continue
        if any(ch in value for ch in ("/", "\\", ".", " ")):
            continue
        out.append(value)
    return sorted(set(out))


def _mode_sources(base_dir: str, registry: dict) -> dict:
    """Map type_key -> mode module source text (the entrypoint's module)."""
    sources: dict = {}
    for type_key, spec in (registry or {}).items():
        entrypoint = spec.get("entrypoint", "")
        if ":" not in entrypoint:
            continue
        module_name = entrypoint.split(":", 1)[0]
        path = os.path.join(base_dir, module_name.replace(".", os.sep) + ".py")
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace") as fh:
                sources[type_key] = fh.read()
    return sources


def analyse(base_dir: str, registry: dict, profiles_modes: list) -> dict:
    """
    The full analysis, per type:

        {"types": {type_key: {"code_keys": [...], "declared": [...], "drift": [...],
                              "derived": [...], "absent_widget_conflicts": {...},
                              "present_shapes": {key: shape}}},
         "totals": {...}}
    """
    from .params import infer_widget, shape_of

    sources = _mode_sources(base_dir, registry)
    present: dict = {}
    for modes in profiles_modes:
        for cfg in modes.values():
            if not isinstance(cfg, dict):
                continue
            type_key = normalize_type(cfg.get("type", ""))
            bucket = present.setdefault(type_key, {})
            for key, value in cfg.items():
                if key in ("type", "name", "title"):
                    continue
                bucket.setdefault(key, shape_of(value))

    out: dict = {"types": {}, "totals": {}}
    for type_key, spec in (registry or {}).items():
        declared = list(spec.get("required", [])) + list(spec.get("optional", []))
        scan = scan_module(sources.get(type_key, ""))
        code_keys = sorted(scan["keys"])
        drift = sorted(k for k in code_keys if k not in declared)
        absent = [k for k in (set(code_keys) | set(declared)) if k not in present.get(type_key, {})]
        conflicts = {}
        for key in absent:
            candidate = _candidate_widget(scan["keys"].get(key, {}))
            inferred = infer_widget_for_absent(key)
            if _is_meaningful_correction(inferred, candidate):
                conflicts[key] = {"inferred": inferred, "from_code": candidate}
        observed = present.get(type_key, {})
        observed_conflicts = {
            key: {"observed": shape}
            for key, shape in observed.items()
        }
        out["types"][type_key] = {
            "code_keys": code_keys,
            "declared": declared,
            "drift": drift,
            "derived": scan["derived"],
            "absent_widget_conflicts": conflicts,
            "observed_shapes": observed_conflicts,
            "declared_absent": sorted(set(declared) - set(observed)),
        }
    out["totals"] = {
        "types": len(out["types"]),
        "types_without_module": len([t for t in out["types"] if t not in sources]),
        "drift_keys": sum(len(v["drift"]) for v in out["types"].values()),
        "derived_candidates": sum(len(v["derived"]) for v in out["types"].values()),
        "declared_absent_keys": sum(len(v["declared_absent"]) for v in out["types"].values()),
        "widget_conflicts": sum(len(v["absent_widget_conflicts"]) for v in out["types"].values()),
    }
    return out


def build_draft(base_dir: str, registry: dict, profiles_modes: list,
                include_all_keys: bool = False) -> tuple[dict, dict]:
    """
    A draft `params` block per type, plus the analysis it came from.

    Only what inference cannot know is emitted: a widget that CONTRADICTS the name heuristic,
    the accepted choices, the code's default, and keys the mode overwrites at runtime. With
    include_all_keys=True every key gets an explicit entry (explicit, but it freezes today's
    inference into the schema — opt in deliberately).
    """
    analysis = analyse(base_dir, registry, profiles_modes)
    sources = _mode_sources(base_dir, registry)
    draft: dict = OrderedDict()

    for type_key, info in analysis["types"].items():
        scan = scan_module(sources.get(type_key, ""))
        declared = set(info["declared"])
        keys = sorted(declared | set(scan["keys"]))
        entries: "OrderedDict[str, dict]" = OrderedDict()

        for key in keys:
            entry = scan["keys"].get(key, {})
            candidate = _candidate_widget(entry)
            inferred = infer_widget_for_absent(key)
            piece: dict = {}
            widget_emitted = None
            if _is_meaningful_correction(inferred, candidate):
                widget_emitted = candidate
                piece["widget"] = candidate
            # A declared value set is a closed set -> choices. Comparison-only evidence is
            # open-ended -> suggestions, so the field stays editable as free text.
            closed = _clean_choices(entry.get("from_set", []))
            comparisons = _clean_choices(entry.get("compares", []))
            if len(closed) >= 2:
                piece["choices"] = closed
            elif comparisons:
                piece["suggestions"] = comparisons
            if entry.get("default") is not None:
                piece["default"] = entry["default"]
            if key in info["derived"]:
                piece["derived"] = True
            if piece or include_all_keys:
                if include_all_keys and "widget" not in piece:
                    piece["widget"] = candidate or inferred
                entries[key] = piece

        if entries:
            draft[type_key] = entries

    return draft, analysis


def merge_into_registry(registry_json: dict, draft: dict, *, drift_keys: dict | None = None,
                        fix_optional: bool = False) -> dict:
    """
    Merge a draft into a registry document, and (optionally) declare the drift keys.

    Rules (deliberate):
      * existing `params` entries are never overwritten, and an existing key inside an entry
        keeps its value — your hand-written bounds and labels survive a re-run
      * `optional` gains the drift keys (keys the code reads but the registry never declared),
        appended in sorted order with existing order preserved — only when fix_optional is set
      * key order is otherwise preserved, so the diff stays readable

    `drift_keys` is {type_key: [key, ...]} from analyse()["types"][t]["drift"].

    Returns {"added_params": {type: [keys]}, "added_optional": {type: [keys]},
             "skipped_existing": {type: [keys]}}
    """
    types = registry_json.setdefault("types", {})
    drift_keys = drift_keys or {}
    report = {"added_params": {}, "added_optional": {}, "skipped_existing": {}}

    for type_key, entries in (draft or {}).items():
        spec = types.setdefault(type_key, {})
        params = spec.setdefault("params", OrderedDict())
        added, skipped = [], []
        for key, entry in entries.items():
            if key in params:
                missing = {k: v for k, v in entry.items() if k not in params[key]}
                if missing:
                    params[key].update(missing)
                    added.append(key)
                else:
                    skipped.append(key)
            else:
                params[key] = entry
                added.append(key)
        if added:
            report["added_params"][type_key] = added
        if skipped:
            report["skipped_existing"][type_key] = skipped

    if fix_optional:
        for type_key, keys in drift_keys.items():
            spec = types.get(type_key)
            if not spec or not keys:
                continue
            optional = spec.setdefault("optional", [])
            declared = set(optional) | set(spec.get("required", []))
            fresh = sorted(k for k in keys if k not in declared)
            if fresh:
                optional.extend(fresh)
                report["added_optional"][type_key] = fresh

    return report
