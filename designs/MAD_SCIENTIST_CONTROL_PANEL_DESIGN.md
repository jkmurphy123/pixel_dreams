# Mad Scientist Control Panel — freeform `controlpanel` layout

**Status:** implemented and verified off-display (2026-10-21); live-wall restart and final
browser alignment remain PENDING user action.

## 1. Goal

Add a new portrait control-panel instance, **Mad Scientist Control Panel**, over the supplied artwork:

`assets/control_panel/backgrounds/mad_lab_1.png`

It reuses the existing animated indicator lamps and adds four reusable freeform control types:

1. `jacobs_ladder` — a blue/violet electrical arc that ignites at the close lower gap, climbs along the diverging electrodes, breaks at the top, then restrikes.
2. `electric_filament` — a glowing tungsten coil in either vertical or horizontal orientation, with a warm shimmer and occasional current surge.
3. `spark_terminal` — a continuous shower of small moving sparks emitted from one point, with no drawn terminal body or idle halo.
4. `mechanical_wheels` — a dark brass/ivory mechanical counter with rolling number drums, not a seven-segment or Nixie display.

This is a new **instance** of the existing `controlpanel` mode, not a new registry mode type and not a fork of the package. The existing layout editor, colour pickers, add-overlay dialog, live placement, backups, refresh path, and validation will therefore work for it automatically.

## 2. Measured starting facts

- Source art exists at the requested path and measures **941 × 1672 px**.
- The portrait wall/layout convention currently used by the active vertical profile is **1080 × 1920 px**.
- Source and wall aspect ratios differ by only **0.053%**. We will produce a one-time 1080 × 1920 wall copy from the supplied image, preserving the original asset unchanged. This prevents the compositor from smooth-scaling the whole background every frame; the prior control-panel work measured that path at about 36 fps versus about 62 fps with wall-sized artwork.
- The vertical profile currently contains control-panel slots 45, 55, 57, and 58. The new instance is proposed as the next free slot, **59**, and will be added only through `ProfileEditor` / the existing profile writer.
- The shared sprite sheet has free cells in rows 12–15 after the existing arcane family. The exact cells will be reserved only after confirming no concurrent change lands there.

## 3. Resolved design choices

| Decision | Choice | Why |
|---|---|---|
| Integration | Extend `controlpanel` | The existing freeform pipeline is already type-driven and provides the complete editor/live-refresh chain. |
| Mode identity | Keep registry type `controlpanel` | A profile instance, not a second registry alias, avoids a duplicate schema and type-count churn. |
| Artwork | Keep `mad_lab_1.png`; add a generated wall-sized copy | The supplied original remains authoritative; pre-scaling avoids per-frame scaling cost. |
| Orientation | Portrait only in this pass | The art and active kiosk profile are portrait. Landscape/narrow need their own artwork and placement pass. |
| Palette | Cold electrical blue/violet for arcs and sparks; warm tungsten orange for filaments; existing red/amber/green lamps | Matches the painting without repainting its brass machinery. |
| Wheel display | Five rolling drums in the painted centre display | It reads clearly as an old instrument counter and does not cover the six painted gauges. |
| Persistent visibility | Every momentary effect has a visible state | The ladder retains charged electrodes; terminals maintain a continuous particle shower rather than a static glow, so the alignment page does not position an empty box. |

## 4. New control family

All classes live together in `controlpanel/controls/mad_science.py` because they share cached glows, numeric coercion/clamping, deterministic seeded choreography, clipping, and the same no-allocation-per-frame rule. Each class will have a docstring with its layout overrides so the panel’s Add Overlay dialog describes it automatically.

### 4.1 `jacobs_ladder`

**Visual:** A jagged luminous bolt starts low between the two close rod bases, climbs upward while the rods spread apart, breaks at the high gap, rests briefly, then restarts. A violet core and blue/cyan halo keep it visible over the dark central panel.

**Key mechanics:**

- The path is generated only for a new strike, never every frame.
- A rising progress parameter maps each point between two linearly diverging rail anchors.
- The main arc is clipped to the control rectangle, with small branches constrained to the same rectangle.
- Idle charged contacts remain drawn between strikes.

