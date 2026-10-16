# pixel_dreams

A kiosk display app that runs one of many visual "modes" (screen-saver style apps)
fullscreen, plus a **web control panel for live tuning** — change a mode's parameters,
disable a mode, or switch profiles while the display keeps running, with no restart.

Born as a fork of [pixel_drift](../pixel_drift) (revision `e0b0e16`): the mode interface
contract, the registry/config format and all 53 modes are inherited unchanged. What
pixel_dreams adds is the panel and the plumbing the panel needs.

- one controller (`pixel_dreams.py`), one registry (`modes_registry.json`), one config
  per orientation (`modes_config.json` + `configs/*.json`), **53 visual modes**
- one pygame shell; modes never touch the display directly
- an embedded NiceGUI panel, in the same process as the display

## Usage

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # add -r requirements-dev.txt for the tests

python pixel_dreams.py --show_modes                      # list configured modes
python pixel_dreams.py --auto 30                         # cycle every 30s, fullscreen
python pixel_dreams.py --play 2 --windowed               # one mode in a window
python pixel_dreams.py --input rotary                    # Raspberry Pi rotary encoder

# with the control panel:
python pixel_dreams.py --auto 30 --panel-port 8090       # panel on http://127.0.0.1:8090/
python pixel_dreams.py --panel-only --panel-port 8090    # panel with no display at all
```

Keys: LEFT/RIGHT switch modes, ESC quits.

## Control panel

Off unless `--panel-port` is given (NiceGUI is imported lazily, so the kiosk runs
without fastapi/uvicorn loaded at all).

| Flag | Meaning |
| --- | --- |
| `--panel-port N` | serve the panel on port N (127.0.0.1 by default) |
| `--panel-bind ADDR` | bind address; a non-loopback address **requires** `panel_token` in `secrets.json` |
| `--panel-only` | serve the panel without initialising pygame — for preparing a profile offline |
| `--frames N` | exit after N frames (used by the verification tests) |

Pages: `/` (active profile + its mode list + live status + the profile switch + backups), `/raw`
(the whole profile document as editable JSON) and `/mode/<n>?profile=<rel>`, the generated parameter
form for one mode. See `designs/PIXEL_DREAMS_DESIGN.md`; the source of truth for what is actually
built is that doc's per-phase implementation records.

### Switching profile from the panel

The profile card on `/` shows the profile being inspected (choose it in the dropdown). If it is not
the one on the display, **Switch the display to <profile>** makes it active: the target is validated,
`runtime/active_profile.json` is recorded, and the running app is told to reload — the wall changes
profile with no restart, and the choice is what the next start loads.

WHICH profile is active, in order: `--config FILE` (a command-line pin), then
`runtime/active_profile.json` (what the panel writes, one line, gitignored), then
`modes_registry.json` → `settings.modes_config_file`. An app started with `--config` cannot be
switched from the panel and says so, because that flag would win again at the next restart.

### Creating a new config

**New config…** on the profile card creates a profile containing every mode `modes_registry.json`
knows about, so a new orientation starts with all the material and you can disable what does not
suit it. Name it, and it lands in `configs/` (`.json` is added if you leave it off) and appears in
the dropdown immediately.

Two things are worth knowing, because they are what the button is careful about:

- **A create never overwrites.** An existing name is refused with the reason and nothing is written —
  a create has no backup to fall back on, so it refuses rather than replaces. To change an existing
  profile, use Save, which backs up first.
- **The tuned values are copied from the profile you are looking at** (tick box, on by default). A
  mode the current profile already configures comes across exactly as it is; a mode it does not
  mention is included with its required keys filled from the registry's recorded defaults and
  everything else unset, for you to tune. Untick it for a file of bare registry defaults.

Anything the button could not do properly, it says rather than hides:

- **Required values that are empty** are written (the key has to exist for the profile to validate)
  and listed as *still needs a value* — a mode with an empty folder shows nothing until you point it
  somewhere.
- **A mode the registry declares but cannot be filled is left out, and named**, with the keys that
  were missing. It is left out rather than guessed at: the registry records no default for those
  keys, and a fabricated value would look configured while doing nothing. Give the registry a
  default for them and the next create includes it. (Today that is four types: `headlinesnews`,
  `animatedcityrain`, `chatreplay` and `antfarm`.)

The file is validated and written atomically through the same path as any other edit, so a new
profile cannot be born broken, and the dialog stays open showing the report.

### Backups and the raw editor

Every save keeps a timestamped copy of the profile in `.backups/` (newest 20 per file). The
**Backups** section on `/` lists them for the inspected profile and restores one — in two steps, and
the restore itself is undoable because the version it replaces is backed up first.

`/raw` edits the whole profile document as JSON. It is the tool for restructuring (copying a mode
block, pasting several), and it goes through the same validation, atomic write, backup and
conflict refusal as the form: it is another view of one write path, not a second one.

### Running it as a service

`deploy/` has two example user units (the kiosk with the embedded panel, and `--panel-only` for
tuning with no display) plus install, log and token notes. Neither is installed or enabled — see
`deploy/README.md`.


### Tuning a mode while the kiosk runs

Open `/`, click `params →` on a mode, change the values you want, then **Save & Apply**: the file
is written (validated, atomic, with a timestamped backup in `.backups/`) and the running app is told
to reload and rebuild that mode — you see the change on the wall without a restart. `Refresh this
mode now` rebuilds it again from the config already loaded, which is what you want after adjusting
something the mode re-reads on construction.

The `Enabled in the rotation` switch writes immediately and takes the mode in or out of the
rotation, so a mode that only looks right in one orientation can be switched off per profile. If
every mode in a profile is disabled the app plays them all anyway and logs a warning, rather than
leaving the wall blank.

Fields the panel will not write, each saying why on the page: secrets (they live in
`secrets.json`), values supplied by `modes_config.local.json` (that file wins over the profile), and
values the mode computes at runtime. A field badged `not set in this profile` is declared by the
registry but absent from the file — editing it adds the key, `unset` removes one.

If the file changed underneath you (another tab, an ssh edit), Save is refused and the page says
what changed, until you press `Reload from disk`. Nothing is written that you did not see.

### Making a variant of a mode

Every row in the mode list has a **duplicate** button. It copies that mode into the **next free slot**
and writes the profile, so you can then open the copy's own params page and change what makes it
different — a different folder, a different font size, a different palette — without touching the
original.

What the copy is, exactly:

- **A verbatim copy of every setting**, including whether it is enabled. The one deliberate difference
  is the name: the copy is called `<name> copy` (then ` copy 2`, ` copy 3` if that is taken), because
  two identical labels in a list of thirty-odd modes is a trap. A mode with no name is left unnamed —
  you can see its type in the list anyway.
- **Written immediately, and applied if it is the profile on the display**, so the copy exists to open
  straight away. If its source was enabled, the copy is now in the rotation too, playing the same
  thing twice until you change it — the message says so, and its switch in the list turns it off if
  you would rather tune it first. If the source was disabled, the copy stays disabled.
- **One click, no confirmation**, because it is additive and easy to undo: the copy is an ordinary
  mode you can edit, disable, or remove from its own params page, and every write keeps a backup.

It goes through the same write path as any other change — validated, atomic, backed up — with one
extra guard: if the slot it was going to use appeared in the file in the meantime (another tab, a hand
edit), it refuses instead of landing on someone else's mode.

Scripted: `curl -H "X-Panel-Token: $TOKEN" -X POST http://jetsons:8090/api/duplicate -H
'Content-Type: application/json' -d '{"index": 3}'` — add `"profile": "configs/..."` to duplicate in
a profile other than the active one.

### Changing modes by hand

Under **Display status** there are two buttons: **◀ Prev** and **Next ▶**, one press per mode. Use
them when you want to drive the rotation yourself instead of leaving it to `--auto`; the line beside
them says where you are and what is either side (`showing mode 7 — 8 of 34 in the rotation · next 8,
prev 6`).

A press is exactly what LEFT/RIGHT already does on the keyboard, including the useful part: if a
transition is in flight the step is **queued rather than dropped**, so clicking Next three times
quickly advances three modes. With `--auto` running, a manual step restarts its timer, so the mode
you picked gets a full interval rather than the remains of the old one.

The buttons disable themselves and say why in two cases: an app started with `--play N` has a single
mode and no rotation to step through, and `--panel-only` has no display to step.

Scripted equivalents, all token-gated and (except the profile record) read-only on disk:

```bash
curl -H "X-Panel-Token: $TOKEN" http://jetsons:8090/api/status
curl -H "X-Panel-Token: $TOKEN" http://jetsons:8090/api/profiles
curl -H "X-Panel-Token: $TOKEN" -X POST http://jetsons:8090/api/refresh
curl -H "X-Panel-Token: $TOKEN" -X POST http://jetsons:8090/api/step -d '{"delta": 1}'   # or -1
curl -H "X-Panel-Token: $TOKEN" -X POST http://jetsons:8090/api/profile/new \
     -H 'Content-Type: application/json' -d '{"name": "modes_config_livingroom", "inherit": true}'
