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

from .config import LOCAL_CONFIG_NAME, load_json, load_project_config, normalize_type
from .params import resolve_params, validate_param_value
from .store import WriteVerificationError, atomic_write_json, sha256_file
from .validation import ERROR, Issue, validate_profile


class EditorRefused(Exception):
    """A change the editor will not stage (e.g. a key supplied by the local override)."""


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
            bits.append(f"enabled = {self.enabled}")
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

    def unstage(self, number) -> None:
        self.staged.pop(int(number), None)

    def revert_all(self) -> None:
        self.staged.clear()

    def reload(self) -> None:
        """Drop staged changes AND re-read the file from disk (the way out of a conflict)."""
        self.document = self._read()
        self.baseline_sha = sha256_file(self.path) if os.path.exists(self.path) else ""
        self.staged.clear()

    # ---------------------------------------------------------------- what would be written

    def prospective(self) -> dict:
        """The document as it would be written right now. Deep copy; self.document is untouched."""
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
                cfg["enabled"] = bool(state.enabled)
            modes[key] = cfg
        return doc

    def is_dirty(self, number=None) -> bool:
        if number is None:
            return any(not s.empty for s in self.staged.values())
        return not self.staged.get(int(number), StagedEdit(int(number))).empty

    def changed_modes(self) -> list:
        return sorted(n for n, s in self.staged.items() if not s.empty)

    def staged_summary(self) -> str:
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
