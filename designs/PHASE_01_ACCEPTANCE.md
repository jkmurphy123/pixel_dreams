# Acceptance report — Phase 1 (fork, scaffold, panel on the wire)

Date: 2026-10-15. Jetson/Tegra aarch64, Python 3.10.12 (venv at `/mnt/ssd/projects/pixel_dreams/.venv`),
pygame 2.6.1, NiceGUI 3.18.0, fastapi 0.143.2, uvicorn 0.54.0, pytest 9.1.1.
Project: `/mnt/ssd/projects/pixel_dreams` (forked from `pixel_drift@e0b0e16`), commits `eabc5e3`,
`b703025`, `7cc2225`, plus the wiring commit.
Display facts the checks depend on: **no display was used**. Every run here used the SDL dummy
video driver, so the panel-only claim could be tested against an intentionally invalid driver.
There is no kiosk service running on this host and no browser was opened.

Legend: **PASS** verified here · **PARTIAL** partly verified · **PENDING** not yet verified.

## Automated (`SDL_VIDEODRIVER=dummy python -m pytest tests/` — 200 passed)

| Area | Coverage |
| --- | --- |
| Inherited suite | The 141 pixel_drift tests still pass unchanged on the renamed tree (modes construct, entrypoints import, configs validate, control-panel/dungeon/satellite/wargames units). |
| Profile discovery (`core/profiles`) | Real tree yields ≥8 profiles with exactly one flagged active and it matches `resolve_active_profile`; malformed profile reported as an error, never raised; `profile` metadata is display-only and does not leak into the mode list; labels derived per filename; precedence `--config` > registry setting > default. |
| Override layer | `merge_local_override` applies `modes_config.local.json`, reports which keys each mode number takes from it, does not mutate its input, and can add a whole mode; override keys reach the mode entries. |
| Control bus | Drain capped at 8/frame (20 commands → 8+8+4); caller's dict is copied; unknown command counted not raised; a raising handler is skipped and the loop survives; snapshot is an isolated deep copy; **500 commands across a real producer/consumer thread pair with zero loss and zero duplication**. |
| Access rule | Loopback open; non-loopback requires a token; header beats cookie beats query; a non-loopback bind with no token is refused before nicegui is imported. |
| Panel pages (in-process render) | Active profile + its modes render with real names; live status text comes from the bus; a profile that is not active is labelled PREVIEW and the unknown-profile case falls back; the Ping button posts a real command; a broken profile renders an error instead of a crash. |
| Panel pages (gated) | Network-bound panel answers 403 on `/` and `/api/status`, leaks no mode data; loopback is open; the query token opens the page; the auth route sets the cookie and the cookie opens the page. |
| Process-level (real app) | With the panel off, `nicegui` is never imported and the run completes at 59+ fps; with it on, `/api/status` serves the live loop, a ping round-trips to `pong_count>=1`, and the page renders; `--panel-only` serves with an invalid SDL driver and reports `display=off, frame=0`; non-loopback without a token exits 2 with an actionable message; non-loopback with a token is 403-gated and the browser cookie flow works; `core.bus`/`core.profiles` import without pulling in nicegui/pygame/fastapi/uvicorn. |

No network calls and no paid calls were made by any test; the one test that binds `0.0.0.0` did so
for a few seconds on loopback-only assertions. Full suite runtime ≈ 30s.

## Live verification

| Check | Status | Evidence |
| --- | --- | --- |
| Riskiest integration: a web server inside the pygame process | PASS | 1500-frame run with the panel live: `avg_fps=58.8`, `rss_mb=87.1`, `nicegui_imported=True`; identical run without the panel: `avg_fps=59.3`, `rss_mb=41.3` (panel costs −0.8% fps, +45.8 MB). |
| Panel → render loop command path, on the real app | PASS | `GET /api/ping` → `{"queued":true,"pending":1}`; 1s later `/api/status` showed `pong_count` 0→1, `commands_applied` 0→1, `last_command=ping`. |
| Modes cycle while the panel lists them | PASS | `--auto 4`: `/api/status` `mode_index` 1 → 2 → 3 across ~9s; page HTML contained `StatusTicker`, `Cyberart`, `ACTIVE`, and the profile paths. |
| Active-profile reporting | PASS | 8 profiles listed; exactly one (`modes_config.json`) flagged active, `profile_source=registry`. |
| Panel-off import isolation | PASS | Summary line `nicegui_imported=False panel=off`; asserted again as a test. |
| LAN token gate | PASS | Bound `0.0.0.0` with `PANEL_TOKEN`: `/` and `/api/status` → 403 without the token, 200 with it; `/_panel/auth?token=…` set the cookie and the follow-up request rendered the panel. |
| Panel-only with no display | PASS | Run with `SDL_VIDEODRIVER=definitely-not-a-real-driver` (any display init would fail): served fine, `display=off`, `frame=0`, no traceback. |

