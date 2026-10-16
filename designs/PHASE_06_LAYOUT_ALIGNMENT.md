# Phase 6 — Aligning controlpanel overlays to the artwork (design for review)

Status: PROPOSED. Nothing built yet. Decisions marked **Q** are the ones I want you to settle; the
rest are calls I have made and will carry through unless you say otherwise.

## What you asked for

> "the mode called controlpanel … shows a background png of a control panel then overlaying small
> animations like gauge needles, blinking lights, etc. the challenge is to align the xy position of
> the animated control exactly where it fits on the underlying png. the controls and their position is
> in a separate config file called demo_console. so when i go to the parameter page for the
> controlpanel mode i need a separate page or popup that lists all the control overlays, lets me add
> and remove them and also lets me select one and adjust its xy position and size using clickable
> buttons; ideally live while the mode is displayed so i can immediately see the results and i can
> precisely position each control over the png."

## What is actually there (read from the code, not assumed)

`modes/control_panel_mode.py` loads a layout through `controlpanel.layout.load_layout()` and hands it
to a `Compositor`. The layout file is chosen by the mode's `layout_file` parameter, and there are two
kinds of layout:

| layout | file | flavour | canvas | controls |
|---|---|---|---|---|
| `steampunk1` | `assets/control_panel/layouts/steampunk1.json` | **freeform** (background PNG `steampunk1.png`) | 1920x1088 | 17 |
| `freeform_demo` | `…/freeform_demo.json` | **freeform** (`freeform_demo.png`) | 1600x900 | 17 |
| `demo_console` | `…/demo_console.json` | **grid** (3 panels, no PNG) | 1920x1080 | 22 |

**One thing to settle straight away (Q1).** The file you named, `demo_console`, is the *grid* flavour:
controls are placed in 128 px cells inside panels (`"panel": "left", "at": [1, 4]`) and the loader
validates that they fit inside their panel. The thing you are describing — a background PNG with
overlays positioned by pixel — is the *freeform* flavour, which is what `steampunk1` and
`freeform_demo` are. So the editor's natural target is freeform; for a grid layout there is no PNG to
align to and positions are whole cells (128 px), which cannot be "precise" by construction.

How it draws (this part matters for what is cheap and what is not):

* On enter, the compositor builds a **static canvas** once at design resolution: the background PNG,
  plus (grid mode only) panel plates and skin sprites.
* Each frame it copies that canvas to a frame buffer and lets **each control draw its own overlay** on
  top; only then is the frame scaled to the screen (`fit` / `cover` / `stretch`).
* In **freeform** mode no sprites are baked into the static canvas, so a control moving does **not**
  touch the canvas at all. In grid mode the control's sprite *is* baked in, so a move needs the canvas
  rebuilt.

`controlpanel/controls/base.py:48` sets `self.rect = placed.rect_px`, and `_anchor()` / `_window()`
re-read `self.rect` on every call — which looks like "just change `.rect` and it moves".

## Measured feasibility (spike, off-display)

