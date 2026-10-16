# core/editor.py
#
# Editing one profile file: stage changes, validate them, write them atomically.
#
# The panel owns the UI; this module owns the RULES about changing a config on disk. It exists
# because "write some JSON" is the one operation in this project that can leave a kiosk dead, and
# the rules are worth having in one place with tests rather than spread through button handlers.
#
# What it enforces (design §7):
#   * stage, don't write. A Save writes once; Cancel/Revert just drops staged state and costs
#     nothing. Nothing touches the disk before Save.
#   * validate the WHOLE profile, not just the edited mode. Removing a required key breaks a mode,
#     and two modes sharing a type can interact (a schema change is checked against both).
#   * validate each value against its field: shape, range, and closed value sets — so a text box
#     cannot store a value the mode will choke on.
#   * refuse a key the untracked local override supplies. That value does not come from this file,
#     so writing it here would look like it worked and change nothing.
#   * refuse to clobber a file that changed since we read it, and say WHAT changed instead.
#   * write atomically with a backup, and only report success once the bytes are verified.
#
# No pygame, no nicegui, no display: the panel calls this from its own thread. The render loop
# never imports it — it only ever receives finished dicts over the bus.

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from datetime import datetime

from .config import (
    LOCAL_CONFIG_NAME,
    active_profile_file,
    load_json,
    load_project_config,
    normalize_type,
    resolve_active_profile,
    write_active_profile,
)
from .params import resolve_params, validate_param_value
from .profiles import PROFILES_DIRNAME
from .store import WriteVerificationError, atomic_write_json, sha256_file
from .validation import ERROR, Issue, validate_profile


class EditorRefused(Exception):
    """A change the editor will not stage (e.g. a key supplied by the local override)."""


@dataclass
class SwitchResult:
    """The outcome of making a different profile active."""

    ok: bool
    reason: str = ""
    errors: tuple = ()
    warnings: tuple = ()
    profile: str = ""                 # relative to base_dir, as recorded
    profile_abs: str = ""
    runtime_file: str = ""
    payload: dict = field(default_factory=dict)     # what the render loop needs


def default_backup_dir(path: str) -> str:
    """Where writes of `path` put their backups (same convention as core.store)."""
    return os.path.join(os.path.dirname(os.path.abspath(path)), ".backups")


def list_backups(path: str, backup_dir: str | None = None) -> list:
    """
    Newest first. Each entry: {name, path, bytes, sha256, stamp, when}.

    `stamp` is the sortable token from the filename; `when` is it rendered for a human. Only files
    belonging to THIS target are listed (the directory holds backups for every profile and the
    registry).
    """
    directory = backup_dir or default_backup_dir(path)
    stem = os.path.basename(path)
    if not os.path.isdir(directory):
        return []
    out = []
    for name in sorted(os.listdir(directory), reverse=True):
        if not (name.startswith(stem + ".") and name.endswith(".bak")):
            continue
        full = os.path.join(directory, name)
        stamp = name[len(stem) + 1:-len(".bak")]
        when = stamp
        try:
            when = datetime.strptime(stamp, "%Y%m%dT%H%M%S_%fZ").strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
        try:
            size = os.path.getsize(full)
        except OSError:
            size = 0
        out.append({"name": name, "path": full, "bytes": size, "stamp": stamp, "when": when,
                    "sha256": sha256_file(full) if os.path.exists(full) else ""})
    return out


@dataclass
class StagedEdit:
    """Everything staged for ONE mode, none of it on disk yet."""

    number: int
    sets: dict = field(default_factory=dict)
    removes: list = field(default_factory=list)
    enabled: bool | None = None

    @property
    def empty(self) -> bool:
        return not self.sets and not self.removes and self.enabled is None

    def describe(self) -> str:
        bits = [f"{k} = {v!r}" for k, v in self.sets.items()]
        bits += [f"{k} removed" for k in self.removes]
        if self.enabled is not None:
            bits.append("enabled (the key is removed)" if self.enabled else "disabled")
        return "; ".join(bits)


@dataclass
class Validation:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    by_mode: dict = field(default_factory=dict)     # mode number (str) -> issues, for inline display

    @property
    def ok(self) -> bool:
        return not self.errors

    def messages(self, limit: int = 8) -> list:
        return [i.render().strip() for i in self.errors[:limit]]