curl -H "X-Panel-Token: $TOKEN" -X POST http://jetsons:8090/api/apply \
     -H 'Content-Type: application/json' -d '{"profile": "configs/modes_config_portrait.json", "refresh": true}'
curl -H "X-Panel-Token: $TOKEN" -X POST http://jetsons:8090/api/profile \
     -H 'Content-Type: application/json' -d '{"profile": "configs/modes_config_portrait.json"}'
```

`/api/step` answers `{"ok": true, "queued": 1}` and deliberately does NOT report the new mode: the
loop applies the step on its next frame, so a `mode_index` read at request time would be the position
*before* the step. Poll `/api/status` for `mode_index` (and `last_step` to confirm), which is what the
acceptance runs and the tests do. It answers 400 for a delta that is not ±1 and 409 for an app locked
to a single mode.

`/api/apply` re-reads a profile from disk and applies it (the same path the button takes, minus the
write) — handy after editing a file by hand or pulling a commit. `/api/profile` is the switch: it
validates, records and applies, and answers 404 for an unknown profile or 409 when it refuses (a
broken profile, or an app started with `--config`).

Panel reach: loopback by default. To open it from another machine, add
`"panel_token": "<long random string>"` to `secrets.json` (gitignored — see
`secrets.example.json`) and start with `--panel-bind 0.0.0.0`, then visit
`http://<host>:8090/?token=<the token>` once. That sets an httpOnly cookie which lasts **60 days**,
so the token is not needed again in that browser until it expires (or you change the token, which
invalidates every existing cookie). Scripts should send `X-Panel-Token: <token>` instead — that
form is never remembered as a cookie.

