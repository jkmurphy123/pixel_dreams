# core/params.py
#
# The parameter model: how a mode's config keys become editable fields.
#
# Design (see designs/PIXEL_DREAMS_DESIGN.md §6.4):
#   * INFERENCE IS THE BASELINE. A param's widget comes from the value's shape in the profile,
#     so a mode added tomorrow gets a form with no UI metadata written at all.
#   * SCHEMA IS AN OPT-IN UPGRADE. An entry in the type's `params` block in
#     modes_registry.json overrides the inference for that key (bounds, choices, label, group).
#
# Nothing here imports pygame or nicegui: the resolver is pure and fully testable, and the
# panel renders whatever it returns.
#
# Measured value shapes across the eight shipped profiles (2026-10-15):
#   int x555, float x321, str x271, bool x216, list[int] len3 x83 (colours),
#   list[float] len2 x28 (ranges), list[str] x25+ (labels/ids), list[list[int]] x6 (palettes),
#   list[int] len2 x6 (int ranges), list[dict] x3 (device lists), no plain dicts.
# Those are what the mapping table below covers; anything else falls back to raw JSON, which is
# honest (visible, validated on save) rather than silently lossy.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: Widget names the panel knows how to draw. A schema naming anything else is reported and
#: ignored rather than trusted (an unknown widget must not blank a field).
WIDGETS = (
    "switch",      # bool
    "number",      # int / float
    "text",        # str
    "choice",      # str with a known set
    "path",        # str that names a file/dir
    "color",       # [r, g, b]
    "range",       # [min, max]
    "stringlist",  # ["a", "b", ...]
    "palette",     # [[r,g,b], ...]
    "json",        # anything else: raw JSON textarea
    "secret",      # never rendered with its value; set in secrets.json
)

GROUPS = ("appearance", "layout", "behaviour", "data")

#: Key names that hold credentials. A secret's value is NEVER sent to the browser.
_SECRET_HINTS = ("api_key", "apikey", "token", "secret", "password", "passwd", "credential")

#: Name heuristics for keys that are declared but absent from a profile, where there is no
#: value to infer from. Matching is on whole TOKENS of the lower-cased key, not substrings:
#: substring matching let a bare "folder" miss the path rule (it only listed "_folder") while
#: "profile" would have hit "file". Ordered: more specific rules first.
_TOKEN_WIDGETS = (
    ("color", {"rgb", "rbg", "color", "colour"}),
    ("range", {"range"}),
    ("path", {"path", "paths", "file", "files", "folder", "folders", "dir", "dirs",
              "directory", "directories"}),
    ("stringlist", {"labels", "ids", "names", "items", "list"}),
    ("json", {"palette", "devices"}),   # structured values with no value to inspect yet
    ("number", {"size", "sizes", "px", "hz", "khz", "sec", "secs", "seconds", "ms", "min",
                "mins", "max", "count", "line", "lines", "alpha", "strength", "probability",
                "factor", "ratio", "scale", "width", "height", "radius", "thickness", "margin",
                "pad", "padding", "gap", "columns", "rows", "interval", "duration", "speed",
                "rate", "limit", "depth", "opacity", "blur", "seed", "x", "y", "w", "h",
                "cps"}),
)

#: Leading tokens that make a key a boolean flag ("show_time", "enable_grid").
_SWITCH_PREFIXES = ("show", "hide", "enable", "disable", "use", "allow", "is", "has", "invert")

#: Trailing tokens that make a key a boolean flag ("grid_enabled", "labels_visible").
_SWITCH_SUFFIXES = ("enabled", "disabled", "visible", "hidden", "on", "off")

#: Tokens that suggest a float rather than an int, when we have no value to look at.
#: "duration" is deliberately NOT here: in this codebase durations are integers (a slideshow
#: duration of 120 means 120), while the float-valued keys name their unit (_hz, _seconds, _cps).
_FLOAT_TOKENS = {"hz", "khz", "sec", "secs", "seconds", "alpha", "probability", "strength",
                 "factor", "ratio", "opacity", "scale", "interval", "cps"}

