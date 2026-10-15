# Acceptance report — Phase 4 (live profile switching, backups, raw editor, packaging)

Date: 2026-10-15. Jetson/Tegra aarch64, Python 3.10.12 (venv), pygame 2.6.1, NiceGUI 3.18.0,
pytest 9.1.1. Project: `/mnt/ssd/projects/pixel_dreams`, commits `5587b56`, `13fb5ef`.
Display facts the checks depend on: **no browser was used anywhere.** Page assertions run through
NiceGUI's in-process user simulation; process-level checks use the SDL dummy driver; the live checks
drive a real controller on `0.0.0.0:8090` with the real configs over HTTP.

Legend: **PASS** verified here · **PARTIAL** partly verified · **PENDING** not yet verified.

## Automated (`SDL_VIDEODRIVER=dummy python -m pytest tests/` — 444 passed)

| Area | Coverage |
| --- | --- |
| The active-profile record | Missing reads as empty; malformed content (junk, a list, `null`, a wrong-typed field) reads as empty rather than raising; a bare string is tolerated; writes are atomic and relative to the project root. |
| Precedence | `--config` beats the record beats the registry's setting beats the default; a recorded profile that has been DELETED falls through to the registry so a kiosk still boots. |
| One resolution | `load_project_config` loads what `resolve_active_profile` reports — asserted directly, including after a switch (this is the unification the phase exists for). |
| Switching | Records + returns a payload matching what a restart would load; refuses a missing file, a file that is not a profile, and a profile with validation ERRORS, writing NOTHING in each case; passes warnings through but still switches; switching back to the registry pick works. |
| Restore | Validate-before-overwrite; a refused restore leaves the file untouched; a valid restore is itself undoable (the replaced version is backed up first); the list is newest-first and scoped to one target; a non-profile file is refused. |
| Raw document staging | Supersedes per-mode staging; goes through the same validation (an invalid document is refused and the file stays); Revert clears it; a non-object document is refused. |
| The real tree | The real project switches landscape → portrait (24 modes) → back, with the loader agreeing at each step. |
| The switch over HTTP, real process | A switch changes what the wall plays: `applied_config_path`, the rotation (34 → 24 modes) and the live mode's build digest all move to the other profile's, with the process still running. The switch SURVIVES a restart (a second process with no `--config` loads the record and logs `via runtime`). Switching back works. A missing profile answers 404, a broken one 409 with the validation errors, and each refusal leaves the record unwritten and the app on its previous profile. An app started with `--config` refuses with the reason.  `/api/profiles` reports active + why. Every endpoint is token-gated on a non-loopback bind. |
| The pages, in-process | The switch button's real closure runs and queues an `apply_config` for the right profile; an already-active profile shows no button; a `--config`-pinned app explains itself; the two-step restore really replaces the file and queues an apply; `/raw` renders the document, refuses an invalid one without writing, and saves + applies a valid one. |
| Unchanged behaviour | Phases 1-3 stay green: 167 modes / 2508 fields coverage 0-missing, editing/apply/refresh, the 141 inherited pixel_drift tests. |

No network and no paid calls. Every test that binds `0.0.0.0` uses a sandbox secrets file.

## Live verification (real project, real configs, real process)

| Check | Status | Evidence |
| --- | --- | --- |
| Switch by HTTP moves the running app | PASS | Portrait applied: applied file `modes_config_portrait.json`, rotation 34 → 24 modes, `mode_config_digest` equal to the portrait file's live mode, `uptime_s` still climbing (no restart). |
| The record is written, and only that file | PASS | `runtime/active_profile.json` contained `{"profile": "configs/modes_config_portrait.json"}`; nothing else in the tree changed. |
| The choice survives a fresh process | PASS | Killed and restarted with no `--config`: startup logged `Using modes config: .../configs/modes_config_portrait.json (via runtime)` and the app played portrait's 24 modes. |
| Switching back works | PASS | Portrait → root: applied file back to `modes_config.json`, rotation back to 34 modes. |
| The machine was left as found | PASS | The record file (and the `runtime/` dir) were removed after the checks, and a final start with no record logged `via registry` and played the root profile — the original behaviour. No process left running, port 8090 free. |
| `systemd-analyze --user verify` on both units | PASS | No output (clean). The `--panel-only` ExecStart form was also run as written and served. |

## Design §10 Phase 4 checks

| # | Check (the doc's words) | Status |
| --- | --- | --- |
| 1 | `runtime/active_profile.json` + precedence + live reload of a different profile | PASS — measured above, including the restart |
| 2 | `/raw` | PASS — whole-document editor through the same write path; mode-page JSON stays read-only by decision (§12 Q15 / §10.4) |
| 3 | optional `/logs` | **NOT DONE — deliberately.** The panel is not the log sink: stdout goes to the journal (and to a file if you redirect it), and `/logs` would mean either tailing the journal from a web thread or keeping a second copy of every line in memory. `journalctl --user-unit pixel_dreams.service -f` is better at it than anything the panel could show, so the README points there instead. Say the word if you want it anyway. |
| 4 | "restore backup" action | PASS — two-step, validated, undoable |
| 5 | Packaging as a user service alongside the existing kiosk setup | PASS (as documentation, per this phase's scope) — `deploy/` with two verified example units matching the host's existing style. **Not installed and not enabled**: that is your call, and nothing here can run the kiosk for you |
| 6 | A request without the token is rejected from a non-loopback address | PASS — already shipped in Phase 1, re-asserted for the new endpoints |

## Known deviations

1. Two units rather than one (§12 Q15): the app needs a graphical session, `--panel-only`
   deliberately does not.
2. The mode page's raw JSON box stays read-only; `/raw` is the editing view for the whole document.
3. The unit files hardcode `DISPLAY=:0` and `XAUTHORITY=/home/ubuntu/.Xauthority`; a session that
   uses another display needs that line changed (noted in the file).
4. `/api/profile` answers 404 for a missing profile and 409 for a refused switch, rather than one
   code for both, so a script can tell "you named the wrong file" from "that switch is not allowed".

## Not verified at all

- **Any of it in a browser.** Everything above is machine-checked, including the button handlers —
  but nobody has *looked* at the profile card, the Backups list, or `/raw`. The URLs below are ready.
- **A switch on the real wall.** The live checks ran headless (SDL dummy), so the *picture* never
  changed: what changed was the rotation, the applied file and the live mode's build digest.
  Whether the wall actually redraws correctly at the new orientation (font sizes, layout) is your
  eyeball's job.
- **The service units in situ.** They verify clean and the ExecStart form runs, but neither unit has
  been installed, enabled, or started by systemd — so restarts, journal capture and the
  graphical-session environment are unproven in practice.
- **Two clients at once.** A profile switch from one browser while another has a mode form open:
  the second client's file is untouched (the profiles are different files), but its view of which
  profile is active only refreshes on its next poll. Not exercised.