## Design §10 Phase 1 checks (the doc's own acceptance list)

| # | Check | Status |
| --- | --- | --- |
| 1 | `python pixel_dreams.py --auto 30 --windowed --panel-port 8090` cycles modes while `http://127.0.0.1:8090/` lists them | PASS — same run with `--auto 4 --panel-port 8091`; modes cycled and the page listed them |
| 2 | fps before/after enabling the panel measured and reported | PASS — 59.3 → 58.8 fps over matched 1500-frame runs |
| 3 | RSS with the panel on/off recorded | PASS — 41.3 MB → 87.1 MB |
| 4 | panel OFF = nicegui never imported (assert it) | PASS — asserted in the process test and observable in the run summary |
| 5 | `--panel-only` serves the same page with no display initialised | PASS — invalid-driver run, `display=off` |
| 6 | `--panel-port 8090` (loopback default) + lazy import | PASS |
| 7 | read-only `/` page listing profiles + modes + live status | PASS — writes no file; Phase 1 has no write path at all |
| 8 | ControlBus with a bounded drain | PASS — cap 8/frame, unit-tested incl. the thread handoff |
| 9 | `--panel-bind` + token gate as decided at review | PASS — pulled forward from Phase 4 (deviation 1, with reason) |

## Known deviations

1. **Token gate and `--panel-bind` shipped in Phase 1**, not Phase 4 (§10.1 deviation 1). Reason:
   the flag exists as soon as the panel does. The gate is an HTTP middleware because a page-level
   guard answers 200 with a refusal page — a test asserting 403 caught that.
2. **`--frames N` added** as a verification affordance; without it the fps/RSS/import claims are
   not reproducible.
3. **`/api/status` and `/api/ping` added**; `/api/ping` is what proved the panel→loop path against
   the real process.
4. **`?profile=<rel>`** chooses the inspected profile, because NiceGUI 3.18's select change event
   cannot be driven from the test harness (its handler reads front-end props that only exist in a
   browser). The page-builder guard for unauthorised requests is therefore unreachable over HTTP in
   this build; it remains as defence in depth and is unit-tested through the access-rule matrix.
5. **`secrets.json` was not gitignored** in the inherited tree (AGENTS.md claimed it was). Fixed
   here. The kiosk's copy of pixel_drift should be checked — a real key file would be committable.
6. Modes 2 and 3 of the root profile render nothing on this machine: the inherited config points at
   the kiosk's image folders. Expected, and the case the local-override layer exists for.
7. `validate_configs.py --all` reports 0 errors and 1 warning, identical to pixel_drift before the
   fork (a Windows path in an inherited profile: `G:\images\...`).

## Not verified at all

- **Real browser rendering and visual layout.** Everything above is headless: in-process page
  builds plus HTTP responses. Nobody has LOOKED at the page in a browser yet, and no screenshot was
  taken. Prerequisite: open the panel on the kiosk (or from a laptop with `--panel-bind` + token).
- **Real display output on the kiosk** (fps/RSS under the actual GPU/display path, and whether the
  auto-cycle feels right on the wall). This host has an X socket but no session; all measurements
  used the dummy driver, so the fps numbers are a *relative* comparison, not the kiosk's absolute
  frame rate.
- **Long-run stability** (hours/days, memory creep with the panel attached) and behaviour on
  Raspberry Pi class hardware, including whether the +46 MB is acceptable there.
- **A second panel client** (two browsers polling one panel) — the design supports it (each client
  gets its own page instance) but it has not been exercised.
- **Phase 2-4 content**: the param schema, dynamic forms, editing, enable/disable, refresh, profile
  switching. Only the read-only listing they build on exists today.