@dataclass
class SaveResult:
    ok: bool
    reason: str = ""
    conflict: bool = False
    errors: tuple = ()
    warnings: tuple = ()
    modes: tuple = ()
    path: str = ""
    sha256: str = ""
    backup: str = ""

    @property
    def wrote_anything(self) -> bool:
        return self.ok and bool(self.sha256)


class ProfileEditor:
    """
    One editing session over one profile file.

    The panel keeps one of these per browser session, so two people editing two profiles cannot
    tread on each other, and a stale session discovers the conflict instead of overwriting.
    """

    def __init__(self, base_dir: str, profile_path: str, registry: dict, *, overridden=None):
        self.base_dir = os.path.abspath(base_dir)
        self.path = os.path.abspath(profile_path)
        self.registry = registry or {}
        self.overridden = dict(overridden or {})     # {mode key: (keys the local override supplies)}
        self.document = self._read()
        self.baseline_sha = sha256_file(self.path) if os.path.exists(self.path) else ""
        self.staged: dict[int, StagedEdit] = {}
        self.last_backup = ""
        #: Set by stage_document() (the raw-JSON editor): it replaces the document wholesale.
        self.document_override = None

    # ---------------------------------------------------------------- reading

    def _read(self) -> dict:
        doc = load_json(self.path, {})
        return doc if isinstance(doc, dict) else {}

    def modes(self) -> dict:
        modes = self.document.get("modes")
        return modes if isinstance(modes, dict) else {}

    def mode_config(self, number) -> dict:
        cfg = self.modes().get(str(int(number)))
        return cfg if isinstance(cfg, dict) else {}

    def mode_in_file(self, number) -> bool:
        """False for a mode that only exists in the local override — there is nothing to edit."""
        return str(int(number)) in self.modes()

    def edit(self, number) -> StagedEdit:
        number = int(number)
        if number not in self.staged:
            self.staged[number] = StagedEdit(number=number)
        return self.staged[number]

    # ---------------------------------------------------------------- staging

    def _guard(self, number, key: str) -> None:
        if key in self.overridden.get(str(int(number)), ()):
            raise EditorRefused(
                f"'{key}' is supplied by {LOCAL_CONFIG_NAME}, which takes precedence over this "
                f"profile — edit it there instead, or the change here would do nothing")
        if key in ("type", "name", "title"):
            raise EditorRefused(f"'{key}' describes the slot, not the mode — it is not editable here")

    def stage_set(self, number, key: str, value) -> None:
        self._guard(number, key)
        state = self.edit(number)
        state.removes = [k for k in state.removes if k != key]
        state.sets[key] = value

    def stage_remove(self, number, key: str) -> None:
        self._guard(number, key)
        state = self.edit(number)
        if key in state.sets and key not in self.mode_config(number):
            # added in this session, now removed: the net change is nothing at all
            del state.sets[key]
            if state.empty:
                self.staged.pop(int(number), None)
            return
        if key not in self.mode_config(number):
            raise EditorRefused(f"'{key}' is not set in this profile, so there is nothing to remove")
        state.sets.pop(key, None)
        if key not in state.removes:
            state.removes.append(key)

    def stage_enabled(self, number, enabled: bool) -> None:
        if not self.mode_in_file(number):
            raise EditorRefused("this mode exists only in the local override, so it has no "
                                "'enabled' flag in this profile")
        self.edit(number).enabled = bool(enabled)

    def stage_document(self, document) -> None:
        """
        Replace the WHOLE document (used by the raw-JSON editor). Validated on save like anything
        else, and it supersedes any per-mode staging: you cannot half-edit a file one way and half
        the other and expect to know what you are saving.
        """
        if not isinstance(document, dict):
            raise EditorRefused("the document must be a JSON object")
        self.document_override = copy.deepcopy(document)
        self.staged.clear()

    def clear_document(self) -> None:
        self.document_override = None

    def reload_if_changed(self) -> bool:
        """
        Re-read the file when it changed underneath us, so a page that is merely DISPLAYING
        state (the switch, the digest note) does not claim something stale. Staged changes are
        kept: reload() here would throw away a form the user is half way through, which is why
        this is a separate method from reload().
        """
        if not self.is_stale():
            return False
        staged = self.staged
        self.document = self._read()
        self.baseline_sha = sha256_file(self.path) if os.path.exists(self.path) else ""
        self.staged = staged
        return True

    def unstage(self, number) -> None:
        self.staged.pop(int(number), None)

    def cancel_remove(self, number, key: str) -> None:
        """Undo a staged removal, so 'keep it after all' needs no poking at internals."""
        state = self.staged.get(int(number))
        if state is None:
            return
        state.removes = [k for k in state.removes if k != key]
        if state.empty:
            self.staged.pop(int(number), None)

    def revert_all(self) -> None:
        self.staged.clear()
        self.document_override = None

    def reload(self) -> None:
        """Drop staged changes AND re-read the file from disk (the way out of a conflict)."""
        self.document = self._read()
        self.baseline_sha = sha256_file(self.path) if os.path.exists(self.path) else ""
        self.staged.clear()

    # ---------------------------------------------------------------- what would be written

    def prospective(self) -> dict:
        """The document as it would be written right now. Deep copy; self.document is untouched."""
        if self.document_override is not None:
            return copy.deepcopy(self.document_override)
        doc = copy.deepcopy(self.document)
        modes = doc.setdefault("modes", {})
        if not isinstance(modes, dict):
            modes = doc["modes"] = {}
        for number, state in self.staged.items():
            key = str(int(number))
            cfg = modes.get(key)
            cfg = dict(cfg) if isinstance(cfg, dict) else {}
            for drop in state.removes:
                cfg.pop(drop, None)
            for k, v in state.sets.items():
                cfg[k] = v
            if state.enabled is not None:
                if state.enabled:
                    # "enabled" is the DEFAULT, so enabling REMOVES the key: a disable -> enable
                    # round trip then leaves the file exactly as it was found, instead of
                    # accumulating `"enabled": true` noise in a config a human reads.
                    cfg.pop("enabled", None)
                else:
                    cfg["enabled"] = False
            modes[key] = cfg
        return doc

    def is_dirty(self, number=None) -> bool:
        if self.document_override is not None:
            return self.document_override != self.document
        if number is None:
            return any(not s.empty for s in self.staged.values())
        return not self.staged.get(int(number), StagedEdit(int(number))).empty

    def changed_modes(self) -> list:
        if self.document_override is not None:
            before, after = self.modes(), (self.document_override.get("modes") or {})
            keys = set(before) | set(after)
            return sorted((int(k) for k in keys if str(k).isdigit()
                           and before.get(k) != after.get(k)))
        return sorted(n for n, s in self.staged.items() if not s.empty)

    def staged_summary(self) -> str:
        if self.document_override is not None:
            changed = self.changed_modes()
            return (f"the whole document was replaced (modes changed: {changed})"
                    if changed else "the whole document was replaced (no mode values differ)")
        return "; ".join(f"mode {n}: {self.staged[n].describe()}" for n in self.changed_modes())


    def is_stale(self) -> bool:
        """True when the file on disk is not the file this session read."""
        current = sha256_file(self.path) if os.path.exists(self.path) else ""
        return current != self.baseline_sha

    # ---------------------------------------------------------------- validation

    def validate(self) -> Validation:
        """
        Validate the profile AS IT WOULD BE WRITTEN.

        Field checks deliberately resolve their schema against the file's CURRENT values, not the
        staged ones: inferring the widget from the value the user just typed would make every value
        valid by construction (stage a number into a text field and the field would become a
        number). The schema and the stored value decide the shape; the staged value is what is
        being judged.
        """
        errors: list = []
        warnings: list = []
        doc = self.prospective()

        for issue in validate_profile(doc.get("modes", {}), self.registry, base_dir=self.base_dir):
            (errors if issue.is_error else warnings).append(issue)

        for number, state in self.staged.items():
            if state.empty:
                continue
            base_cfg = self.mode_config(number)
            type_key = normalize_type(str(base_cfg.get("type", "")))
            spec = self.registry.get(type_key)
            params, _ = resolve_params(base_cfg, spec, self.overridden.get(str(number), ()))
            by_key = {p.key: p for p in params}
            for key, value in state.sets.items():
                param = by_key.get(key)
                if param is None:
                    continue        # an undeclared key: validate_profile already warns about it
                for message in validate_param_value(param, value):
                    errors.append(Issue(ERROR, f"{key}: {message}", mode_key=str(number),
                                        type_key=type_key, key=key))

        by_mode: dict = {}
        for issue in list(errors) + list(warnings):
            by_mode.setdefault(issue.mode_key, []).append(issue)
        return Validation(errors=errors, warnings=warnings, by_mode=by_mode)

    def conflict_detail(self, limit: int = 6) -> str:
        """What changed on disk since we read it — the reason a save was refused, in words."""
        other = self._read()
        differences = []
        mine, theirs = self.modes(), (other.get("modes") or {})
        for key in sorted(set(mine) | set(theirs), key=lambda k: int(k) if str(k).isdigit() else 10 ** 9):
            a, b = mine.get(key, {}), theirs.get(key, {})
            if a == b:
                continue
            if not isinstance(a, dict) or not isinstance(b, dict):
                differences.append(f"mode {key}")
                continue
            changed = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
            differences.append(f"mode {key} ({', '.join(sorted(changed)[:4])})")
        if differences:
            extra = "" if len(differences) <= limit else f" and {len(differences) - limit} more"
            return "; ".join(differences[:limit]) + extra
        return "the file changed but its modes look the same (whitespace or an unrelated key)"

    # ---------------------------------------------------------------- writing

    def save(self, *, force: bool = False) -> SaveResult:
        """Validate and write. Nothing is written unless every check passes."""
        if not self.is_dirty():
            return SaveResult(ok=True, reason="nothing to save — no file was written")

        if not force and self.is_stale():
            return SaveResult(
                ok=False, conflict=True,
                reason="the file changed on disk since this form was loaded, so saving would "
                       "overwrite someone else's change — reload and re-apply",
                )

        validation = self.validate()
        if validation.errors:
            return SaveResult(ok=False, reason="validation failed — nothing was written",
                              errors=tuple(validation.messages()),
                              warnings=tuple(i.render().strip() for i in validation.warnings))

        changed = self.changed_modes()
        doc = self.prospective()
        try:
            report = atomic_write_json(self.path, doc, backup=True)
        except WriteVerificationError as e:
            return SaveResult(ok=False, reason=f"write could not be verified: {e}")
        except (TypeError, ValueError) as e:
            # a value JSON cannot represent (a set, a tuple key...) must be a refusal, not a 500
            return SaveResult(ok=False, reason=f"a value cannot be saved as JSON: {e}")
        except OSError as e:
            return SaveResult(ok=False, reason=f"could not write {self.path}: {e}")

        # Our own write is the new baseline, so a second save does not look like a conflict.
        self.document = doc
        self.baseline_sha = report["sha256"]
        self.last_backup = report.get("backup") or ""
        self.staged.clear()

        return SaveResult(
            ok=True,
            reason=f"saved {len(changed)} mode(s)",
            modes=tuple(changed),
            path=report["path"],
            sha256=report["sha256"],
            backup=self.last_backup,
            warnings=tuple(i.render().strip() for i in validation.warnings),
        )


