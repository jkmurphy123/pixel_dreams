# pixel_dreams

A kiosk display app that runs one of many visual "modes" (screen-saver style apps)
fullscreen, plus a **web control panel for live tuning** — change a mode's parameters,
disable a mode, or switch profiles while the display keeps running, with no restart.

Born as a fork of [pixel_drift](../pixel_drift) (revision `e0b0e16`): the mode interface
contract, the registry/config format and its modes are inherited unchanged. What
pixel_dreams adds is the panel and the plumbing the panel needs.

- one controller (`pixel_dreams.py`), one registry (`modes_registry.json`), one config
  per orientation (`modes_config.json` + `configs/*.json`), **64 visual mode types**
- one pygame shell; modes never touch the display directly
- an embedded NiceGUI panel, in the same process as the display

Recent scenic additions include Sunrise, Space Station V, Cyberspace Matrix,
Trench Run, **The Glass Castle** (SLOW_WORLDS_DESIGN.md §5.13) and **Terraform**
(SLOW_WORLDS_DESIGN.md §5.15).

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
| `--panel-bind ADDR` | bind address; a non-loopback address **requires** `panel_token` in `secrets.json` (or `--panel-open`) |
| `--panel-open` | serve with **no token gate** on any bind — anyone who can reach the address can read and change configs |
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

`deploy/` has three example user units (the kiosk with the embedded panel, `--panel-only` for
tuning with no display, and a Raspberry Pi kiosk with its own profile and the rotary encoder) plus
install, log and token notes. None is installed or enabled — see `deploy/README.md`.

### Raspberry Pi kiosk with a rotary encoder

The controller already understands a rotary encoder. This kiosk is a **1280x400 landscape
wall**, so it needs its own **profile**, **gpiozero**, and a **pin map**.

**1. Its own profile.** The Pi runs `configs/modes_config_narrow_horz.json` — the narrow
horizontal profile, now 21 modes. Trench Run is slot **17**, Cyberspace Matrix is slot **18**,
Space Station V is slot **19** and Sunrise is slot **20**; the 3-D scenes are tuned for the
1280x400 aspect (minimal HUD, a lower camera, a closer draw distance, and the Cyberspace landmark
inset off because it would eat half the height). The profile's display-only
`profile` block records `resolution: [1280, 400]`, so the panel labels it correctly.

Start the Pi with `--config configs/modes_config_narrow_horz.json`. `--config` outranks
`runtime/active_profile.json` and the registry, so a profile switch recorded on another wall cannot
change this one; the panel also stops offering profile switches, because the command-line pin would
win again at the next restart. The portrait wall keeps `configs/modes_config_vert.json`: the two
kiosks use separate files, so tuning the Pi cannot reach the portrait wall. Host-only media paths
belong in `modes_config.local.json` (gitignored).

**2. gpiozero and GPIO permissions.** On Raspberry Pi OS, the encoder needs gpiozero plus the
`lgpio` pin factory. The easy path is a venv that can see the distro's copies:

```bash
sudo apt install python3-gpiozero python3-lgpio
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
```

If your venv was created without `--system-site-packages`, either recreate it that way or install
`lgpio` into it (the pip build needs `swig` and `liblgpio-dev`). The app must be able to open
`/dev/gpiochip*`: run it as the `pi` user (member of `gpio`), or add `SupplementaryGroups=gpio`
to a system unit. `--input rotary` never crashes without gpiozero: it prints a `[Hardware]` line
and falls back to the keyboard.

**3. Pins.** Defaults are **BCM GPIO numbers**, not header pin numbers:

| Signal | Default BCM GPIO | Notes |
| --- | --- | --- |
| Encoder A | 17 | `--rotary-pins 17,27` |
| Encoder B | 27 | |
| Encoder button | 23 | to GND, internal pull-up; `--rotary-button-pin` |
| Mode LEDs (optional) | 5, 6, 13, 19, 26, 21, 20, 16 | `--rotary-led-pins ""` for no LEDs |

