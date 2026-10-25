# inkmap design-time prototypes

**Throwaway probes, not application code.** Nothing here is imported by
`pixel_dreams.py`, any mode, or any test. They exist so the numbers and the
calibration rules in `designs/INK_FANTASY_MAP_DESIGN.md` can be re-derived
instead of trusted, and so the prototype renders can be looked at again.

| File | What it is |
|---|---|
| `COST_SPIKE.py` | the measurement run behind §3 of the design doc: per-op costs, the dirty-rect flush table, supersample downscale, memory, the end-to-end stroke budget. Writes to stdout only. |
| `cost_spike_output.txt` | its recorded output |
| `PRIMITIVES.py` | the drawing vocabulary (pen widths from real nib millimetres, the `Hand` tremor model, `pen`/`curve`/`dot`) plus the land, water and feature recipes, as prototyped |
| `SHEET.py` | composes one finished sheet: pour rice → trace contour → continent border → water → terrain zoning → mountains, hills, rivers, desert, forest, grass. Writes `ref_render.png` next to itself. |
| `ref_render.png` | the last `SHEET.py` render (1080×1920) |
| `REGISTRY_CHECK.py` | injects the registry block from the design doc's §6 into the real registry and runs the app's own `validate_registry` / `resolve_params` / `validate_profile` over it, with controls proving the value checks refuse bad input. Exits non-zero if the draft entry does not pass. |
| `registry_check_output.txt` | its recorded output (VERDICT: PASS) |
| `VIDEO_TRANSCRIPT.txt` | transcript of part 1, used for §1 |
| `VIDEO2_TRANSCRIPT.txt` | transcript of part 2, used for §1b |

## Running them

```bash
cd /mnt/ssd/projects/pixel_dreams
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python designs/inkmap_proto/COST_SPIKE.py
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python designs/inkmap_proto/SHEET.py
                .venv/bin/python designs/inkmap_proto/REGISTRY_CHECK.py
```

Everything is off-display (`SDL_VIDEODRIVER=dummy`); none of it touches the wall.
`ref_render.png` is the honest state of the prototype: the coast, the sea and the
paper read as hand-drawn, the inland features are still too sparse and too uniform —
which is rules 4, 5 and 6 of the design doc's §5 not yet applied.