**Layout overrides:** `arc_rgb`, `cycle`, `climb`, `rest`, `jag`, `branches`, `glow`, `left_rail`, `right_rail`.

`left_rail` and `right_rail` are each two normalized points (bottom then top), allowing the control to fit any future artwork rather than hard-coding this laboratory’s rods.

### 4.2 `electric_filament`

**Visual:** A tungsten coil inside a lamp/tube, visibly warm at rest and brightening in rolling sections during a current surge. It supports a tall vertical tube and a wide horizontal bulb/tube with one class.

**Layout overrides:** `filament_rgb`, `orient` (`"v"` or `"h"`), `turns`, `thickness`, `heat`, `surge`, `glow`, `inset`.

The control draws only the filament and its contained bloom. The painting remains responsible for glass, sockets, and hardware.

### 4.3 `spark_terminal`

**Visual:** Small asymmetric sparks continuously emit from one point and travel briefly outward/upward. There is no terminal disc, core, or halo: every visible mark is a moving particle.

**Layout overrides:** `spark_rgb`, `rate`, `count`, `speed`, `spread`, `life`.

A fixed particle pool is constructed once, recycled in place, and bounded by a conservative count ceiling. New particles are seeded deterministically from the mode’s `seed`.

### 4.4 `mechanical_wheels`

**Visual:** A five-digit mechanical number counter: dark recessed wells, ivory/aged-paper digit bands, separators, and digit strips that visibly roll over rather than changing as flat text. The step rhythm stays deliberately slow enough to read.

**Layout overrides:** `wheel_rgb`, `face_rgb`, `digits`, `start`, `per_sec`, `step_time`, `direction`, `window`, `bezel`, `font_name`.

Unlike `counter`, it does not call the shared seven-segment renderer. Digits are pre-rendered during construction from `font_name`: a pygame system-font family name (for example `dejavusansmono`) or an explicit `.ttf`/`.otf` path. An unavailable font falls back safely to pygame's default; steady-state drawing must allocate no surfaces.

## 5. Registration and editor wiring

For each new type, the implementation will add exactly one entry in each of these existing tables:

1. `controlpanel/registry.py` — type key → default sprite ID.
2. `controlpanel/controls/__init__.py` — type key → class and colour-key row.
3. `assets/control_panel/sprite_defs.json` — appended reserved sprite geometry.

The sprite entries are validation/placement metadata: freeform layouts do not blit them over artwork. `scripts/make_placeholder_skin.py` will be rerun so the placeholder skin remains complete for existing grid-mode tests.

New colour picker keys will use the project’s recognized `*_rgb` vocabulary:

- `jacobs_ladder`: `color`, `arc_rgb`
- `electric_filament`: `color`, `filament_rgb`
- `spark_terminal`: `color`, `spark_rgb`
- `mechanical_wheels`: `color`, `wheel_rgb`, `face_rgb`

No class will repurpose the freeform layout’s `size` key for an internal scalar; that key already means the pixel rectangle.

## 6. Artwork placement plan

Coordinates below are proposed wall-pixel rectangles for the generated **1080 × 1920** background. They were derived from the supplied 941 × 1672 image with separate x/y scales and are starting points to verify with the live alignment page.

| Overlay | Initial wall rect / anchors | Artwork feature | Notes |
|---|---|---|---|
| Jacob’s ladder | rect `[365, 40, 367, 586]`; rails run from its lower close gap toward its high outer tips | Two gold diverging rods at top centre | Primary effect; must not spill into the two large tube lamps. |
| Left vertical filament | `[115, 212, 155, 367]` | Tall left glass tube | Warm orange; inset avoids drawing over the glass rim and metal base. |
| Right vertical filament | `[813, 212, 155, 367]` | Tall right glass tube | Mirror placement and independent phase. |
| Left sparking terminal | `[402, 531, 121, 126]` | Lower left ladder insulator/contact | Spark cone points inward/upward, not into the gauge row. |
| Right sparking terminal | `[560, 531, 121, 126]` | Lower right ladder insulator/contact | Mirror of left, with different deterministic phase. |
| Mechanical wheels | `[371, 916, 339, 167]` | Recessed centre CRT/display window | Five wheels, brass bezel; deliberately below the gauge faces. |
| Reused indicator lamps, left | `[223, 876, 75, 201]` | Painted red/amber/green lamp stack | Use three existing `lamp` overlays with tight individual rectangles, not one full-box lamp. |
| Reused indicator lamps, right | `[783, 876, 75, 201]` | Painted red/amber/green lamp stack | Same strategy; signals have staggered periods so both stacks do not blink in lockstep. |