_GROUP_KEYWORDS = (
    ("appearance", ("font", "color", "rgb", "colour", "alpha", "opacity", "palette", "glow",
                    "brightness", "vignette", "scanline", "noise", "border", "shadow", "weight",
                    "italic", "bold", "size", "contrast", "theme", "text")),
    ("data", ("folder", "path", "file", "dir", "url", "devices", "feed", "api", "cache",
              "quote", "weather_location", "crypto", "ids", "labels", "data", "sources",
              "hostname", "endpoint", "directory")),
    ("layout", ("layout", "portrait", "landscape", "margin", "pad", "gap", "align", "x", "y",
                "width", "height", "columns", "rows", "position", "anchor", "spacing",
                "columns", "column", "row", "offset", "anchor", "resolution")),
)

_HUMAN_ACRONYMS = {"rgb": "RGB", "fps": "FPS", "hz": "Hz", "px": "px", "id": "ID", "ids": "IDs",
                   "url": "URL", "api": "API", "cpu": "CPU", "ram": "RAM", "gpu": "GPU",
                   "dow": "day of week", "crt": "CRT", "ai": "AI", "llm": "LLM"}


@dataclass
class ParamSpec:
    """One field of a mode's form."""

    key: str
    widget: str
    label: str
    group: str
    value: Any = None
    present: bool = False          # is the key set in the profile being inspected?
    origin: str = "absent"         # "profile" | "local override" | "absent"
    source: str = "inferred"       # "schema" | "inferred"
    type_name: str = ""            # bool | int | float | str | list[int] | ...
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: tuple = ()
    suggestions: tuple = ()        # known-but-not-closed values: keep the field free text
    item: str = ""                 # element type for list widgets
    derived: bool = False          # the mode computes its own value at runtime
    secret: bool = False
    required: bool = False
    help: str = ""
    default: Any = None            # the mode's own default (from its code), for absent keys
    has_default: bool = False
    warnings: tuple = ()


# ---------------------------------------------------------------- shape helpers

def is_secret_key(key: str) -> bool:
    low = key.lower()
    return any(hint in low for hint in _SECRET_HINTS)


def shape_of(value: Any) -> str:
    """A readable description of a value's shape, used for typing and messages."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        if not value:
            return "list"
        if all(isinstance(v, list) for v in value):
            inner = "int" if all(isinstance(n, int) for v in value for n in v) else "num"
            return f"list[list[{inner}]]"
        if all(isinstance(v, dict) for v in value):
            return "list[dict]"
        kinds = {type(v).__name__ for v in value}
        return f"list[{kinds.pop() if len(kinds) == 1 else 'mixed'}]"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def _is_rgb(value) -> bool:
    return (isinstance(value, list) and len(value) == 3
            and all(isinstance(v, int) and 0 <= v <= 255 for v in value))


def _is_range(value) -> bool:
    return (isinstance(value, list) and len(value) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value))


def infer_widget(value: Any, key: str = "") -> str:
    """The mapping table: a value's shape decides how it is edited."""
    if is_secret_key(key):
        return "secret"
    if isinstance(value, bool):
        return "switch"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        if _is_rgb(value):
            return "color"
        if _is_range(value):
            return "range"
        if all(isinstance(v, list) for v in value) and value:
            return "palette"
        if all(isinstance(v, str) for v in value):
            return "stringlist"
        return "json"
    return "json"


def key_tokens(key: str) -> list[str]:
    return [t for t in re.split(r"[_\s]+", key.strip().lower()) if t]


def infer_widget_for_absent(key: str) -> str:
    """
    Widget for a declared key that the profile does not set (no value to inspect).

    Token-based, and the boolean-flag test runs FIRST and only once: the switch prefixes used
    to be tested inside the per-widget loop, so every rule after them was unreachable for any
    key starting with "show_"/"is_"/"enable_" and "show_clock" came back as a colour.
    """
    if is_secret_key(key):
        return "secret"
    tokens = key_tokens(key)
    if not tokens:
        return "text"
    if tokens[0] in _SWITCH_PREFIXES or tokens[-1] in _SWITCH_SUFFIXES:
        return "switch"
    token_set = set(tokens)
    for widget, vocabulary in _TOKEN_WIDGETS:
        if token_set & vocabulary:
            return widget
    return "text"