```bash
./scripts/run_pi_kiosk.sh                              # defaults, no panel
./scripts/run_pi_kiosk.sh --rotary-pins 5,6 --rotary-button-pin 12
./scripts/run_pi_kiosk.sh --rotary-led-pins ""         # no LED ring
./scripts/run_pi_kiosk.sh --panel-port 8090            # panel on 127.0.0.1 only
./scripts/run_pi_kiosk.sh --windowed --width 1280 --height 400  # test on a desktop
```

Turning the knob steps Next/Prev through the profile's enabled rotation. A fast spin arrives as one
accumulated delta, and a step that lands mid-fade is queued rather than dropped (the panel shows
`stepped next (rotary)`). A short press exits, and a 2s hold reboots (`--rotary-hold none` disables
that). The hold runs `sudo -n reboot`, so the run user needs passwordless sudo for `/sbin/reboot`;
a systemd unit with `NoNewPrivileges=true` blocks it.

**4. Start it at boot.** `deploy/pixel_dreams-pi.service` is a user unit that pins the Pi profile
and passes `--input rotary`. Adjust its display block for X11 (Bullseye) or Wayland (Bookworm), then:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/pixel_dreams-pi.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now pixel_dreams-pi.service
journalctl --user-unit pixel_dreams-pi.service -f
```

The panel is off in that unit. Add `--panel-port 8090` (and, for the LAN,
`--panel-bind 0.0.0.0 --panel-open`) to `ExecStart` if you want it. The Pi's profile file is what
the panel edits, so tuning the Pi cannot reach the portrait wall.

> The newest modes are `modes/cyberspace_mode.py`, `modes/trench_run_mode.py`,
> `modes/space_station_mode.py`, `modes/sunrise_mode.py` and the
> `cyberspace/` / `trench_run/` / `space_station/` / `sunrise/` packages (slots 17, 18, 19 and 20
> in `configs/modes_config_narrow_horz.json`, and Sunrise slot 64 in the portrait
> `configs/modes_config_vert.json`). Space Station V also needs
> `data/earth_coastlines.json`; its design is in `designs/SPACE_STATION_DESIGN.md`. Sunrise is the
> four-season forest day cycle; its art and notes are in `designs/sunrise_proto/`. A Pi cloned from
> an older revision will not have them; make sure those files and their registry entries are on
> the Pi before enabling those slots.

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

On a trusted LAN you can skip the token entirely: `--panel-bind 0.0.0.0 --panel-open` serves the
panel with no gate, so `http://jetsons:8090` just opens. This is an explicit command-line choice,
not a config setting: it makes the panel readable AND writable by anyone who can reach that
address (and the LAN is the trust boundary). The app says so at startup
(`[Panel] Control panel on … UNGATED (--panel-open)`) and on the panel's status card. Drop the
flag to put the token gate back.

This repo's own launch paths already pass the flag — `scripts/run_kiosk.sh` for a manual start and
`deploy/pixel_dreams.service` for the service — so a restart never re-arms the gate. The flag has
to live in the command that starts the process: a gated panel cannot remember anything except a
browser cookie, and a cookie that a private window, a "clear on exit" setting or the IP instead of
the hostname discards will ask for the token again.

## Configuration

- `modes_registry.json` — mode *types* (entrypoints + defaults + per-param UI metadata)
- `modes_config.json` — mode *instances* (what actually plays)
- `configs/*.json` — **profiles**: one per display orientation (portrait, landscape,
  narrow_horz 1280x400, narrow_vert, jetson, windows, basic)
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

### What each control type looks like

The add-overlay dialog describes the type you have selected, in the class's own words, plus the keys
that type lets you override. That matters more than it sounds: the catalogue is 24 types and the names
do not say what their shapes are. The lamp family, for instance:

    lamp          a round glow (halo + bright core)
    lamp_square   the same lamp, drawn as a square glow
    lamp_rect     the same lamp, drawn as a rectangle wider than it is tall
    lamp_bank, led_matrix   grids of lamps

All three lamps blink and fade identically, take `color_rgb` (and the universal `color`), and add
`size`; only the drawn shape differs. Proved by measuring them rather than by name —
`tests/test_lamp_shapes.py` draws each one alone and asks whether it fills its own bounding box's corner,
which a circle never does.
