# core/param_audit.py
#
# The parameter exposure audit (design §10 Phase 5).
#
# The panel can only tune what is a parameter. This finds the appearance values that are NOT
# parameters yet — hardcoded colours, magic margins and ratios, font sizes computed from a constant,
# hardcoded alphas, pacing — so they can be reviewed and, where it is worth it, exposed.
#
# It is a READ-ONLY analysis: nothing here changes a mode. The output is a candidate list with a
# recommendation each, for review (design §10: "reviewed before anything changes").
#
# What makes it more than a grep:
#   * PLACEHOLDERS ARE NOT CANDIDATES. `self.margin_x = 20` followed by `self.margin_x = int(self.w
#     * 0.06)` in enter()/resize() is a default that is immediately overwritten; the real knob is the
#     ratio, and reporting the 20 would be noise. An attribute assigned a literal AND later assigned
#     a computed value is reported as `placeholder`, with the computed expression named.
#   * ALREADY-PARAMETRIZED VALUES ARE NOT CANDIDATES. If the attribute is fed from a config read
#     (`self.font_size = int(self.font_size_cfg)`), exposing it again would add a second knob for one
#     value. Detected via the config reads the mode already does.
#   * REACH MATTERS. A knob in a mode used by 6 profiles is worth more than one in a mode used by
#     none, so every candidate carries the profiles that use it.
#
# AST, not regex: this has to distinguish an assignment from a reassignment, and a literal from an
# expression containing literals.

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field

#: Which kinds of hardcoded value this audit looks for, and how much each matters for tuning a wall
#: in different orientations (the thing this project is for).
KIND_WEIGHT = {
    "font_size": 10,     # the single most orientation-sensitive thing there is
    "margin": 8,         # layout breathing room: what looks right in portrait looks cramped in landscape
    "ratio": 8,          # a layout proportion: the knob behind most margins
    "colour": 6,         # taste, and the easiest to judge on a real wall
    "font_name": 5,      # legibility at a distance
    "alpha": 4,          # subtlety: often the difference between polished and flat
    "gap": 4,
    "timing": 3,         # pacing, tunable but rarely the problem
    "geometry": 2,       # one-off coordinates: rarely worth a knob
}

KINDS = tuple(KIND_WEIGHT)

#: Calls whose arguments are appearance values, and which position carries what.
_FONT_SIZE_CALLS = {
    "get_font": 1,        # (name, size, ...)
    "SysFont": 1,         # (name, size)
    "Font": 1,            # (path_or_none, size)
}

#: Names that suggest a margin/padding/gap when they hold a number.
_MARGIN_TOKENS = ("margin", "padding", "inset", "gutter", "border", "spacing", "indent")
_GAP_TOKENS = ("gap", "space", "separation", "offset", "pad")
_SIZE_TOKENS = ("_w", "_h", "_size", "_px", "_width", "_height", "_len", "_thickness", "_radius")
_TIMING_TOKENS = ("interval", "period", "delay", "duration", "fps", "speed", "rate", "fade",
                  "cooldown", "timeout", "pace")


#: Attribute names that are screen geometry rather than a knob of their own: a ratio computed from
#: these is a candidate; a ratio computed from anything else is a value derived from something that
#: already exists (and exposing it would be a second knob for one behaviour).
_SCREEN_ATTRS = {"w", "h", "width", "height", "screen", "cache", "manager", "surface", "rect",
                 "size", "min", "max"}


def _derived_from_screen_only(expr_ast, attr: str) -> bool:
    for node in ast.walk(expr_ast):
        if isinstance(node, ast.Attribute) and node.attr not in _SCREEN_ATTRS | {attr}:
            return False
    return True


def _ratio_detail(expr_ast, ratios: list) -> str:
    """What the ratio is, and the constants that go with it (a floor is part of the knob)."""
    floors = []
    for node in ast.walk(expr_ast):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in ("max", "min") and node.args:
            first = _literal(node.args[0])
            if isinstance(first, (int, float)) and not isinstance(first, bool):
                floors.append(f"{node.func.id}({first}, ...)")
    text = "a proportion baked into the mode"
    if floors:
        text += f", with {' and '.join(floors)} as a floor/cap"
    return text


