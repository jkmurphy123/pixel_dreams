# Mad Scientist Control Panel — acceptance record

Date: 2026-10-21

## Delivered

- Four reusable freeform control types in `controlpanel/controls/mad_science.py`:
  - `jacobs_ladder`: climbing/restriking arc between configurable diverging rails.
  - `electric_filament`: warm coil with vertical or horizontal orientation.
  - `spark_terminal`: continuous fixed-pool particle shower with no persistent terminal body or halo.
  - `mechanical_wheels`: five rolling, mechanical number drums with a held resting state between roll events.
- `mechanical_wheels.font_name` accepts either a pygame system-font family name or a `.ttf`/`.otf` path. The shipped layout selects `dejavusansmono`; off-display build confirmed `system:dejavusansmono` and the rendered display was visually readable.
- Registration in the control type, animation class, colour-picker, and sprite-definition tables.
- Regenerated `assets/control_panel/skins/placeholder/sheet.png`; generator reported 62 sprites.
- New 1080×1920 pre-scaled background: `assets/control_panel/backgrounds/mad_lab_1_wall.png`.
- New 1080×1920 freeform layout: `assets/control_panel/layouts/mad_scientist_lab.json`.
- Six reused existing lamp overlays, two filaments, two terminals, one ladder, and one mechanical display: 12 animated overlays total.
- Vertical profile slot 59, named `Mad Scientist Control Panel`, added through `ProfileEditor` with an atomic backup.

## Automated PASS

- `tests/test_mad_science.py`: 8 passed.
  - registration, frame-zero visibility, rectangle containment, live move geometry, active-ladder move, real-layout loading, one-minute durability, no post-warm-up `pygame.Surface` allocations, and mechanical roll hold timing.
- `tests/test_control_panel_all.py tests/test_control_edit.py tests/test_layout_align.py`: 31 passed.
- Full headless suite: **785 passed in 250.96 s**.
- `python validate_configs.py --all`: 0 errors; one pre-existing missing Windows-path warning in `configs/modes_config_portrait.json`.
- Profile write readback compared the generated backup against the current file: exactly slot `59` changed. Backup:
  `configs/.backups/modes_config_vert.json.20261021T134811_006737Z.bak`.
- `pixel_dreams.py --config configs/modes_config_vert.json --show_modes` listed:
  `59: controlpanel - Mad Scientist Control Panel`.
- Headless process run: `--play 59 --windowed --frames 120` built `mad_scientist_lab` with 12/12 animated controls and exited cleanly.

## Visual and performance PASS

- Off-display render built at its final 1080×1920 canvas with 12/12 animated controls.
- Render reviewed from `designs/mad_science_lab_render_07s.png`:
  - the arc bridges the painted diverging rods;
  - filaments sit inside the two tall glass tubes;
  - spark particles remain bounded to their own author-placed rectangles, with no terminal glow/body;
  - the mechanical display is readable at rest in the centre CRT window;
  - no effect covers a gauge face.
- Frame hashes differ between moments of the animation, proving time-varying output.
- Direct 1080×1920 off-display `update` + `render` benchmark: 5.391 ms/frame (185.5 fps ceiling). The individual new-overlay pass measured 0.964 ms/frame. The controller's dummy-driver FPS is not used as a wall-performance verdict.

## PENDING — user-owned live-wall verification

New Python classes are imported once by the kiosk process. A layout refresh alone cannot load this revision, so the display service must be restarted by the user before it can show slot 59.

After restarting the kiosk, verify on the control panel:

1. Select `Mad Scientist Control Panel` / slot 59 in the vertical profile.
2. Confirm the ladder rises from the lower close gap to the high wide gap, then restarts.
3. Open the layout-alignment page for `mad_scientist_lab`; use its marker/freeze controls to make any final pixel nudges without another restart.
4. Watch the two tube filaments, terminal spark bursts, lamps, and the five number drums for at least one ladder cycle.

No kiosk service was restarted, no active profile record was changed, and no live display was taken over during this work.