`/home/ubuntu/.hermes/cache/scratch/pd_layout_spike3.py` — SDL dummy, the kiosk's screen untouched.
Instrument: draw the control alone on black, colorkey the background, ask pygame for the bounding rect
of what it drew (no whole-frame diffing, no dependence on the animation's phase).

```
A. instrument drift, nothing moved      : 0 px          (trustworthy)
B. poking control.rect alone            : 13/13 and 12/12 still drawn in the OLD box
C. one-control rebuild (new object)     : left the old box 13/13 / 12/12,
                                          drew in the new box 11/13 / 9/12
   cost of one rebuild                  : 57-116 us      (a 60 fps frame is 16000 us)
   compositor static canvas unchanged   : True
```

**B is the important negative result: changing `control.rect` moves nothing.** Seven control classes
compute their geometry from the rect **once** and cache it (`lamps.LampControl` → `center`,`radius`;
`needles.GaugeControl` → `pivot`; `reels.RadarControl` and `reels.ClockControl` → `center`,`radius`;
`stateful.ToggleSwitchControl` → `pivot`; `stateful.RotaryKnobControl` and `stateful.PushButtonControl`
→ `center`,`radius`), and their subclasses inherit the behaviour. A naive implementation would look
like it did nothing at all, on the wall, and the person pressing the button would conclude the tool was
broken. Worth recording: my first two spike attempts were *also* wrong — the first compared sums of
different rectangles (proves nothing) and the second diffed whole frames while the overlays animated
off their own clock (cannot separate "the animation changed" from "the control moved"). The instrument
above was built to answer the question directly, and its 0 px drift is the check that it can.

**C's misses are informative too**: the 4 failures are a `LampControl`, a `DigitalReadoutControl`, a
`ScopeControl` and a `PushButtonControl` whose fresh instance draws *nothing* until it has been updated
at least once (an unlit lamp, a blank readout, an empty trace buffer). That is the real cost of the
rebuild approach: a nudge restarts that control's animation.

## Proposed design (Q2-Q4 pick the shape)

**A dedicated page `/layout?profile=<rel>&mode=<n>`** (Q4: page, not popup — a list, a preview and a
nudge pad do not fit in a dialog, and a dialog would sit on top of the mode list you navigate from).
Linked from the controlpanel mode's params page as `position overlays →`.

**Live editing through the bus, never through disk.** A new command `layout_edit` carries
`{op: "set_rect" | "select" | "freeze", index, rect}` to the render loop, which applies it to the live
mode instance in memory. Panel thread still never touches pygame; render thread still never touches
disk. One nudge costs microseconds on the loop (measured above) and does not rebuild the compositor,
switch modes, or write a file.

**A `set_rect` hook in the controlpanel package** (Q2, my recommendation). `Control.set_rect(rect)`
sets `self.rect` and calls a new `_recompute_geometry()`, whose default is a no-op; the seven caching
classes above move their existing geometry lines into that method (they already compute them, so it is
a move, not new maths). That is ~40 mechanical lines across 4 files, and it is what keeps the overlay
*animating in place while you nudge* instead of restarting on every press. The alternative is
per-control rebuild (C above): zero package changes, but a lamp/readout/scope goes blank for a moment
on every single press, which is the opposite of what you want when judging alignment.

**A marker on the wall** (Q3). While a control is selected, the mode draws its rect plus a crosshair,
in design space, on the live frame — so you are aligning against the real render at the real scale, not
against a browser approximation. Toggleable from the page. `freeze overlays` stops the selected
control's animation (or all of them) so the thing you are positioning holds still; the measured
`update(0.0)` is not a reliable freeze (some controls animate off their own clock), so freeze means
"skip update() for the frozen controls", which is exact.

**The page's preview.** The background PNG served by a new read-only, token-gated route restricted to
`assets/control_panel/backgrounds/`, drawn at page scale with one absolutely-positioned box per
control (from the layout file), the selected one emphasised. Click a box to select. Honest framing:
the boxes are geometry, not a render — the wall is the real render; the preview is for finding a
control in a 17-item layout, not for judging alignment.

**The nudge pad.** `←` `→` `↑` `↓` at a step you choose (1 / 5 / 10 px, default 1), `W+ W− H+ H−` for
size (or `scale ±0.05` when the layout uses `scale`), plus direct number entry for x / y / w / h and
`centre in canvas`. Every press is one bus command.

**Add / remove.** `Add overlay…` picks a type from the catalogue (`controlpanel.controls.CONTROL_CLASSES`)
plus a sprite id and an optional `signal`/`wave` block, and appends it at a default position (the
centre of the canvas, or the centre of the selection) — that is a change to the layout document, and
it needs a mode rebuild to exist on the wall (a one-off, unlike a nudge). `Remove` is two-step, like
the restore flow. `Save` writes the layout file; `Reload from disk` discards.

**One writer, one validator.** New module `core/layout_edit.py` (the profile editor is not touched):
validate-first, atomic write, timestamped backup, conflict refusal if the file changed underneath —
the same rules as `core/editor.py`. Validation uses the package's OWN loader (a new
`layout.load_layout_data(name, data)` so a candidate document can be checked without writing it), so
the editor cannot invent a second opinion about what a valid layout is.

## Questions (also in the chat message)

1. **Which layouts should the editor act on?** Freeform only (recommended — that is the PNG-overlay
   case you described, and `steampunk1` / `freeform_demo` are ready to try it on), freeform **plus** a
   way to start a new freeform layout over a PNG of your own, or also grid layouts (`demo_console`:
   whole cells, and a move needs the PNG canvas rebuilt each time).
2. **How should a live nudge reach the wall?** `set_rect` hook in the controlpanel package
   (recommended: the overlay keeps animating while you nudge; ~40 mechanical lines, 4 files), or
   per-control rebuild (no package changes; the control restarts its animation on every press, and
   lamps/readouts/scopes blink blank each time).
3. **Do you want the selection marker drawn on the wall** (rect + crosshair for the selected control,
   plus a freeze option)? Recommended yes — without it you are nudging blind on a busy PNG.
4. **Page or popup?** Page `/layout` (recommended), or a popup on the mode's params page.
5. **Save or auto-save?** Explicit `Save` (recommended: nudging means dozens of presses, and each write
   would be a file write with a backup), or write on every press.

## Delivery (after you answer)

* **6A — the live mechanism.** `set_rect` hook + `_recompute_geometry` in the 7 classes; the mode's
  `edit_rect` / `select` / `freeze`; the `layout_edit` bus command and the loop's handler; the marker;
  a `POST /api/layout` endpoint so it can be driven and tested without a browser. Verified by tests per
  control class (move the rect → the drawn extent follows, and the animation state is NOT reset) and by
  a live check on a real instance. You can try it with curl at the end of this step.
* **6B — the page.** Layout list, preview, nudge pad, add/remove, save/reload, conflict handling.
  Verified by page tests plus a process-level run that nudges, saves, and reloads.

## Non-goals, and the risks I want on the record

* **No drag-and-drop** in this phase (you asked for buttons; dragging can come later on the same
  plumbing).
* **No dial auto-detection** — finding the drawn dials in the PNG automatically is a research
  project, not a feature. The marker and the freeze option are the practical answer.
* **Grid layouts** cannot be nudged precisely: positions are cells and the sprite is baked into the
  static canvas, so every move rebuilds the PNG layer. Scope question Q1.
* **Scale mode interacts with what you see**: under `fit`/`cover` the design canvas is letterboxed or
  cropped on the screen, so a design-space offset is not a screen-space offset. The marker is drawn in
  design space (on the frame, before scaling), so what you align is what you get.
* **A freeform layout needs its PNG to exist** (`background_image` under
  `assets/control_panel/backgrounds/`); `demo_console` has none today.
* The spike scripts live in the Hermes scratch dir (paths above) and are not part of the repo; if you
  want the instruments kept, say so and I will move them under `scripts/` with a test that runs them.