@dataclass
class Candidate:
    """One hardcoded appearance value, with everything a review needs to judge it."""

    mode: str                     # module name, e.g. "status_ticker_mode"
    type_key: str = ""            # registry type, e.g. "statusticker"
    attr: str = ""                # the attribute or call target it feeds, e.g. "font_size"
    kind: str = "geometry"
    line: int = 0
    code: str = ""                # the source line, stripped
    literal: str = ""             # the literal as written
    status: str = "operative"     # operative | placeholder | parametrized
    detail: str = ""              # why it is/ is not a candidate, or what overwrites it
    suggestion: str = ""          # the param name + type to add, when there is one
    profiles: tuple = ()          # profiles that use this mode
    weight: float = 1.0

    @property
    def key(self) -> str:
        return f"{self.mode}:{self.attr}:{self.line}"


@dataclass
class ModeAudit:
    mode: str
    type_key: str = ""
    path: str = ""
    candidates: list = field(default_factory=list)
    config_keys: tuple = ()
    trivial: int = 0          # 0/1/2/-1 values skipped as indexes or flags, not knobs


# ---------------------------------------------------------------- literal helpers

def _literal(node):
    """The Python value for a literal node, or None. Tuples come back as tuples."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        # -1 and +1 are UnaryOp, not Constant: without this, every negative literal is invisible
        # to the audit (found by a test whose only job was to check 0/1/-1 noise handling).
        inner = _literal(node.operand)
        if isinstance(inner, (int, float)) and not isinstance(inner, bool):
            return -inner if isinstance(node.op, ast.USub) else inner
        return None
    if isinstance(node, ast.Tuple):
        values = []
        for element in node.elts:
            if not isinstance(element, ast.Constant):
                return None
            values.append(element.value)
        return tuple(values)
    return None


def _is_colour(value) -> bool:
    """An RGB/RGBA tuple of ints in range, or a #rrggbb string."""
    if isinstance(value, str):
        body = value.lstrip("#")
        return len(body) in (3, 6) and all(c in "0123456789abcdefABCDEF" for c in body)
    if isinstance(value, tuple) and len(value) in (3, 4):
        return all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255
                   for v in value)
    return False


def _numbers(node) -> list:
    """Every numeric literal inside an expression (for spotting ratios and magic margins)."""
    found = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, (int, float)) \
                and not isinstance(child.value, bool):
            found.append(child.value)
    return found


def _parametrised(node, config_names) -> bool:
    """True when the expression's value ultimately comes from a config read."""
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in config_names:
            return True
        if isinstance(child, ast.Attribute) and child.attr in config_names:
            return True
    return False


def _classify(attr: str, value) -> str:
    """Which kind of knob this looks like, from the attribute name and the value's shape."""
    name = attr.lower()
    if _is_colour(value):
        return "colour"
    if any(t in name for t in _MARGIN_TOKENS):
        return "margin"
    if any(t in name for t in _GAP_TOKENS):
        return "gap"
    if any(t in name for t in _TIMING_TOKENS):
        return "timing"
    if "font" in name and "name" in name:
        return "font_name"
    if "font" in name or "text" in name and "size" in name:
        return "font_size"
    if any(t in name for t in _SIZE_TOKENS):
        return "geometry"
    return "geometry"


def _suggest(attr: str, kind: str, value) -> str:
    """The param this value would become, named the way the rest of the registry names things."""
    if kind == "colour":
        return f"{attr} (colour widget; current {value!r})"
    if kind == "ratio":
        return f"{attr} (number 0.0-1.0; widget number, step 0.005)"
    if kind == "margin" or kind == "gap":
        return f"{attr} (number; int pixels, or a ratio if it scales with the wall)"
    if kind == "font_size":
        return f"{attr} (number; int pixels)"
    if kind == "timing":
        return f"{attr} (number seconds)"
    return f"{attr} (number)"


# ---------------------------------------------------------------- the analysis

