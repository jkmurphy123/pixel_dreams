# core/validation.py
#
# One implementation of "is this config valid?", used by BOTH the static validator
# (validate_configs.py, a dev/CI tool) and the panel before it writes anything.
#
# Two callers, one set of rules — deliberately. A second copy of these checks living in the panel
# would drift from the validator, and the panel is the one that can corrupt a kiosk's config at
# 2am, so it must be the stricter of the two rather than the looser.
#
# Issue levels mirror the tool's existing output, which people already read:
#   error   — the config cannot work (missing required key, unknown type, bad entrypoint)
#   warning — it probably works but is suspicious (typo'd key, unnormalized type name, a relative
#             data file that is not there)
#
# Pure Python, no pygame, no nicegui: importable from the panel thread, a test, or CI.

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass

from .config import COMMON_INSTANCE_KEYS, infer_max_modes_from_config, normalize_type

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    level: str
    message: str
    mode_key: str = ""
    type_key: str = ""
    key: str = ""

    @property
    def is_error(self) -> bool:
        return self.level == ERROR

    def render(self) -> str:
        """The line shape the validator has always printed."""
        where = f"mode {self.mode_key} ({self.type_key})" if self.mode_key else (
            f"type '{self.type_key}'" if self.type_key else "")
        head = f"{where}: " if where else ""
        if self.is_error:
            return f"  ERROR: {head}{self.message}"
        return f"  warn:  {head}{self.message}"


def errors(issues) -> list:
    return [i for i in issues if i.is_error]


def warnings(issues) -> list:
    return [i for i in issues if not i.is_error]


# ---------------------------------------------------------------- registry

def validate_registry(registry_json: dict, *, check_imports: bool = True) -> list:
    """Validate the registry document itself (types, entrypoints, secret hygiene)."""
    issues: list = []
    types = registry_json.get("types") if isinstance(registry_json, dict) else None
    if not isinstance(types, dict) or not types:
        return [Issue(ERROR, "registry has no 'types' dict (or it is empty)")]

    for type_key, spec in types.items():
        if not isinstance(spec, dict):
            issues.append(Issue(ERROR, "entry is not an object", type_key=type_key))
            continue

        entrypoint = spec.get("entrypoint")
        if not entrypoint:
            issues.append(Issue(ERROR, "missing 'entrypoint'", type_key=type_key))
            continue
        if ":" not in entrypoint:
            issues.append(Issue(ERROR, f"entrypoint '{entrypoint}' lacks 'module:Class' form",
                                type_key=type_key))
            continue

        if check_imports:
            module_name, class_name = entrypoint.split(":", 1)
            try:
                module = importlib.import_module(module_name)
            except Exception as e:  # noqa: BLE001 - reported, not raised
                issues.append(Issue(ERROR, f"cannot import module '{module_name}': {e}",
                                    type_key=type_key))
                continue
            if not hasattr(module, class_name):
                issues.append(Issue(ERROR, f"module '{module_name}' has no class '{class_name}'",
                                    type_key=type_key))

        if normalize_type(type_key) != type_key:
            issues.append(Issue(WARNING,
                                f"key is not in normalized form ('{normalize_type(type_key)}')",
                                type_key=type_key))

        for key in spec.get("type_config", {}) or {}:
            if any(word in key for word in ("api_key", "secret", "token")):
                issues.append(Issue(WARNING,
                                    f"type_config contains '{key}' — secrets belong in "
                                    f"secrets.json or env vars", type_key=type_key))
    return issues


# ---------------------------------------------------------------- one mode instance

def validate_instance(mode_key, cfg, registry: dict, *, base_dir: str | None = None) -> list:
    """Every rule that applies to one mode instance in one profile."""
    issues: list = []
    mode_key = str(mode_key)

    if not mode_key.isdigit():
        return [Issue(WARNING, f"mode key '{mode_key}' is not numeric — it will never be loaded")]

    if not isinstance(cfg, dict):
        return [Issue(ERROR, "config is not an object", mode_key=mode_key)]

    raw_type = cfg.get("type")
    if not raw_type:
        return [Issue(ERROR, "missing 'type'", mode_key=mode_key)]

    type_key = normalize_type(raw_type)
    spec = registry.get(type_key)
    if spec is None:
        return [Issue(ERROR, f"unknown type '{raw_type}' (normalized '{type_key}')",
                      mode_key=mode_key, type_key=type_key)]

    required = spec.get("required", [])
    missing = [k for k in required if k not in cfg]
    if missing:
        issues.append(Issue(ERROR, f"missing required keys: {missing}",
                            mode_key=mode_key, type_key=type_key))

    known = set(required) | set(spec.get("optional", [])) | set(COMMON_INSTANCE_KEYS)
    for key in cfg:
        if key not in known:
            issues.append(Issue(WARNING,
                                f"unknown key '{key}' (not in required/optional for this type)",
                                mode_key=mode_key, type_key=type_key, key=key))

    if "enabled" in cfg and not isinstance(cfg["enabled"], bool):
        issues.append(Issue(WARNING,
                            f"'enabled' is {cfg['enabled']!r} — it must be true/false (JSON "
                            f"booleans); anything else is treated as enabled",
                            mode_key=mode_key, type_key=type_key, key="enabled"))

    if base_dir:
        for key in ("file", "data_file", "quotes_file"):
            value = cfg.get(key)
            if isinstance(value, str) and value and not os.path.isabs(value):
                if not os.path.exists(os.path.join(base_dir, value)):
                    issues.append(Issue(WARNING,
                                        f"'{key}' -> '{value}' not found relative to project root",
                                        mode_key=mode_key, type_key=type_key, key=key))
    return issues


# ---------------------------------------------------------------- a whole profile

def validate_profile(modes_config: dict, registry: dict, *, base_dir: str | None = None) -> list:
    """
    Every mode in a profile. `modes_config` is the {"<number>": {...}} mapping, already merged
    with any local override, so what is validated is what will actually run.
    """
    issues: list = []
    if not modes_config:
        return [Issue(ERROR, "no 'modes' found (or file missing/invalid)")]

    for mode_key, cfg in sorted(modes_config.items(),
                                key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 10 ** 9):
        issues.extend(validate_instance(mode_key, cfg, registry, base_dir=base_dir))
    return issues


def summarise(modes_config: dict) -> dict:
    """Small facts a caller wants alongside the issues (used by the panel's status page)."""
    indices = sorted(int(k) for k in (modes_config or {}) if str(k).isdigit())
    return {
        "count": len(indices),
        "max_modes": infer_max_modes_from_config(modes_config or {}),
        "indices": indices,
    }
