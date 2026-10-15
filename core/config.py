# core/config.py
#
# Config loading for pixel_dreams (forked from pixel_drift).
#
# Load order for a mode's effective config:
#   registry type_config  ->  modes_config.json instance  ->  modes_config.local.json instance
#
# Secrets never live in versioned JSON. They come from (in priority order):
#   1. secrets.json (gitignored) at the project root: {"OPENAI_API_KEY": "..."}
#   2. environment variables (e.g. OPENAI_API_KEY)

import json
import os

DEFAULT_MAX_MODES = 8
LOCAL_CONFIG_NAME = "modes_config.local.json"
SECRETS_NAME = "secrets.json"

# Keys in a mode instance that are structural, not per-type parameters.
COMMON_INSTANCE_KEYS = {"type", "name", "title", "duration", "enabled"}

# Of those, the ones that describe the SLOT rather than the mode's behaviour, so they must never
# render as an editable parameter in the panel. `duration` is deliberately NOT here: it is a real,
# useful per-instance parameter (how long the mode shows) that the panel should let you tune.
NON_PARAM_KEYS = {"type", "name", "title", "enabled"}


def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        print(f"[Config] Failed to load {path}: {e}")
        return default


def normalize_type(t):
    return str(t).strip().lower().replace(" ", "").replace("_", "")


def resolve_config_path(base_dir: str, filename_or_path: str) -> str:
    """
    Allow the registry to specify either:
      - a filename relative to base_dir (recommended), or
      - an absolute path (useful if configs live elsewhere)
    """
    if not filename_or_path:
        return os.path.join(base_dir, "modes_config.json")
    if os.path.isabs(filename_or_path):
        return filename_or_path
    return os.path.join(base_dir, filename_or_path)


def infer_max_modes_from_config(cfg_dict: dict) -> int:
    if not cfg_dict:
        return DEFAULT_MAX_MODES
    digit_keys = [int(k) for k in cfg_dict.keys() if str(k).isdigit()]
    if not digit_keys:
        return DEFAULT_MAX_MODES
    return max(digit_keys) + 1


def config_digest(cfg) -> str:
    """
    A stable hash of one mode's config.

    Why it exists: after a save the panel wants to say "the wall is showing this config" instead of
    being taken on trust. The controller records the digest at the moment it BUILDS a mode, so
    comparing it with the file's proves the running process really did pick up the new values (or
    still has the old ones).
    """
    import hashlib

    blob = json.dumps(cfg if isinstance(cfg, dict) else {}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _is_disabled(cfg) -> bool:
    """
    True only for an explicit false. Strict on purpose: `"enabled": "false"` (a string) must not
    silently remove a mode from the rotation — the validator warns about it instead, so the
    mistake is visible rather than acted upon.
    """
    return isinstance(cfg, dict) and cfg.get("enabled") is False


def enabled_mode_indices(modes_cfg: dict):
    """
    The mode indices a rotation may use, honouring each mode's "enabled" flag (absent = enabled).

    Returns (indices, fell_back). If EVERY mode is disabled the caller gets all of them plus
    fell_back=True, so a typo cannot leave a kiosk showing nothing — and the caller has a reason
    to say so loudly instead of the wall just going blank.
    """
    if not modes_cfg:
        return [], False
    all_indices = sorted(int(k) for k in modes_cfg if str(k).isdigit())
    enabled = [i for i in all_indices if not _is_disabled(modes_cfg.get(str(i)))]
    if all_indices and not enabled:
        return all_indices, True
    return enabled, False


def list_configured_modes(modes_cfg: dict, modes_config_file: str):
    if not modes_cfg:
        print("[Modes] No modes found in config.")
        return
    keys = sorted(int(k) for k in modes_cfg.keys() if str(k).isdigit())
    print(f"[Modes] Found {len(keys)} configured mode(s) in {os.path.basename(modes_config_file)}:")
    for k in keys:
        cfg = modes_cfg.get(str(k), {})
        t = cfg.get("type", "?")
        name = cfg.get("name") or cfg.get("title") or ""
        extra = f" - {name}" if name else ""
        print(f"  {k}: {t}{extra}")


def load_secrets(base_dir: str) -> dict:
    """
    Secrets available for injection into mode configs.
    secrets.json wins over environment variables.
    """
    secrets = {}

    # Environment first (lowest priority)
    for key in ("OPENAI_API_KEY", "PANEL_TOKEN"):
        val = os.environ.get(key)
        if val:
            secrets[key.lower()] = val  # e.g. secrets["openai_api_key"], secrets["panel_token"]

    # Untracked secrets.json overrides env
    raw = load_json(os.path.join(base_dir, SECRETS_NAME), {})
    for key, val in raw.items():
        if isinstance(val, str) and val:
            secrets[key.lower()] = val

    return secrets


def load_project_config(base_dir: str, config_override: str = None):
    """
    Load registry + modes config (+ optional local override).

    Returns:
        registry_json (dict): full registry document
        registry (dict):      registry["types"]
        modes_config (dict):  merged instance configs keyed by mode number string
        config_path (str):    path of the primary modes config used
    """
    registry_file = os.path.join(base_dir, "modes_registry.json")
    registry_json = load_json(registry_file, {})
    registry = registry_json.get("types", {})

    settings = registry_json.get("settings", {})
    config_name = config_override or settings.get("modes_config_file", "modes_config.json")
    config_path = resolve_config_path(base_dir, config_name)
    print(f"[Config] Using modes config: {config_path}")

    modes_config = load_json(config_path, {}).get("modes", {})

    # Optional per-host override, gitignored. Instance-level shallow merge:
    # local["modes"]["3"]["folder"] overrides the base value for mode 3.
    local_path = os.path.join(base_dir, LOCAL_CONFIG_NAME)
    local = load_json(local_path, {})
    local_modes = local.get("modes", {}) if isinstance(local, dict) else {}
    if local_modes:
        print(f"[Config] Applying local override: {local_path}")
        for mode_key, override_cfg in local_modes.items():
            base_cfg = modes_config.get(mode_key, {})
            if isinstance(base_cfg, dict) and isinstance(override_cfg, dict):
                merged = dict(base_cfg)
                merged.update(override_cfg)
                modes_config[mode_key] = merged
            else:
                modes_config[mode_key] = override_cfg

    return registry_json, registry, modes_config, config_path