def audit_source(source: str, *, mode: str = "", type_key: str = "", profiles: tuple = (),
                 path: str = "") -> ModeAudit:
    """
    Audit one mode module.

    Only values that are ALREADY what the mode draws with are worth reporting, so an attribute
    assigned a literal and later recomputed is recorded as a placeholder instead of a knob.
    """
    tree = ast.parse(source)
    lines = source.splitlines()
    result = ModeAudit(mode=mode, type_key=type_key, path=path)

    # 1. which config keys the mode reads, and which attributes they land in (a value fed from
    #    config is already tunable; exposing it again would be two knobs for one value)
    config_keys = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("get", "getint", "getfloat", "getbool") and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                config_keys.add(first.value)
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str):
            config_keys.add(node.slice.value)
    result.config_keys = tuple(sorted(config_keys))
    config_vars = {f"{k}" for k in config_keys} | {f"{k}_cfg" for k in config_keys}

    # 2. every attribute assignment, so a literal can be told apart from a later computation
    literal_hits: list = []            # (attr, value, line, code)
    computed_attrs: dict = {}          # attr -> the expression that overwrites it
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            # `self.margin_x = 20` and a knob-named local (`pad = 10`) are both appearance values
            # a mode draws with. A bare `x = 480` is not: locals with coordinate names are layout
            # arithmetic, and auditing them would bury the list in one-off numbers.
            if isinstance(target, ast.Attribute):
                attr = target.attr
            elif isinstance(target, ast.Name) and any(
                    token in target.id.lower() for token in
                    _MARGIN_TOKENS + _GAP_TOKENS + ("font", "alpha", "colour", "color")):
                attr = target.id
            else:
                continue
            value = _literal(node.value)
            if value is not None:
                literal_hits.append((attr, value, node.lineno,
                                     lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""))
            elif isinstance(node.value, (ast.BinOp, ast.Call, ast.IfExp, ast.Subscript)):
                computed_attrs.setdefault(attr, ast.unparse(node.value))

    for attr, value, line, code in literal_hits:
        kind = _classify(attr, value)
        # 0/1/2/-1 (and 0.0/1.0) as a value is an index, a flag or a state initialiser, not a knob:
        # `self._fade_t = 0.0` is where a fade starts, not something to tune. Colours are the
        # exception (black and white are colours).
        trivial_number = (isinstance(value, (int, float)) and not isinstance(value, bool)
                          and value in (0, 1, 2, -1, 0.0, 1.0))
        if trivial_number and kind != "colour":
            result.trivial += 1
            continue
        candidate = Candidate(mode=mode, type_key=type_key, attr=attr, kind=kind, line=line,
                              code=code, literal=repr(value), profiles=profiles)
        # a literal that is later recomputed is a placeholder, not a knob — but the recomputation
        # is the interesting part, so it is named
        if attr in computed_attrs:
            candidate.status = "placeholder"
            candidate.detail = f"overwritten later by: {computed_attrs[attr]}"
            candidate.weight = KIND_WEIGHT.get(kind, 1) * 0.25
        else:
            candidate.status = "operative"
            candidate.suggestion = _suggest(attr, kind, value)
            candidate.weight = KIND_WEIGHT.get(kind, 1)
        result.candidates.append(candidate)

    # 3. magic numbers inside a computed appearance attribute: the ratio behind a derived size.
    #    Two things are NOT candidates here: an expression that reads config (already tunable), and
    #    one built from another attribute (a value derived from an existing knob, where a second
    #    knob would be two controls for one behaviour).
    for attr, expr in computed_attrs.items():
        kind = _classify(attr, None)
        if kind not in ("font_size", "margin", "gap") and "font" not in attr.lower() \
                and not any(t in attr.lower() for t in _MARGIN_TOKENS + _GAP_TOKENS):
            continue
        try:
            parsed = ast.parse(expr)
        except SyntaxError:
            continue
        if _parametrised(parsed, config_vars):
            continue
        if not _derived_from_screen_only(parsed, attr):
            continue
        numbers = [n for n in _numbers(parsed) if isinstance(n, float) and 0 < n < 1]
        if not numbers:
            continue
        candidate = Candidate(
            mode=mode, type_key=type_key, attr=attr, kind="ratio",
            code=f"{attr} = {expr}", literal=", ".join(repr(n) for n in numbers),
            status="operative",
            detail=_ratio_detail(parsed, numbers),
            suggestion=f"{attr} scale (number; current "
                       f"{' + '.join(repr(n) for n in numbers)})",
            profiles=profiles, weight=KIND_WEIGHT["ratio"])
        result.candidates.append(candidate)

    # 4. calls that take an appearance value directly (font sizes, alphas, fills)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else (
            node.func.id if isinstance(node.func, ast.Name) else "")
        if name in _FONT_SIZE_CALLS:
            index = _FONT_SIZE_CALLS[name]
            if len(node.args) > index:
                value = _literal(node.args[index])
                if value is not None:
                    result.candidates.append(Candidate(
                        mode=mode, type_key=type_key, attr=f"{name} size", kind="font_size",
                        line=node.lineno,
                        code=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                        literal=repr(value), status="operative",
                        detail="a literal font size at the call site",
                        suggestion="font_size (number; int pixels)", profiles=profiles,
                        weight=KIND_WEIGHT["font_size"]))
        if name == "set_alpha" and node.args:
            value = _literal(node.args[0])
            if value is not None:
                result.candidates.append(Candidate(
                    mode=mode, type_key=type_key, attr="alpha", kind="alpha", line=node.lineno,
                    code=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                    literal=repr(value), status="operative",
                    detail="a hardcoded transparency",
                    suggestion="alpha (number 0-255 or 0.0-1.0)", profiles=profiles,
                    weight=KIND_WEIGHT["alpha"]))
        if name in ("sleep", "delay") and node.args:
            value = _literal(node.args[0])
            if value is not None:
                result.candidates.append(Candidate(
                    mode=mode, type_key=type_key, attr=f"{name}()", kind="timing",
                    line=node.lineno,
                    code=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                    literal=repr(value), status="operative", detail="pacing",
                    suggestion="a timing param (number seconds)", profiles=profiles,
                    weight=KIND_WEIGHT["timing"]))

    return result


