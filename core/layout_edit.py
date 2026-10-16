# core/layout_edit.py
#
# Editing a control-panel LAYOUT file (the per-mode asset document that places the animated overlays
# over the artwork).
#
# Same rules as the profile editor, and for the same reasons:
#   * validate with the OWNER's validator — here `controlpanel.layout.layout_from_data` — so there is
#     never a second opinion about what a valid layout is;
#   * write atomically with a timestamped backup, and refuse when the file changed underneath;
#   * ONE writer per file: this is the only module that writes a layout.
#
# What is different is the shape of the work: the editor holds a DOCUMENT, and the file is touched
# only by save(). That is what makes the live page possible — a nudge changes the document and posts
# one bus command (the loop applies it to the running mode in memory), and nothing is written until
# Save is pressed. Nudging is dozens of presses; each one must not be a write.
#
# No pygame rendering here and no display: the panel calls this from its own thread.

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field

from core.store import WriteVerificationError, atomic_write_json, sha256_file


def _paths():
    """
    The package's asset paths, imported ON DEMAND.

    Two separate reasons, both learned the hard way in one session: `controlpanel.layout` imports
    pygame (so a module-level import drags a display library into the panel's import chain), and the
    package itself is not present in every tree that imports `core` — the test sandboxes copy core/
    without controlpanel/, so a top-level import made the panel thread die at startup with
    "panel never came up".
    """
    from controlpanel import paths
    return paths


def backgrounds_dir() -> str:
    """The directory a freeform layout's artwork must live in (also the asset route's boundary)."""
    return str(_paths().BACKGROUNDS_DIR)


def layouts_dir() -> str:
    return str(_paths().LAYOUTS_DIR)


def _loader():
    """The package's layout validator, imported on demand (see _paths)."""
    from controlpanel.layout import layout_from_data
    return layout_from_data


def _layout_error():
    """The loader's exception class, imported on demand — for `except _layout_error() as e:`."""
    from controlpanel.layout import LayoutError
    return LayoutError


def __getattr__(name):
    """
    `LayoutError` / `layout_from_data` for OUTSIDE callers (`core.layout_edit.LayoutError`).

    Note what this cannot do: it does not satisfy a bare name lookup inside this module's own
    functions (PEP 562 covers attribute access, not globals), which is why the code here calls the
    helpers above instead.
    """
    if name in ("LayoutError", "layout_from_data"):
        from controlpanel.layout import LayoutError, layout_from_data
        return {"LayoutError": LayoutError, "layout_from_data": layout_from_data}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@dataclass
class LayoutSaveResult:
    ok: bool
    reason: str = ""
    path: str = ""
    rel: str = ""
    sha256: str = ""
    backup: str = ""
    errors: tuple = ()


#: A control entry needs a type and a sprite; everything else is optional. Kept here rather than in the
#: page so the rules live next to the writer that has to satisfy them.
_MINIMAL_CONTROL = ("type", "sprite")


def resolve_layout_path(name_or_path: str) -> str:
    """A layout file by bare name (under the package's layouts dir) or by path."""
    return str(_paths().resolve_under(_paths().LAYOUTS_DIR, name_or_path, ".json"))


def list_backgrounds() -> list:
    """The PNGs a freeform layout can be built over, newest name order."""
    directory = _paths().BACKGROUNDS_DIR
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.glob("*.png"))


def list_layouts() -> list:
    directory = _paths().LAYOUTS_DIR
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob("*.json"))