def restore_backup(path: str, backup: str, *, registry: dict, base_dir: str | None = None) -> SaveResult:
    """
    Put a backup back as the live profile.

    Validated FIRST: a backup may predate a type or schema change, and restoring it straight over
    the live file is how a rollback becomes an outage. The write then goes through the same atomic
    path, which backs up the CURRENT file first — so a restore is itself undoable.
    """
    if not os.path.exists(backup):
        return SaveResult(ok=False, reason=f"no such backup: {backup}")
    doc = load_json(backup, None)
    if not isinstance(doc, dict) or not isinstance(doc.get("modes"), dict):
        return SaveResult(ok=False,
                          reason=f"{os.path.basename(backup)} is not a profile document")
    issues = validate_profile(doc["modes"], registry,
                              base_dir=base_dir or os.path.dirname(os.path.abspath(path)))
    blocking = [i for i in issues if i.is_error]
    if blocking:
        return SaveResult(
            ok=False,
            reason=f"{os.path.basename(backup)} does not validate, so nothing was restored",
            errors=tuple(i.render().strip() for i in blocking))
    try:
        report = atomic_write_json(path, doc, backup=True)
    except (WriteVerificationError, OSError, TypeError, ValueError) as e:
        return SaveResult(ok=False, reason=f"could not restore: {e}")
    return SaveResult(ok=True, reason=f"restored {os.path.basename(backup)}",
                      path=report["path"], sha256=report["sha256"],
                      backup=report.get("backup") or "",
                      warnings=tuple(i.render().strip() for i in issues if not i.is_error))