def mode_sources(base_dir: str, registry: dict) -> dict:
    """{mode_module: (source, type_key)} for every type in the registry, read from disk."""
    out = {}
    for type_key, spec in (registry or {}).items():
        entrypoint = (spec or {}).get("entrypoint", "")
        module_name = entrypoint.split(":")[0]
        rel = module_name.replace(".", os.sep) + ".py"
        path = os.path.join(base_dir, rel)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                source = fh.read()
        except OSError:
            continue
        out[os.path.basename(module_name)] = (source, type_key, path)
    return out


def usage_by_mode(profiles: dict) -> dict:
    """{mode type_key: [profile rel, ...]} — reach, so the review can rank by what matters."""
    used: dict = {}
    for rel, modes in (profiles or {}).items():
        for cfg in modes.values():
            if not isinstance(cfg, dict):
                continue
            key = str(cfg.get("type", "")).lower().replace(" ", "").replace("_", "")
            if key:
                used.setdefault(key, []).append(rel)
    return {k: tuple(sorted(v)) for k, v in used.items()}


def audit(base_dir: str, registry: dict, profiles: dict) -> dict:
    """
    Audit every mode module. Returns {"modes": [ModeAudit], "totals": {...}, "candidates": [...]}.

    `profiles` is {profile rel: {"<n>": instance cfg}} so each candidate can carry its reach.
    """
    usage = usage_by_mode(profiles)
    audits = []
    for mode, (source, type_key, path) in sorted(mode_sources(base_dir, registry).items()):
        try:
            audits.append(audit_source(source, mode=mode, type_key=type_key, path=path,
                                       profiles=usage.get(type_key, ())))
        except SyntaxError as e:                        # a module that will not parse is reported
            audits.append(ModeAudit(mode=mode, type_key=type_key, path=path,
                                    candidates=[Candidate(mode=mode, type_key=type_key,
                                                          attr="(unparsable)", kind="geometry",
                                                          detail=f"SyntaxError: {e}")]))

    candidates = [c for a in audits for c in a.candidates]
    operative = [c for c in candidates if c.status == "operative"]
    reviewable = [c for c in operative if c.kind != "geometry"]
    return {
        "modes": audits,
        "candidates": candidates,
        "totals": {
            "modules": len(audits),
            "candidates": len(candidates),
            "operative": len(operative),
            "worth_reviewing": len(reviewable),
            "placeholder": len([c for c in candidates if c.status == "placeholder"]),
            "skipped_trivial": sum(a.trivial for a in audits),
            "operative_in_used_modes": len([c for c in reviewable if c.profiles]),
            "by_kind": {kind: len([c for c in operative if c.kind == kind]) for kind in KINDS
                        if any(c.kind == kind for c in operative)},
            "modes_with_candidates": len([a for a in audits if a.candidates]),
        },
    }


def _as_result(value) -> dict:
    """
    Accept either audit()'s result dict or a single ModeAudit, so a caller (and a test) can group
    one module's candidates without wrapping it first.
    """
    if isinstance(value, dict):
        return value
    return {"candidates": list(getattr(value, "candidates", [])), "modes": [value], "totals": {}}