class LayoutEditor:
    """
    One editing session over one layout file.

    Every mutating method works on the in-memory document and validates the RESULT, rolling back if
    it would not load — so a bad edit is refused at the point of the edit, with the loader's own
    words, instead of at save time or (worse) on the wall.
    """

    def __init__(self, name_or_path: str):
        self.path = resolve_layout_path(name_or_path)
        self.name = os.path.basename(self.path)[:-5] if self.path.endswith(".json") else self.path
        self.document = self._read()
        self.baseline_sha = sha256_file(self.path) if os.path.exists(self.path) else ""
        self.last_backup = ""

    # ---------------------------------------------------------------- reading

    def _read(self) -> dict:
        try:
            with open(self.path) as handle:
                data = json.load(handle)
        except FileNotFoundError:
            raise _layout_error()(f"layout not found: {self.path}")
        except json.JSONDecodeError as e:
            raise _layout_error()(f"invalid JSON in {self.path}: {e}")
        if not isinstance(data, dict):
            raise _layout_error()(f"{self.path} is not a layout document")
        return data

    @property
    def mode(self) -> str:
        return str(self.document.get("mode", "grid")).strip().lower()

    def controls(self) -> list:
        controls = self.document.get("controls")
        return controls if isinstance(controls, list) else []

    def canvas(self) -> tuple:
        """Design resolution: what the layout says, else the background PNG's real size."""
        explicit = self.document.get("design_resolution")
        if isinstance(explicit, list) and len(explicit) == 2:
            return int(explicit[0]), int(explicit[1])
        bg = self.document.get("background_image")
        if bg:
            candidate = _paths().resolve_under(_paths().BACKGROUNDS_DIR, bg)
            if candidate.exists():
                try:
                    import pygame
                    return pygame.image.load(str(candidate)).get_size()
                except Exception:
                    pass
        return 1920, 1080

    def rect_of(self, index: int):
        """(x, y, w, h) of one control, from what the file says (size OR scale-derived)."""
        controls = self.controls()
        if not 0 <= index < len(controls):
            return None
        entry = controls[index]
        at = entry.get("at") or [0, 0]
        size = entry.get("size")
        if isinstance(size, list) and len(size) == 2:
            return (int(at[0]), int(at[1]), int(size[0]), int(size[1]))
        # No explicit size: the loader derives it from the sprite footprint and "scale". Report that
        # rather than pretending, so the page shows the real box.
        try:
            layout = self.layout()
            for i, placed in enumerate(layout.controls):
                if i == index:
                    return tuple(int(v) for v in placed.rect_px)
        except _layout_error():
            pass
        return (int(at[0]), int(at[1]), 0, 0)

    def layout(self):
        """The validated layout the loader makes of the current document."""
        return _loader()(copy.deepcopy(self.document), name=self.name)

    def validate(self) -> tuple:
        """(errors, warnings) — errors in the loader's own words."""
        try:
            self.layout()
        except _layout_error() as e:
            return (str(e),), ()
        return (), self._sanity_warnings()

    def _sanity_warnings(self) -> tuple:
        """
        Things that LOAD fine and are still worth saying: an overlay whose box sticks out of the
        canvas is a refusal, but one that sits entirely off the artwork is usually a mistake.
        """
        warnings = []
        w, h = self.canvas()
        for i, entry in enumerate(self.controls()):
            at = entry.get("at")
            if not isinstance(at, list) or len(at) != 2:
                continue
            if at[0] < 0 or at[1] < 0:
                warnings.append(f"#{i} is placed at a negative position {at}")
        return tuple(warnings)

    # ---------------------------------------------------------------- editing (in memory)

    def set_rect(self, index: int, rect) -> dict:
        """
        Move/resize one control in the document. Freeform only.

        A grid layout places controls in whole cells inside panels; there is no pixel to nudge, so it
        is refused with that reason instead of writing a shape the loader would reject anyway.
        """
        if self.mode != "freeform":
            return {"ok": False, "reason": "this is a grid layout: controls sit in 128px cells inside "
                                          "panels, so there is no pixel position to nudge. The "
                                          "alignment editor works on freeform layouts."}
        controls = self.controls()
        if not 0 <= index < len(controls):
            return {"ok": False, "reason": f"this layout has no control #{index}"}
        try:
            x, y, w, h = (int(v) for v in rect)
        except (TypeError, ValueError):
            return {"ok": False, "reason": f"a rect must be four numbers, not {rect!r}"}
        if w <= 0 or h <= 0:
            return {"ok": False, "reason": "width and height must be positive"}

        before = copy.deepcopy(controls[index])
        controls[index]["at"] = [x, y]
        controls[index]["size"] = [w, h]
        controls[index].pop("scale", None)      # an explicit size wins; keeping both would confuse
        errors, _ = self.validate()
        if errors:
            controls[index] = before
            return {"ok": False, "reason": f"that position does not fit the layout: {errors[0]}"}
        return {"ok": True, "index": index, "rect": [x, y, w, h]}

    def add_control(self, entry: dict) -> dict:
        """Append a control to the document, refusing anything the loader will not accept."""
        if not isinstance(entry, dict):
            return {"ok": False, "reason": "a control must be an object"}
        missing = [k for k in _MINIMAL_CONTROL if not entry.get(k)]
        if missing:
            return {"ok": False, "reason": f"a control needs {', '.join(missing)}"}

        candidate = dict(entry)
        w, h = self.canvas()
        if not candidate.get("at"):
            size = candidate.get("size") or [160, 160]
            candidate["at"] = [max(0, (w - int(size[0])) // 2), max(0, (h - int(size[1])) // 2)]
            candidate.setdefault("size", size)
        controls = self.controls()
        controls.append(candidate)
        errors, _ = self.validate()
        if errors:
            controls.pop()
            return {"ok": False, "reason": f"the loader rejected that control: {errors[0]}"}
        return {"ok": True, "index": len(controls) - 1, "entry": candidate}

    def remove_control(self, index: int) -> dict:
        controls = self.controls()
        if not 0 <= index < len(controls):
            return {"ok": False, "reason": f"this layout has no control #{index}"}
        if len(controls) <= 1:
            return {"ok": False, "reason": "this is the last overlay: removing it would leave a "
                                          "layout with nothing in it"}
        removed = controls.pop(index)
        errors, _ = self.validate()
        if errors:
            controls.insert(index, removed)
            return {"ok": False, "reason": f"removing that would break the layout: {errors[0]}"}
        return {"ok": True, "removed": removed, "index": index}

    def centre_rect(self, index: int) -> dict:
        rect = self.rect_of(index)
        if rect is None:
            return {"ok": False, "reason": f"this layout has no control #{index}"}
        w, h = self.canvas()
        return self.set_rect(index, [(w - rect[2]) // 2, (h - rect[3]) // 2, rect[2], rect[3]])

    # ---------------------------------------------------------------- the file

    def is_stale(self) -> bool:
        current = sha256_file(self.path) if os.path.exists(self.path) else ""
        return current != self.baseline_sha

    def is_dirty(self) -> bool:
        try:
            return self.document != self._read()
        except _layout_error():
            return True

    def save(self, *, force: bool = False) -> LayoutSaveResult:
        """
        Validate the document and write it. Nothing is written unless every check passes, and a save
        that cannot be verified is reported as a failure rather than assumed to have worked.
        """
        if not self.is_dirty():
            return LayoutSaveResult(ok=True, reason="nothing to save", path=self.path,
                                    rel=self.name)
        errors, _ = self.validate()
        if errors:
            return LayoutSaveResult(ok=False,
                                    reason=f"the layout does not validate, so nothing was written: "
                                           f"{errors[0]}", errors=errors)
        if not force and self.is_stale():
            return LayoutSaveResult(
                ok=False,
                reason="the layout file changed on disk since this page loaded it, so saving would "
                       "overwrite someone else's change — reload and re-apply")
        try:
            report = atomic_write_json(self.path, self.document, backup=True)
        except (WriteVerificationError, OSError, TypeError, ValueError) as e:
            return LayoutSaveResult(ok=False, reason=f"could not write {self.path}: {e}")

        self.baseline_sha = report["sha256"]
        self.last_backup = report.get("backup") or ""
        return LayoutSaveResult(ok=True, reason=f"saved {os.path.basename(self.path)}",
                                path=report["path"], rel=self.name, sha256=report["sha256"],
                                backup=self.last_backup)

    def reload(self) -> None:
        self.document = self._read()
        self.baseline_sha = sha256_file(self.path) if os.path.exists(self.path) else ""


def create_freeform(name: str, background: str, seed_from: str | None = None) -> dict:
    """
    Make a NEW freeform layout over a PNG the author supplies — the "start a new panel" flow.

    Seeding copies the controls from an existing layout (type, sprite, size, and any signal/wave
    block) but NOT its fidelity to the new artwork: a control whose box falls outside the new canvas
    is clamped inward and counted, because a control you cannot see is worse than one you have to
    move. Refuses to overwrite, and validates with the loader before writing.
    """
    raw = str(name or "").strip()
    if raw.lower().endswith(".json"):
        raw = raw[:-5]
    # Refused rather than sanitised: taking a basename first would quietly turn "../escape" into
    # "escape", and a silent rename leaves you looking for a file under the name you typed.
    if not raw or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                      for ch in raw):
        return {"ok": False, "reason": "a layout name may use letters, digits, dashes and "
                                      "underscores only"}
    stem = raw

    bg_name = os.path.basename(str(background or "").strip())
    if not bg_name or not (_paths().BACKGROUNDS_DIR / bg_name).exists():
        available = ", ".join(list_backgrounds()) or "none found"
        return {"ok": False, "reason": f"no such background image in "
                                      f"{_paths().BACKGROUNDS_DIR.name}/: {bg_name!r} "
                                      f"(available: {available})"}

    path = _paths().LAYOUTS_DIR / f"{stem}.json"
    if path.exists():
        return {"ok": False, "reason": f"{stem}.json already exists — pick another name"}

    try:
        import pygame
        width, height = pygame.image.load(str(_paths().BACKGROUNDS_DIR / bg_name)).get_size()
    except Exception as e:
        return {"ok": False, "reason": f"cannot read {bg_name}: {e}"}

    controls, seed_note = [], ""
    if seed_from:
        try:
            source = LayoutEditor(seed_from)
            copied, clamped = [], []
            for i, entry in enumerate(source.controls()):
                fresh = copy.deepcopy(entry)
                at = fresh.get("at") or [0, 0]
                size = fresh.get("size")
                if isinstance(size, list) and len(size) == 2:
                    w, h = int(size[0]), int(size[1])
                else:
                    rect = source.rect_of(i) or (at[0], at[1], 160, 160)
                    w, h = rect[2], rect[3]
                    fresh["size"] = [w, h]
                x = min(max(0, int(at[0])), max(0, width - w))
                y = min(max(0, int(at[1])), max(0, height - h))
                if (x, y) != (at[0], at[1]):
                    clamped.append(i)
                fresh["at"] = [x, y]
                fresh.pop("scale", None)
                copied.append(fresh)
            controls = copied
            seed_note = (f", {len(copied)} controls copied from {source.name}"
                         + (f" ({len(clamped)} clamped into the new canvas)" if clamped else ""))
        except _layout_error() as e:
            return {"ok": False, "reason": f"cannot seed from {seed_from}: {e}"}

    document = {
        "name": stem,
        "mode": "freeform",
        "design_resolution": [width, height],
        "background_image": bg_name,
        "controls": controls,
    }
    try:
        _loader()(document, name=stem)                             # the package's own validator
    except _layout_error() as e:
        return {"ok": False, "reason": f"the new layout would not load: {e}"}
    try:
        report = atomic_write_json(str(path), document, backup=False)
    except (WriteVerificationError, OSError, TypeError, ValueError) as e:
        return {"ok": False, "reason": f"could not write {path}: {e}"}

    return {"ok": True, "name": stem, "path": str(path), "canvas": [width, height],
            "background": bg_name, "controls": len(controls), "seeded": seed_note,
            "sha256": report["sha256"]}