def infer_type_for_absent(key: str, widget: str) -> str:
    if widget == "switch":
        return "bool"
    if widget == "color":
        return "list[int]"
    if widget == "number":
        return "float" if set(key_tokens(key)) & _FLOAT_TOKENS else "int"
    if widget in ("range", "stringlist", "palette", "json"):
        return "list"
    return "str"


def infer_group(key: str, widget: str) -> str:
    """A heuristic grouping (the schema's `group` wins when it is set)."""
    if widget == "color" or widget == "palette":
        return "appearance"
    if widget == "path":
        return "data"
    low = key.lower()
    for group, keywords in _GROUP_KEYWORDS:
        if any(word in low for word in keywords):
            return group
    return "behaviour"


def humanize(key: str) -> str:
    """'overlay_font_size' -> 'Overlay font size'; keeps known acronyms upper-case."""
    words = []
    for word in re.split(r"[_\s]+", key.strip()):
        if not word:
            continue
        low = word.lower()
        if low in _HUMAN_ACRONYMS:
            words.append(_HUMAN_ACRONYMS[low])
        elif word.isdigit():
            words.append(word)
        else:
            words.append(word if word.isupper() and len(word) > 1 else low)
    if not words:
        return key
    # Capitalise the first word unless it is an acronym — a blanket .capitalize() would turn
    # "CRT vignette" into "Crt vignette".
    acronyms = set(_HUMAN_ACRONYMS.values())
    head = words[0] if words[0] in acronyms else words[0].capitalize()
    return " ".join([head, *words[1:]])


# ---------------------------------------------------------------- schema resolution

def schema_entries(spec: dict) -> tuple[dict, list]:
    """
    The type's `params` block, plus warnings about entries the panel cannot use.

    A malformed entry is REPORTED and then ignored (the inference still renders the field),
    because one bad schema line must not cost you the ability to tune a mode.
    """
    raw = spec.get("params", {}) if isinstance(spec, dict) else {}
    warnings: list = []
    if not isinstance(raw, dict):
        return {}, [f"params block is {type(raw).__name__}, expected object"]

    clean: dict = {}
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            warnings.append(f"{key}: entry is {type(entry).__name__}, expected object")
            continue
        widget = entry.get("widget")
        if widget is not None and widget not in WIDGETS:
            warnings.append(f"{key}: unknown widget {widget!r} (known: {', '.join(WIDGETS)})")
            entry = {k: v for k, v in entry.items() if k != "widget"}
        group = entry.get("group")
        if group is not None and group not in GROUPS:
            warnings.append(f"{key}: unknown group {group!r} (known: {', '.join(GROUPS)})")
            entry = {k: v for k, v in entry.items() if k != "group"}
        clean[key] = entry
    return clean, warnings


def _apply_schema(spec: ParamSpec, entry: dict) -> ParamSpec:
    """Overlay a schema entry onto an inferred spec (schema wins, inference fills gaps)."""
    if not entry:
        return spec
    spec.source = "schema"
    if "widget" in entry:
        spec.widget = entry["widget"]
    if "label" in entry:
        spec.label = str(entry["label"])
    if "group" in entry:
        spec.group = entry["group"]
    if "help" in entry:
        spec.help = str(entry["help"])
    if "item" in entry:
        spec.item = str(entry["item"])
    if "derived" in entry:
        spec.derived = bool(entry["derived"])
    if "secret" in entry:
        spec.secret = bool(entry["secret"])
    if "default" in entry:
        spec.default = entry["default"]
        spec.has_default = True
    if "choices" in entry and isinstance(entry["choices"], list):
        spec.choices = tuple(entry["choices"])
        # A declared closed set DEFINES the widget, whatever inference guessed: a key whose
        # name looks numeric ("scale_mode") would otherwise keep a number field and silently
        # ignore the choices. Secrets stay masked.
        if spec.choices and not spec.secret:
            spec.widget = "choice"
    if "suggestions" in entry and isinstance(entry["suggestions"], list):
        # Suggestions are NOT a closed set: the field stays editable free text, with the
        # known values offered. Turning comparison-only code evidence into a dropdown would
        # hide every value the code never happened to compare against.
        spec.suggestions = tuple(entry["suggestions"])
    for bound in ("min", "max", "step"):
        if bound in entry and isinstance(entry[bound], (int, float)):
            setattr(spec, bound, entry[bound])
    if spec.secret:
        spec.widget = "secret"
    return spec