## Configuration

- `modes_registry.json` — mode *types* (entrypoints + defaults + per-param UI metadata)
- `modes_config.json` — mode *instances* (what actually plays)
- `configs/*.json` — **profiles**: one per display orientation (portrait, landscape,
  narrow_horz, narrow_vert, jetson, windows, basic)
- `modes_config.local.json` — optional per-host overrides (gitignored)
- `secrets.json` — API keys and the panel token (gitignored, see `secrets.example.json`) with
  chmod 600
- `runtime/active_profile.json` — which profile is active (gitignored, written by the panel)
- `.backups/` — timestamped copies of a profile taken just before each save (gitignored, newest 20
  kept per file). If a save ever goes wrong, the previous file is here.

Any mode may carry `"enabled": false` to opt out of the rotation; a profile where every mode is
disabled still plays them all, with a warning in the log, so a mistake cannot blank the wall.

Validate everything after editing:

```bash
python validate_configs.py --all
```

The parameter exposure audit (what is NOT tunable yet, and what it would take):

```bash
python3 scripts/audit_params.py                       # the knobs worth reviewing
python3 scripts/audit_params.py --mode blinkenlights  # one mode
```

Read-only. Its findings and recommendations are in `designs/PHASE_05_PARAMETER_AUDIT.md`.