def switch_profile(base_dir: str, profile_path: str, registry: dict, *,
                   config_override: str | None = None) -> SwitchResult:
    """
    Make `profile_path` the active profile: validate it, record it in runtime/active_profile.json,
    and hand back the payload the render loop needs to switch over.

    Refused — with nothing written and nothing applied — when:
      * the app was started with --config. That flag outranks the recorded profile at every restart,
        so a switch here would look like it worked and be gone at the next boot: better to say so.
      * the target is missing or is not a profile.
      * the profile has validation ERRORS. A switch must not be able to put a broken profile on the
        wall, which is the same rule the writer follows for edits.
    """
    if config_override:
        return SwitchResult(
            ok=False,
            reason=f"this app was started with --config {config_override}, which always wins over "
                   f"the recorded profile — restart it without --config to switch from here")

    path = (os.path.abspath(profile_path) if os.path.isabs(profile_path)
            else os.path.abspath(os.path.join(base_dir, profile_path)))
    if not os.path.exists(path):
        return SwitchResult(ok=False, reason=f"no such profile file: {path}")

    modes = load_json(path, {}).get("modes")
    if not isinstance(modes, dict) or not modes:
        return SwitchResult(ok=False,
                            reason=f"{os.path.basename(path)} has no 'modes' — not a profile")

    issues = validate_profile(modes, registry, base_dir=base_dir)
    blocking = [i for i in issues if i.is_error]
    if blocking:
        return SwitchResult(
            ok=False,
            reason="this profile does not validate, so it was not made active — a switch must not "
                   "put a broken profile on the wall",
            errors=tuple(i.render().strip() for i in blocking))

    report = write_active_profile(base_dir, path)
    return SwitchResult(
        ok=True,
        reason=f"{os.path.basename(path)} is now the active profile",
        profile=report["profile"],
        profile_abs=path,
        runtime_file=active_profile_file(base_dir),
        payload=load_payload(base_dir, path),
        warnings=tuple(i.render().strip() for i in issues if not i.is_error))