def resolve_params(instance_params: dict | None, spec: dict | None,
                   overridden_keys: tuple | list = ()) -> tuple[list[ParamSpec], list]:
    """
    Every field of a mode's form: the keys this profile sets, plus every key the registry
    declares for the type (so a param you have not set yet is still visible and, in Phase 3,
    addable). Returns (params, warnings).

    instance_params: the mode instance's own keys/values (after the override merge)
    spec: the registry type entry (for `params`, `required`, `optional`)
    overridden_keys: keys the modes_config.local.json layer supplies for this mode number
    """
    spec = spec or {}
    schema, warnings = schema_entries(spec)
    required = [k for k in spec.get("required", []) if isinstance(k, str)]
    optional = [k for k in spec.get("optional", []) if isinstance(k, str)]
    instance_params = instance_params or {}
    overridden = set(overridden_keys or ())

    declared = list(dict.fromkeys(required + optional))          # order preserved, deduped
    extras = [k for k in instance_params if k not in declared]    # config keys the registry lacks
    if extras:
        warnings.append(
            f"{len(extras)} key(s) are set in the config but not declared in the registry: "
            f"{', '.join(sorted(extras))} (add them to 'optional' so the validator stops warning)"
        )

    params: list[ParamSpec] = []
    for key in declared + extras:
        present = key in instance_params
        value = instance_params.get(key) if present else None
        if present:
            widget = infer_widget(value, key)
            type_name = shape_of(value)
        else:
            widget = infer_widget_for_absent(key)
            type_name = infer_type_for_absent(key, widget)

        p = ParamSpec(
            key=key,
            widget=widget,
            label=humanize(key),
            group=infer_group(key, widget),
            value=value,
            present=present,
            origin=("local override" if (present and key in overridden)
                    else "profile" if present else "absent"),
            type_name=type_name,
            required=key in required,
            secret=widget == "secret" or is_secret_key(key),
        )
        if p.widget == "number" and isinstance(value, bool) is False and isinstance(value, int):
            p.step = 1
        if p.widget == "range" and isinstance(value, list) and value:
            p.item = shape_of(value[0])
        if p.widget in ("stringlist", "palette") and isinstance(value, list) and value:
            p.item = shape_of(value[0])
        if p.secret:
            # A secret's value must not travel to the renderer at all. The loader injects it
            # into the mode at construction time; the panel only ever needs to know it exists.
            p.value = None
        _apply_schema(p, schema.get(key, {}))
        if p.secret:
            p.value = None
        params.append(p)

    # One source of truth for group order: GROUPS. A separate dict here drifted out of step
    # with group_params() once already.
    order = {group: index for index, group in enumerate(GROUPS)}
    params.sort(key=lambda p: (order.get(p.group, 9), 0 if p.present else 1, p.key))
    return params, warnings


def group_params(params: list[ParamSpec]) -> list[tuple[str, list[ParamSpec]]]:
    """Params bucketed by group, each bucket in the order given by GROUPS."""
    buckets: dict[str, list[ParamSpec]] = {g: [] for g in GROUPS}
    for p in params:
        buckets.setdefault(p.group, []).append(p)
    return [(g, buckets[g]) for g in GROUPS if buckets.get(g)]


def coverage(instance_params: dict, spec: dict) -> dict:
    """
    What a form built from this resolver covers, for the Phase 2 acceptance check:
    every key the profile sets, and every key the registry declares.
    """
    params, _ = resolve_params(instance_params, spec)
    rendered = {p.key for p in params}
    present = {k for k in (instance_params or {}) if k not in ("type", "name", "title")}
    spec = spec or {}
    declared = set(spec.get("required", [])) | set(spec.get("optional", []))
    return {
        "rendered": len(rendered),
        "present": len(present),
        "declared": len(declared),
        "missing_present": sorted(present - rendered),
        "missing_declared": sorted(declared - rendered),
    }