See AGENTS.md for the developer guide, including the panel's thread rules.

### Pointing a control panel at your own artwork

The `controlpanel` mode draws its animated overlays (needles, lamps, scopes, readouts) over a
background PNG. There is one PNG per mode, and the mode owns it: the `background_image` parameter.

    blank         use whatever artwork the layout file names (the default)
    a bare name   looked up under assets/control_panel/backgrounds/  (e.g. steampunk1.png)
    a path        used as given, so it can live anywhere on disk
                  (e.g. /mnt/ssd/projects/images/panel.png, or ./pics/panel.png)

So one layout can be reused over different pictures without editing any JSON: open the mode in the
panel, type the path, press Save. Two things are worth knowing, because otherwise they bite quietly:

  * the artwork only SHOWS on a freeform layout. A grid layout builds its panels from the skin and
    has no background image at all, so it refuses an artwork override and says so, rather than
    accepting it and drawing something else.
  * when a layout declares no `design_resolution`, its canvas IS the artwork's size — so pointing at
    a taller PNG moves the coordinate space every overlay is measured in. On a portrait wall that is
    usually what you want; the alignment page reports the canvas it is working in.

`modes/control_panel_mode.py` documents the mode's config keys, and `tests/test_background_param.py`
pins the resolution rules and the refusals.

The alignment page draws its boxes over the SAME artwork the display is drawing, and says which
one that is and where it came from. If the two ever disagreed, every position on that page would
be measured against the wrong picture.

### Editing a layout as JSON, and picking a layout instead of typing it

A layout is a JSON file, and the params page now offers the layouts on disk as a dropdown — with the
box still accepting a typed path, because a layout may live anywhere:

    layout_file   dropdown of assets/control_panel/layouts/  +  any path you type
    background_image   dropdown of assets/control_panel/backgrounds/  +  any path you type

A field only becomes a picker when the schema names where its known values come from, so this stays
opt-in per key rather than a guess about which strings are paths.

For what the boxes and the nudge pad cannot express — pasting a whole panel in, fixing a sprite id,
moving three overlays one line each — every layout page has a "raw JSON →" link. That editor goes
through the same writer as the page it came from: validated by the package's own loader, written
atomically with a backup, and refused if the file changed underneath. Validate never changes what Save
would write, and if the display is showing that layout the mode is rebuilt after a save; if it is not,
the page says so rather than pretending.

### Editing a control: copy it, or colour it

Every row on the alignment page has a **duplicate** button. It copies that overlay, nudges the copy
24px clear (clamped inside the canvas, because a box outside it cannot be nudged back), inserts it next
to its source and writes the file straight away — so the wall rebuilds and you can nudge the copy
against what the display is really showing. The copy becomes the selection, since the first thing you
do with a copy is move it.

With an overlay selected, **Colours** lists the drawn colours *that control actually reads*, from
`controlpanel.controls.COLOUR_KEYS` (a test walks every class and its bases to hold that table to the
code):

    gauge_round / meter_vu   needle_rgb, hub_rgb      clock        hand_rgb
    scope / strip_chart      trace_rgb                tape_reel    spoke_rgb
    bar_graph / readouts     color_rgb                keypad       entry_rgb...
    toggles, knobs, buttons  lever_rgb, pointer_rgb, ring_rgb
    lamp / lamp_square / lamp_rect   color_rgb — the sprite's colour is only the default
    led_bar, lamp_bank       color

`color` is the universal key and wins over all the others. Setting one writes immediately and rebuilds
the mode, for the same reason a copy does: a control resolves its colours when it is built. `default`
clears the key and hands the colour back to the control.