# ---------------------------------------------------------------- creating a new profile
#
# "New config" is a CREATE, and it is the only writer path here that makes a file rather than
# changing one. Two rules follow from that, and both are about not producing an unusable profile:
#   * anything it writes goes through the same validation + atomic write as an edit, so a new file
#     cannot be born broken;
#   * a mode the registry declares but whose required keys cannot be filled is LEFT OUT and named in
#     the result, rather than written as an empty entry the app would then fail to build (and rather
#     than guessing a value from the key's name, which is exactly what the param layer refuses to do).

PROFILE_SUFFIX = ".json"
_NAME_ALLOWED = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


@dataclass
class CreateResult:
    """The outcome of creating a new profile file."""

    ok: bool
    reason: str = ""
    path: str = ""                     # absolute
    rel: str = ""                      # relative to base_dir, as the panel lists it
    sha256: str = ""
    modes: int = 0
    types: tuple = ()                  # every type included, in file order
    inherited: tuple = ()              # types whose tuned values came from the seed profile
    at_defaults: tuple = ()            # types included at registry defaults
    placeholders: tuple = ()           # "type.key" required values that are empty or null
    left_out: tuple = ()               # (type, (keys...)) that could not be created validly
    seed: str = ""                     # which profile the tuned values came from
    switched: "SwitchResult | None" = None
    errors: tuple = ()
    warnings: tuple = ()


