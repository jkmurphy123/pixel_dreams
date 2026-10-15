# core/profiles.py
#
# Profiles: one modes config file per display orientation.
#
#   modes_config.json              the default profile (project root)
#   configs/modes_config_*.json    orientation variants (portrait, landscape, narrow_*, ...)
#
# A profile file has the same shape as any modes config:
#
#   {
#     "profile": { "label": "...", "resolution": [1080, 1920], "notes": "..." },   # optional
#     "modes":   { "7": { "type": "dungeon", "seed": 42 } }
#   }
#
# The optional "profile" block is ignored by the controller and used only for display; it
# exists so a dropdown can read "Portrait 1080x1920 wall" instead of a filename.
#
# This module is deliberately importable with no display, no pygame and no NiceGUI: the
# controller uses it at startup and the panel uses it to list things.
#
# IMPORTANT: mode numbers are SLOT numbers inside one profile, not global identities.
# Landscape has 9 modes, portrait has 24, and the numbers do not line up between them, so
# anything that identifies a mode must carry (profile, number) together.

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

from .config import LOCAL_CONFIG_NAME, NON_PARAM_KEYS, load_json, normalize_type

PROFILES_DIRNAME = "configs"
DEFAULT_PROFILE_NAME = "modes_config.json"


@dataclass
class ModeEntry:
    """One mode instance inside one profile, as written on disk (plus override info)."""

    number: int
    type: str                          # as written: "SystemInformation"
    type_key: str                      # normalised: "systeminformation"
    label: str = ""                    # "name" or "title" if present
    params: dict = field(default_factory=dict)     # this instance's own keys/values
    override_keys: tuple = ()          # keys the local override layer supplies
    enabled: bool = True               # "enabled": false opts the mode out of the rotation


@dataclass(frozen=True)
class ProfileInfo:
    path: str
    rel: str
    name: str
    label: str
    resolution: str = ""
    notes: str = ""
    mode_count: int = 0
    active: bool = False
    error: str = ""


def derive_label(filename: str) -> str:
    """'modes_config_portrait.json' -> 'portrait'; 'modes_config.json' -> 'default'."""
    stem = filename[:-5] if filename.endswith(".json") else filename
    stem = stem.replace("modes_config", "")
    stem = stem.strip("._- ")
    if not stem:
        return "default"
    return stem.replace("_", " ")


def _format_resolution(value) -> str:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return f"{value[0]}x{value[1]}"
    if isinstance(value, str):
        return value
    return ""


def load_local_overrides(base_dir: str) -> dict:
    """The per-host override layer, keyed by mode number (may be empty)."""
    raw = load_json(os.path.join(base_dir, LOCAL_CONFIG_NAME), {})
    if not isinstance(raw, dict):
        return {}
    modes = raw.get("modes", {})
    return modes if isinstance(modes, dict) else {}


def merge_local_override(modes: dict, local_modes: dict) -> tuple[dict, dict]:
    """
    Apply the local override layer the same way core.config does at startup, and report
    which keys each mode number takes from the override (a shadowed value that is edited in
    the profile but has no effect — the panel has to be able to say so).

    Returns (merged_modes, {mode_key: [override_key, ...]}).
    """
    merged = {k: (dict(v) if isinstance(v, dict) else v) for k, v in (modes or {}).items()}
    overridden: dict[str, list[str]] = {}
    for key, override in (local_modes or {}).items():
        if not isinstance(override, dict):
            continue
        base = merged.get(key)
        if isinstance(base, dict):
            merged[key] = {**base, **override}
        else:
            merged[key] = dict(override)
        overridden[str(key)] = sorted(override.keys())
    return merged, overridden


def profile_modes(path: str) -> tuple[dict, dict]:
    """
    Read one profile file. Returns (modes_dict, profile_metadata).
    A missing or malformed file yields ({}, {}) — callers render the error, not a crash.
    """
    raw = load_json(path, {})
    if not isinstance(raw, dict):
        return {}, {}
    modes = raw.get("modes", {})
    meta = raw.get("profile", {})
    return (modes if isinstance(modes, dict) else {},
            meta if isinstance(meta, dict) else {})


def mode_entries(modes: dict, overridden: dict | None = None) -> list[ModeEntry]:
    """Sorted ModeEntry list for one profile's modes dict."""
    overridden = overridden or {}
    entries = []
    for key, cfg in (modes or {}).items():
        if not str(key).isdigit() or not isinstance(cfg, dict):
            continue
        raw_type = str(cfg.get("type", ""))
        label = cfg.get("name") or cfg.get("title") or ""
        entries.append(ModeEntry(
            number=int(key),
            type=raw_type,
            type_key=normalize_type(raw_type),
            label=str(label),
            params={k: v for k, v in cfg.items() if k not in NON_PARAM_KEYS},
            override_keys=tuple(overridden.get(str(key), ())),
            enabled=cfg.get("enabled") is not False,
        ))
    entries.sort(key=lambda e: e.number)
    return entries


def discover_profiles(base_dir: str, active_path: str | None = None) -> list[ProfileInfo]:
    """
    Every profile we know about: the root modes_config.json plus configs/*.json.

    Read-only. Malformed files are reported as an `error` rather than raised, because the
    panel must render even when one profile is broken (that is exactly when you need it).
    """
    active_real = os.path.realpath(active_path) if active_path else None
    candidates = []
    root = os.path.join(base_dir, DEFAULT_PROFILE_NAME)
    if os.path.exists(root):
        candidates.append(root)
    candidates.extend(sorted(glob.glob(os.path.join(base_dir, PROFILES_DIRNAME, "*.json"))))

    infos = []
    for path in candidates:
        name = os.path.basename(path)
        rel = os.path.relpath(path, base_dir)
        meta_modes, meta = profile_modes(path)
        error = ""
        if not meta_modes:
            error = "no modes found (missing or malformed JSON)"
        infos.append(ProfileInfo(
            path=os.path.abspath(path),
            rel=rel,
            name=name,
            label=str(meta.get("label") or derive_label(name)),
            resolution=_format_resolution(meta.get("resolution")),
            notes=str(meta.get("notes") or ""),
            mode_count=len([k for k in meta_modes if str(k).isdigit()]),
            active=(active_real is not None and os.path.realpath(path) == active_real),
            error=error,
        ))
    return infos


def resolve_active_profile(base_dir: str, config_override: str | None = None) -> tuple[str, str]:
    """
    Which profile the running app is using, and why.
        --config FILE  >  runtime/active_profile.json  >  registry settings  >  modes_config.json
    Returns (absolute path, source) with source in {"cli", "runtime", "registry", "default"}.

    Thin delegate: the resolution itself lives in core.config, next to the loader that must obey
    it, so the app, the panel and the switcher can never disagree about which profile is active.
    """
    from .config import resolve_active_profile as _resolve   # local import: module stays light

    return _resolve(base_dir, config_override)
