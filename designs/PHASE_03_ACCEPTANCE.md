# Acceptance report — Phase 3 (editing while the kiosk runs)

Date: 2026-10-15. Jetson/Tegra aarch64, Python 3.10.12 (venv), pygame 2.6.1, NiceGUI 3.18.0,
pytest 9.1.1. Project: `/mnt/ssd/projects/pixel_dreams`, commits `316e6e6`, `843d667`, `38ad54b`.
Display facts the checks depend on: **no browser was used anywhere.** Page assertions run through
NiceGUI's in-process user simulation; process-level checks use the SDL dummy driver; the live
checks run against a real controller on `0.0.0.0:8090` with the real configs, driven over HTTP.

Legend: **PASS** verified here · **PARTIAL** partly verified · **PENDING** not yet verified.

## Automated (`SDL_VIDEODRIVER=dummy python -m pytest tests/` — 410 passed)

| Area | Coverage |
| --- | --- |
| Staging costs nothing | Staging and Revert change no bytes and create no backup; a Save with nothing staged does not rewrite the file. |
| The write itself | Only staged keys change; every other key, every other mode and the `profile` metadata block survive; a backup holds the previous content; a second Save is not a conflict with our own write; the file is re-readable. |
| Validation blocks writes | Out-of-range numbers, a fraction in an int field, a value outside a closed choice set, a cleared number box, and removing a required key are all refused WITH a reason, and the file is untouched. Unknown keys warn without blocking. |
| No circular validation | Field checks resolve their schema from the file's CURRENT values, never from the value just typed — a test stages a number into a text field and gets a refusal instead of a silently redefined field. |
| Conflicts | A file edited underneath us is refused, the message names which modes/keys changed, `Reload` clears it, and `force=True` is the only way past. |
| Untouchable values | A key supplied by the local override, and the structural keys, are refused; a mode that exists only in the override cannot be toggled. |
| Shared rules | `validate_configs.py` keeps no copy of the checks (a test fails if the messages reappear there); rendering/CLI output format pinned. |
| The real tree | A real profile round-trips through the editor with every other mode unchanged; all 8 real profiles validate clean; an edit touches only the file it was told to. |
| The generated form | Every shape renders with the right widget and is EDITABLE, except secrets (which have no widget at all) and fields whose value comes from the override or from the mode's own runtime; each read-only field states why. Save/Revert/Reload/Refresh buttons present; the disabled badge appears in the mode list; the status card reports the live rotation and shouts when every mode is disabled. |
| The loop end to end (real process, HTTP) | A parameter edit reaches the running loop and changes what the live mode was BUILT from (`mode_config_digest`); a disabled mode leaves the rotation and is never shown by it over several seconds of `--auto`; disabling everything keeps the wall alive and logs a warning; a mode disabled before startup is never rotated in; apply never writes the file; applying one profile leaves the other untouched; apply/refresh are gated on a non-loopback bind and ungated on loopback. |
| Unchanged behaviour | The 141 inherited pixel_drift tests still pass; 167 modes / 2508 fields coverage is 0-missing, as in Phase 2. |

No network and no paid calls. Every test that binds `0.0.0.0` uses a sandbox secrets file.

## Live verification (real project, real configs, running process on the LAN address)

| Check | Status | Evidence |
| --- | --- | --- |
| What is on the wall is what the file says | PASS | `applied_config_sha256` == the file's sha256; `mode_config_digest` == the digest of mode 0's config. Both true on a fresh start. |
| Edit → Save → Apply reaches the running mode | PASS | `refresh_hz` 2.0 → 2.5 through the real editor: backup written, apply accepted, `refresh_count` 0 → 1, and the live mode's digest CHANGED to match the edited file — while `uptime_s` kept climbing, i.e. same process. |
| The file is left exactly as found | PASS | The check's own edit was reverted and the config compared byte-for-byte with the backup taken before it: **identical** (`c5fc8ff9e531`). |
| The disable toggle changes the rotation live | PASS | Mode 33 disabled → 33 of 34 enabled, `disabled=[33]`, rotation ends `[30,31,32]`; re-enabled → 34 of 34, rotation restored, and the file byte-identical to the original again. |
| Every mode page of every real profile, live | PASS | Swept all 167 pages of all 8 profiles on the live instance: **0 non-200**, every page carries the editor, covering 1522 configured fields. |
| Configs still valid | PASS | `validate_configs.py --all` → 0 errors, 1 warning (pre-existing: a Windows path in an inherited profile). |

## Design §10 Phase 3 checks

| # | Check (the doc's words) | Status |
| --- | --- | --- |
| 1 | Write path with validation, conflict detection, atomic write + backup | PASS — `core/editor.py`; the rules live in `core/validation.py`, shared with the CLI |
| 2 | Save / Cancel semantics | PASS — Save & Apply, Save only, Revert, Reload; staging is free and a no-op Save writes nothing |
| 3 | `enabled` end to end (config → playlist → rotation) | PASS — honoured at startup and on apply, with the all-disabled fallback surfaced rather than silent |
| 4 | Refresh rebuilds a mode from the new config, no restart | PASS — measured above; queued if a fade is in flight and counted when it happens |
| 5 | Add/remove optional params | PASS — absent declared keys are editable in place (adding the key); `unset` removes one; required and override-supplied keys are protected |
| 6 | You eyeball it in a browser and tune the wall | **PENDING — yours.** Nothing here has been looked at by a human eye; the URLs below are ready. |

## Found during live verification (fixed in this phase)

1. **Enabling a mode wrote `"enabled": true` into the file**, so a disable → enable round trip left
   noise in a config a human reads. Now enabling REMOVES the key (the default needs no key), which
   makes the round trip byte-identical — proven live on the real config, and pinned by a test.
2. **`max_modes` was missing from the status until the first apply**, so a freshly started
   instance could not report how many slots a profile has. It is published from startup now, along
   with the mode's identity and build digest, so a consumer never has to guess whether a missing
   key means "not yet".
3. **`disabled_modes` reported empty in the all-disabled fallback**, which would have let the panel
   claim the flag was respected when the app was deliberately ignoring it. The status now reports
   the PROFILE's answer and the ROTATION's answer separately.

## Known deviations

1. `core/store.py`, `core/params.py` and `core/validation.py` shipped in earlier phases than the
   doc's plan (§10.2, §7). The write contract belonged with the first writer.
2. The enable switch writes immediately instead of staging (§12 Q7).
3. Absent keys are edited in place rather than through a separate "add a parameter" picker (§12
   Q8) — one way to do one thing.
4. Profile switching is still Phase 4: the panel says `PREVIEW` for a profile that is not on the
   display, and applying a non-active profile updates the config in memory without changing what
   plays.
5. `--play N` deliberately ignores `enabled`: an explicit request by slot number plays that mode.
6. A derived (`derived at runtime`) value is labelled and not editable; making those real params is
   Phase 5.

## Not verified at all

- **Any of it in a browser.** Everything above is machine-checked. Nobody has clicked a button,
  seen the staged-changes summary update as they type, or watched the wall change — that is the
  whole point of the URLs below.
- **The real tuning loop on the portrait wall** (the actual reason for this phase): change a font
  size in the portrait profile, Save & Apply, and judge it on the display. The mechanism is proven;
  whether the numbers look right is a judgement only you can make.
- **Simultaneous editors.** Two browser tabs are refused rather than merged (the second one gets
  the stale-file banner); concurrent editing is not supported and is not planned.
- **NiceGUI's live re-render on a slow link** — the form rebuilds on Save/Revert/Reload, which is
  fine in-process, but no one has watched it over a slow connection.