def safe_profile_name(name: str) -> tuple:
    """
    (filename, problem) for a user-supplied profile name.

    A create writes a new file into the project, so the name is restricted rather than sanitised:
    anything with a path separator, a leading dot, a `..`, or a character outside `[A-Za-z0-9._-]`
    is REFUSED with the reason shown, not quietly rewritten into something else. A silent rename
    would leave the user looking for a file under the name they typed. `.json` is appended when it
    is missing, because that is the only extension the app will load.
    """
    raw = (name or "").strip()
    if not raw:
        return "", "give the new config a name"
    # Checked before the leading-dot rule: '../evil.json' and 'a/b.json' both contain a separator,
    # and "that is not allowed in a name" is the reason a user needs to see, not "starts with a dot".
    if any(ch not in _NAME_ALLOWED for ch in raw):
        return "", (f"{raw!r} contains characters that are not allowed in a profile name "
                    f"(use letters, digits, dot, dash, underscore — no slashes, spaces or tildes)")
    if raw.startswith("."):
        return "", f"{raw!r} starts with a dot — hidden files are not profiles"
    if not raw.lower().endswith(PROFILE_SUFFIX):
        raw += PROFILE_SUFFIX
    if len(raw) > 100:
        return "", "that name is too long (100 characters max)"
    return raw, ""


def _type_specs(registry) -> dict:
    """
    The `types` mapping out of whatever the caller has.

    Three shapes meet at this boundary: the panel's `_load_registry` hands out the `types` MAPPING,
    the file on disk is the whole document, and `validate_profile` wants the mapping. Normalising in
    one place beats remembering which one each caller passes — getting it wrong is not loud, it just
    reports every type as unknown.
    """
    if not isinstance(registry, dict):
        return {}
    types = registry.get("types", registry)
    return types if isinstance(types, dict) else {}


def build_full_profile(registry: dict, seed_modes: dict | None = None) -> tuple:
    """
    Every mode the registry knows, as a profile document body.

    Returns `(modes, report)`. Pure — no disk access — so the RULES are testable without a project
    directory, which is the part worth testing: which types appear, what they are seeded with, and
    which ones could not be created at all.

    * A type the seed profile already has is copied VERBATIM (its tuned values, its own `type`
      spelling, its `enabled` state). Copying is what makes a new orientation start from the values
      already adjusted rather than from nothing.
    * A type the seed does not have gets its REQUIRED keys only, filled from the schema's recorded
      defaults. Everything else is left unset on purpose: an unset key is a key the mode itself
      decides, and the panel shows it as "not set in this profile". Filling all 409 declared keys
      would invent settings the user never chose.
    * A required key with no recorded default cannot be filled honestly, so its whole type is left
      out and reported. Writing `null`, or guessing from the key's name, would produce a mode that
      looks configured and is not.
    * A default that exists but is empty (`""`, `[]`, `{}`, `null`) IS written — the key has to be
      present for the profile to validate — and the pair is reported as a placeholder so the panel
      can say which values still need a real answer.
    """
    types = _type_specs(registry)
    by_type = {}
    for cfg in (seed_modes or {}).values():
        if isinstance(cfg, dict) and cfg.get("type"):
            by_type.setdefault(normalize_type(cfg["type"]), cfg)

    modes: dict = {}
    inherited, at_defaults, placeholders, left_out = [], [], [], []
    slot = 0
    for type_key, spec in types.items():
        seed = by_type.get(type_key)
        if seed is not None:
            modes[str(slot)] = copy.deepcopy(seed)
            inherited.append(type_key)
            slot += 1
            continue

        entry: dict = {"type": type_key}
        unfillable, empty_valued = [], []
        for key in spec.get("required", []) or []:
            schema = (spec.get("params") or {}).get(key)
            if not isinstance(schema, dict) or "default" not in schema:
                unfillable.append(key)
                continue
            value = schema["default"]
            entry[key] = copy.deepcopy(value)
            if value is None or value == "" or value == [] or value == {}:
                empty_valued.append(f"{type_key}.{key}")
        if unfillable:
            left_out.append((type_key, tuple(unfillable)))
            continue
        # Only an INCLUDED type contributes placeholders: reporting "headlinesnews.feed_url is empty"
        # for a type that was then left out of the file would point at something that is not there.
        placeholders.extend(empty_valued)
        modes[str(slot)] = entry
        at_defaults.append(type_key)
        slot += 1

    report = {
        "types": tuple(inherited) + tuple(at_defaults),
        "inherited": tuple(inherited),
        "at_defaults": tuple(at_defaults),
        "placeholders": tuple(placeholders),
        "left_out": tuple(left_out),
    }
    return modes, report


