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

Scripted equivalents, all token-gated and (except the profile record) read-only on disk:

```bash
curl -H "X-Panel-Token: $TOKEN" http://jetsons:8090/api/status
curl -H "X-Panel-Token: $TOKEN" http://jetsons:8090/api/profiles
curl -H "X-Panel-Token: $TOKEN" -X POST http://jetsons:8090/api/refresh
curl -H "X-Panel-Token: $TOKEN" -X POST http://jetsons:8090/api/apply \
     -H 'Content-Type: application/json' -d '{"profile": "configs/modes_config_portrait.json", "refresh": true}'
curl -H "X-Panel-Token: $TOKEN" -X POST http://jetsons:8090/api/profile \
     -H 'Content-Type: application/json' -d '{"profile": "configs/modes_config_portrait.json"}'
```

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

See AGENTS.md for the developer guide, including the panel's thread rules.