Visual conflicts to avoid:

- The six gauge faces already have detailed markings. No overlay will cover them.
- Existing `lamp` overlays should be tightly centered on the painted indicator jewels; their broad unmasked disc would otherwise read as a dark hole over brass.
- The yellow/white portions of a ladder must not be additive-only over a light reflection. The class will use an alpha-blended violet/cyan core plus a capped additive halo, following the proven lightning control’s `blend` lesson.
- Filament rectangles must not extend onto the tube frames: artwork supplies the glass and brass; code supplies only the moving hot coil.

## 7. Proposed layout and profile instance

A new freeform asset document, `assets/control_panel/layouts/mad_scientist_lab.json`, will name the wall-sized background and use the wall resolution:

- `mode`: `freeform`
- `design_resolution`: `[1080, 1920]`
- `background_image`: proposed generated wall copy
- controls in draw order: sparking terminals and ladder charge first, filaments and lamps next, ladder core and mechanical display last where necessary for readability.

Proposed vertical profile instance:

- slot: `59`
- type: `controlpanel`
- name: `Mad Scientist Control Panel`
- layout: `mad_scientist_lab`
- fixed seed: `19`
- scale mode: `cover` (effectively a no-op because canvas matches the wall)

The profile change will use the repository’s `ProfileEditor` writer, creating a timestamped backup and validating the entire profile. It will not be handwritten into JSON.

## 8. Tests and acceptance

### Automated tests

1. Extend the all-types freeform fixture in `tests/test_control_panel_all.py` with the four types.
2. Add `tests/test_mad_science.py`, modeled on the arcane family’s proven suite:
   - complete registration in type/class/colour/sprite tables;
   - visible on frame zero and after one simulated minute;
   - drawn pixels contained within the control rectangle;
   - `set_rect()` moves the drawing completely out of the old rectangle;
   - same seed + same updates produces the same frame;
   - malformed/extreme values clamp or fall back without an enter-time exception;
   - after cache warm-up, 600 update/draw frames create zero `pygame.Surface` objects.
3. Validate the real layout with `load_layout()` and build `ControlPanelMode` under the dummy video driver.
4. Run `python validate_configs.py --all`.
5. Run the full headless test suite.

### Visual/performance checks

1. Render the real layout off-display at 1080 × 1920 and inspect the saved PNG.
2. Capture two or more timed frames and difference them to prove the rising ladder and spark particles actually animate; a single screenshot is not enough for a momentary strike.
3. Run a sandbox instance on a free loopback port. Do not take over the user’s live kiosk display.
4. Final wall verification is PENDING user consent to restart/reload changed Python modules. Layout-only placement edits can refresh live; new classes require a process restart.

## 9. Implementation sequence

1. Make an off-display spike for the ladder’s rising topology, the filament coil, spark-pool performance, and rolling wheels; measure a control render and output frame differences.
2. Add the four controls and their registrations, default sprite metadata, placeholder skin regeneration, and unit/contract tests.
3. Create the pre-scaled background copy and the real freeform layout from the placement table.
4. Add slot 59 through the profile editor and structurally verify that exactly one slot changed.
5. Run validation + full test suite; render and inspect the full layout off-display.
6. Start a sandbox only, inspect its image/animation, clean up its listener/process, then hand off wall restart and browser verification to the user.

## 10. Explicit non-goals for this pass

- No new registry mode type or parallel control-panel package.
- No separate landscape/narrow layout.
- No changes to the control-panel web application; it already discovers these types from the established tables.
- No live kiosk restart or display takeover without the user’s explicit request.