def create_profile(base_dir: str, name: str, registry: dict, *, inherit_from: str | None = None,
                   switch: bool = False, config_override: str | None = None) -> CreateResult:
    """
    Create a new profile: every mode the registry knows, in a file you name, in configs/.

    Written through the same validation and atomic write as an edit, so a new file cannot be born
    broken. `inherit_from` (usually the active profile) seeds the tuned values — see
    `build_full_profile` for the rules and for what happens to a mode that cannot be filled.

    Refused, with nothing written, when: the name is unsafe, the file already exists (a create must
    never be a silent overwrite — that is what Save is for, and Save backs up first), the registry
    lists no types, or the generated document does not validate.
    """
    filename, problem = safe_profile_name(name)
    if problem:
        return CreateResult(ok=False, reason=problem)

    directory = os.path.join(os.path.abspath(base_dir), PROFILES_DIRNAME)
    path = os.path.abspath(os.path.join(directory, filename))
    # Defence in depth: the name is restricted above, and a create still must not escape configs/.
    if os.path.dirname(path) != os.path.abspath(directory):
        return CreateResult(ok=False,
                            reason=f"{name!r} does not name a file directly inside {PROFILES_DIRNAME}/")
    if os.path.exists(path):
        return CreateResult(
            ok=False,
            reason=f"{os.path.relpath(path, base_dir)} already exists — pick another name. "
                   f"Nothing was written.")

    seed_label, seed_modes = "", None
    if inherit_from:
        seed_path = (os.path.abspath(inherit_from) if os.path.isabs(inherit_from)
                     else os.path.abspath(os.path.join(base_dir, inherit_from)))
        candidate = load_json(seed_path, None)
        if isinstance(candidate, dict) and isinstance(candidate.get("modes"), dict) \
                and candidate["modes"]:
            seed_modes = candidate["modes"]
            seed_label = os.path.relpath(seed_path, base_dir)

    modes, report = build_full_profile(registry, seed_modes)
    if not modes:
        return CreateResult(ok=False,
                            reason="the registry lists no mode types, so there is nothing to put in "
                                   "a new profile")

    issues = validate_profile(modes, _type_specs(registry), base_dir=base_dir)
    blocking = [i for i in issues if i.is_error]
    if blocking:
        return CreateResult(
            ok=False,
            reason="the generated profile did not validate, so nothing was written",
            errors=tuple(i.render().strip() for i in blocking))

    os.makedirs(directory, exist_ok=True)
    try:
        written = atomic_write_json(path, {"modes": modes}, backup=False)
    except (WriteVerificationError, OSError, TypeError, ValueError) as e:
        return CreateResult(ok=False, reason=f"could not write {filename}: {e}")

    result = CreateResult(
        ok=True,
        path=path,
        rel=os.path.relpath(path, base_dir),
        sha256=written.get("sha256", ""),
        modes=len(modes),
        types=report["types"],
        inherited=report["inherited"],
        at_defaults=report["at_defaults"],
        placeholders=report["placeholders"],
        left_out=report["left_out"],
        seed=seed_label,
        warnings=tuple(i.render().strip() for i in issues if not i.is_error),
    )
    if switch:
        result.switched = switch_profile(base_dir, path, _type_specs(registry),
                                         config_override=config_override)
    return result


def load_payload(base_dir: str, profile_path: str) -> dict:
    """
    What the render loop needs to run a profile's FRESHLY READ state.

    Built by re-running the startup loader (core.config.load_project_config) rather than by hand,
    so "what the panel applied" is by construction "what a restart would load" — including the
    local override and the registry. The panel calls this (it owns disk I/O); the render loop only
    swaps the dicts it receives.
    """
    registry_json, registry, modes_config, config_path = load_project_config(
        base_dir, config_override=profile_path)
    return {
        "registry_json": registry_json,
        "registry": registry,
        "modes_config": modes_config,
        "config_path": config_path,
    }