def group_candidates(audit_result, *, used_only: bool = True, include_geometry: bool = False,
                     kinds=None, limit: int | None = None) -> list:
    """
    One row per KNOB, not per literal.

    `_accent` assigned three different colours at three lines is one decision ("what colour is the
    accent, and does it change per state?"), not three. Grouping is what turns a 180-row list into
    something a person can review, and it keeps the distinct values visible so a state-dependent
    value is obvious instead of hidden behind a count.
    """
    groups: dict = {}
    for c in _as_result(audit_result)["candidates"]:
        if c.status != "operative":
            continue
        if c.kind == "geometry" and not include_geometry:
            continue
        if kinds and c.kind not in kinds:
            continue
        if used_only and not c.profiles:
            continue
        key = (c.mode, c.attr, c.kind)
        group = groups.get(key)
        if group is None:
            group = groups[key] = {
                "mode": c.mode, "type_key": c.type_key, "attr": c.attr, "kind": c.kind,
                "values": [], "lines": [], "profiles": c.profiles, "detail": c.detail,
                "code": c.code, "weight": c.weight,
            }
        if c.literal not in group["values"]:
            group["values"].append(c.literal)
        group["lines"].append(c.line)

    out = list(groups.values())
    for group in out:
        group["count"] = len(group["lines"])
        group["score"] = group["weight"] * (1 + 0.5 * len(group["profiles"]))
        group["suggestion"] = _group_suggestion(group)
    out.sort(key=lambda g: (-g["score"], g["mode"], g["attr"]))
    return out[:limit] if limit else out


def _group_suggestion(group: dict) -> str:
    kind, attr = group["kind"], group["attr"]
    values = group["values"]
    if kind == "colour":
        if len(values) > 1:
            return (f"{attr} (colour widget) — {len(values)} different values here, so this is a "
                    f"state accent: expose it as a colour, or as an accent + variants")
        return f"{attr} (colour widget; current {values[0]})"
    if kind == "ratio":
        return f"{attr} scale (number; current {' + '.join(values)})"
    if kind == "font_size":
        return f"{attr} (number; int pixels)"
    if kind == "timing":
        return f"{attr} (number; seconds)"
    if kind in ("margin", "gap"):
        return f"{attr} (number; int pixels — or a ratio if it should scale with the wall)"
    return f"{attr} (number)"


def rank(audit_result, *, used_only: bool = True, limit: int = 40,
         include_geometry: bool = False) -> list:
    """
    Worth reviewing first: operative values in a mode you actually use, weighted by kind.

    Coordinate literals are excluded by default. They are most of the raw count and almost never
    worth a knob (a one-off `x = w - 20` is an implementation detail, not a tuning control), and
    leaving them in buries the handful of values that decide how a wall looks.
    """
    scored = []
    for c in _as_result(audit_result)["candidates"]:
        if c.status != "operative":
            continue
        if c.kind == "geometry" and not include_geometry:
            continue
        if used_only and not c.profiles:
            continue
        score = c.weight * (1 + 0.5 * len(c.profiles))
        scored.append((score, c))
    scored.sort(key=lambda pair: (-pair[0], pair[1].mode, pair[1].attr))
    return [c for _score, c in scored[:limit]]


def render_report(audit_result: dict, *, top: int = 40) -> str:
    """The machine-generated part of the audit document (the review curates its top picks)."""
    totals = audit_result["totals"]
    lines = [
        "### Machine scan",
        "",
        f"- modules scanned: **{totals['modules']}**",
        f"- raw candidate values: **{totals['candidates']}** "
        f"({totals['operative']} operative, {totals['placeholder']} placeholders the mode itself "
        f"overwrites, {totals['skipped_trivial']} trivial 0/1/2/-1 values skipped)",
        f"- **worth reviewing** (operative, not a one-off coordinate): "
        f"**{totals['worth_reviewing']}**, of which {totals['operative_in_used_modes']} are in modes "
        f"a profile actually uses",
        f"- modes with at least one candidate: {totals['modes_with_candidates']}",
        "",
        "| kind | operative values |",
        "| --- | --- |",
    ]
    for kind, count in sorted(totals["by_kind"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {kind} | {count} |")
    lines += ["", f"### Knobs worth reviewing, by reach and kind "
                  f"(weight = kind x profiles using the mode)", "",
              "| mode | value | kind | literals | as written | suggested param | profiles |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for g in group_candidates(audit_result, limit=top):
        values = ", ".join(g["values"][:3]) + (" +more" if len(g["values"]) > 3 else "")
        code = g["code"].replace("|", "\\|")[:60]
        lines.append(f"| `{g['mode']}` | `{g['attr']}` | {g['kind']} | {values} | `{code}` | "
                     f"{g['suggestion']} | {len(g['profiles'])} |")
    return "\n".join(lines) + "\n"
