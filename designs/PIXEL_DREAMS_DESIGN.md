# pixel_dreams — design document (for review, before any coding)

Status: DRAFT for review. Date: 2026-10-15. Author: Hikari (with the user).
Scope: the application, the live-tuning web control panel, and the phased build plan.

Convention used throughout this doc:

- **MEASURED** = I ran a command or read the code and have the output. Evidence is named.
- **ASSUMED** = believed, not yet proven. Every ASSUMED item is either probed in Phase 1 or
  called out as an open decision.

---

## 1. What is being asked for

pixel_drift works and its config method is fine. The problem is the tuning loop: to change a
font size or a colour in a mode you edit JSON by hand and restart the app, which is painful when
you are dialling in the same mode across portrait / landscape / narrow-orientation profiles.

pixel_dreams keeps the same architecture (one controller, many visual modes, one JSON config per
orientation) and adds **a web control panel that talks to the running application**:

1. pick the active profile (config file) from a dropdown — the one that is actually on the wall
2. pick a mode from that profile's list
3. get a form **generated from that mode's parameters and their current values**
4. edit values, then **Save** (write the JSON) or **Cancel** (discard)
5. toggle a mode **off** without deleting it
6. hit **Refresh** and watch the live mode restart on the new parameters — no app restart

Out of scope for this doc: rewriting the modes. The mode interface contract does not change.

---

## 2. Resolved decisions (measured before designing)

The riskiest assumption in the obvious design is "a NiceGUI web server can live in the same
process as the pygame render loop without wrecking the frame rate". That was **probed, not
assumed** — probe script kept at `designs/arch_spike_probe.py`, run on this host
(Jetson/Tegra, aarch64, Python 3.10.12) on 2026-10-15.

| # | Question | Measured answer | Consequence for the design |
|---|----------|-----------------|----------------------------|
| D1 | Can NiceGUI's uvicorn server run in a background thread while pygame owns the main thread? | **YES** — panel served on 127.0.0.1:8099, `/api/health` answered with `main_thread: False` | In-process panel is viable. No second process, no IPC layer. |
| D2 | Can an HTTP request hand a command to the render loop? | **YES** — `GET /api/refresh` → queue → loop drained it: `refresh_count=1`, `params={'font_size': 96}` | The Save/Refresh/Profile-switch buttons all work through one queue. |
| D3 | Does the panel thread cost frame rate? | **NO** — 62.3 fps sustained live sample with the panel serving (SDL dummy driver) | Render loop is untouched; the panel never does work on the frame path. |
| D4 | Crash-safe config write round-trips? | **YES** — temp sibling + `fsync` + `os.replace`, re-read identical (sha256 `6fec1cdf501e`), no leftover tmp | Use this for every write. A kiosk loses power; a torn config is a dead display. |
| D5 | Do param value types conflict across profiles? | **NO** — 0 conflicts across 8 config files, 279 distinct param keys | Per-**type** param schemas are safe; no per-instance typing needed. |
| D6 | Are all params flat scalars? | **NO** — params include `list[int]` (RGB), `list[float]` (ranges), `list[str]` (labels), `list[list[int]]` (palette), and `list[dict]` (`devices`: list of `{hostname,name,role}`) | The form needs real typed editors plus a raw-JSON escape hatch. Generic "text box" would corrupt data. |
| D7 | Is the registry's `required`/`optional` list a complete list of a mode's knobs? | **NO** — 6 types read config keys that are not declared: `blinkenlights`, `headlinesnews`, `penrosetiling`, `quotegenerator`, `slideshow`, `statusticker` (e.g. slideshow reads `dow_symbol`, `overlay_margin`, `scale_mode`, `scaled_cache_items`) | A form built only from the registry would silently hide real knobs. Schema must be inference-first. |

Dependency versions installed and verified working together on this host: pygame 2.6.1,
nicegui 3.18.0, uvicorn 0.54.0, fastapi 0.143.2, Python 3.10.12 (`/usr/bin/python3`).
**ASSUMED:** the same stack installs and holds its frame rate on the target kiosk hardware;
Phase 1 measures RSS and fps there.

### 2.1 Confirmed at design review (2026-10-15)

| Decision | Answer | Effect on this doc |
|---|---|---|
| Fork vs in-place | **New repo `pixel_dreams`, forked with history; pixel_drift frozen as the fallback app.** | §4 stands as the plan; the fork commands in §4 are step 1 of Phase 1. |
| Panel reach | **Loopback by default; LAN only with `--panel-bind 0.0.0.0` plus a token from `secrets.json`.** | Token gate shipped in **Phase 1**, not Phase 4: `--panel-bind` exists from the first release of the panel, so the gate that makes it safe had to ship with it. Loopback remains the default everywhere. |
| Sparse profiles | **The form may add and remove optional parameters per profile.** | Phase 3 includes the add/remove-optional-param controls (§8), not just editing existing keys. |
| Panel without a display | **`--panel-only` is wanted.** | Added to Phase 1, not deferred — it also makes Phases 2-3 testable without a display attached. |

Taken as recommended defaults (object at any time, nothing depends on them): §6.2's `profile` metadata
block for readable dropdown labels, and the "derived at runtime" tag on params whose mode computes its
own size.

---

## 3. What exists today (measured inventory)

- Controller: `pixel_drift.py` — 258 lines, one pygame shell, 60 fps loop, arrow keys / rotary
  encoder to switch, `--play N`, `--auto N`, `--config FILE`, `--windowed`.
- `core/manager.py` — `ModeManager` owns the display, does the fade, and `_activate_now(index)`
  **exits the old mode, re-reads config from an in-memory dict, and constructs the new one**.
  This is why live tuning needs no new lifecycle machinery.
- `core/config.py` + `core/loader.py` — three-layer merge, per-mode:
  `registry type_config` → `modes_config.json` (or profile) instance → `modes_config.local.json`
  (gitignored per-host override). `load_project_config()` is the single entry point.
- Scale: 53 mode modules / 53 registry types, ~25.7k LOC in `modes/` + `core/`, 34 instances in
  the root profile, 8 config files (root + 7 in `configs/`).
- Profiles are **not** the same set of modes: `modes_config_landscape.json` has 9 instances
  (modes 1-4, 7-11), `modes_config.basic.json` has 20 (0-4, 13-19), portrait/jetson/windows
  have 14-25 with overlapping numbers. Mode numbers are **slot numbers within a profile**, not
  global identities — so the panel's unit of work is *(profile, mode number)*.
- No param type metadata exists anywhere. `modes_registry.json` gives `required`, `optional`,
  `entrypoint`, and (for 2 types only) `type_config`.
- Several modes already auto-adapt to orientation at runtime (`self._is_portrait = h > w` in
  `status_ticker_mode.py`, `system_information_mode.py`, `mission_control_console_mode.py`), and
  some derive sizes from screen width rather than from config (ticker computes its font size from
  `self.w`). So for those modes a config value is a *hint*, not the rendered truth. The panel
  should show the configured value and label these as derived — Phase 5 makes them real params.

---

## 4. Recommendation: new project `pixel_dreams`, seeded as a fork of pixel_drift

**Recommended:** create `pixel_dreams` as a **new project forked from pixel_drift** (git clone so
the mode-authoring history comes along, then detach it as its own repo), and treat pixel_drift as
the **frozen fallback kiosk app**. All future mode work happens in pixel_dreams.

Why a fork rather than extending pixel_drift in place:

- A live-write path over a running display's configs plus a web server is a real risk surface. Put
  it where a bug cannot corrupt the app you rely on today.
- The core changes needed are **small and additive** (an `enabled` flag honoured at selection time,
  a playlist that takes an allowed-index set, a reload path, a param-schema block). Copying is
  cheap; there is no big rewrite to justify staying.
- Adding NiceGUI/fastapi/uvicorn to the kiosk app is a dependency decision you may want to reverse.
  A separate repo makes "go back to the lean app" a checkout, not a revert.
- Divergence is safe because there is only **one live codebase**: new modes go in pixel_dreams. A
  mode you want in pixel_drift is a manual cherry-pick — acceptable, and it is the honest cost of
  the split. (If you would rather keep a single tree, say so and I will design the panel as an
  opt-in module inside pixel_drift instead; the rest of this doc is unchanged either way.) Confirmed
  at review (2026-10-15): fork it.

**Rejected — extend pixel_drift in place:** mixes a live experiment into a working kiosk, and the
panel would end up editing the same versioned files the kiosk boots from.

**Rejected — pixel_dreams imports pixel_drift across `sys.path`:** the two trees get coupled while
still diverging, because the fork-specific changes (enabled flag, playlist, reload, param schema)
have to be edited anyway. The kiosk would then break whenever pixel_drift's working tree changes.
Worst of both.

Implementation note: `/mnt/ssd/projects/pixel_dreams` already exists and holds only the `.venv` I
created for the spike. Fork with:

```bash
cd /mnt/ssd/projects
mv pixel_dreams/.venv /tmp/pdvenv && rmdir pixel_dreams
git clone pixel_drift pixel_dreams && mv /tmp/pdvenv pixel_dreams/.venv
cd pixel_dreams && git remote remove origin
```

---

## 5. Architecture

One process. The panel is a thread inside it; the render loop is the only thing that touches
pygame, and the only way in is a command queue it drains once per frame. (MEASURED: D1-D3.)

```
   ┌──────────────────────────── pixel_dreams process ────────────────────────────┐
   │                                                                              │
   │  MAIN THREAD (60 fps, owns pygame)          PANEL THREAD (uvicorn + NiceGUI)  │
   │  ┌───────────────────────────────┐          ┌──────────────────────────────┐ │
   │  │ pixel_dreams.py loop          │          │ http://<host>:8090/          │ │
   │  │  - events (keys/rotary)       │          │  profile dropdown            │ │
   │  │  - ModeManager.update/render  │          │  mode list + enable toggles  │ │
   │  │  - drain ControlBus  ◄────────┼──────────┼── post(cmd)                  │ │
   │  └───────────────┬───────────────┘   queue  └───────────┬──────────────────┘ │
   │                  │                                      │ disk I/O only here │
   │                  ▼                                      ▼                    │
   │   ModeManager (registry, modes_config in memory)   ConfigStore (read/write)   │
   │                  │                                      │                    │
   │            modes/*.py (unchanged contract)              ▼                    │
   │                                              configs/*.json  (atomic writes) │
   └──────────────────────────────────────────────────────────────────────────────┘
```

Rules this buys us (each one is a bug class avoided):

- **The render thread never does disk I/O.** The panel parses config files and hands over finished
  dicts; the loop only swaps references. D3 is the evidence that this matters.
- **One writer.** The panel is the only thing that writes profile JSON; the app is the only reader.
  No lock files, no lost updates.
- **No cross-thread UI calls.** The panel never touches pygame objects. It posts commands and
  polls the bus snapshot on a `ui.timer` for its status display.
- **Bounded drain.** At most N commands per frame, so a burst can't stall a frame.
- **Opt-in.** `--panel-port 8090` enables it; importing NiceGUI is lazy, so the kiosk runs without
  the panel (and without the dependency) if you ever want that. `--panel-only` serves the same panel
  with no display at all — pygame is never initialised (useful for preparing a profile offline, and
  for testing Phases 2-3 with no display attached).

---

## 6. Config data model

### 6.1 `enabled` — the disable toggle

Add an optional instance key, default true:

```json
"7": { "type": "dungeon", "enabled": false, "seed": 42 }
```

Semantics — **selection, not construction**:

- `enabled` is a *rotation* concept. The loader keeps ignoring/normalising it; the playlist and the
  auto-cycle skip disabled slots; `--play N` still plays a disabled mode on purpose (explicit user
  intent), printing a note.
- If a profile ends up with **zero** enabled modes the app must not show a black wall: fall back to
  all modes with a loud log line, and the panel refuses to save a zero-enabled profile in the first
  place.
- Files touched: `core/config.py` (add `enabled` to `COMMON_INSTANCE_KEYS` so the validator stops
  calling it an unknown key), `core/playlist.py` (build entries from an allowed-index set instead of
  `range(max_modes)`), `pixel_dreams.py` (compute the mask, respect it in `--auto`).

Why a flag and not "just delete the mode from the profile": non-destructive and reversible in one
click, and it keeps the tuned parameters for when that orientation comes back — which is exactly the
workflow (same mode, different orientation, different settings).

### 6.2 Profile metadata (default taken at review)

Profiles currently carry no identity beyond their filename, and one of them references a Windows
path (`configs/modes_config_portrait.json` mode 1 → `G:\images\...`), which suggests they travel
between machines. Optional, ignored by core, displayed by the panel:

```json
"profile": { "label": "Portrait 1080x1920 wall", "resolution": [1080, 1920], "notes": "kitchen" },
"modes": { ... }
```

Discovery: `modes_config.json` + every `configs/*.json` (glob, so `mode_*.json` naming conventions
both work — the folder currently mixes `modes_config.basic.json` and `modes_config_portrait.json`).

### 6.3 Which profile is active

Precedence (extends the existing pattern, one new source inserted):

```
--config FILE (CLI)  >  runtime/active_profile.json  >  registry settings.modes_config_file
```

The panel's profile dropdown writes **`runtime/active_profile.json`** (small, untracked, one line)
and never rewrites `modes_registry.json`.

**Why not write `settings.modes_config_file` in the registry:** that file already has an editor —
your text editor — and it holds entrypoints and (after Phase 2) the param schemas. A second writer
that must round-trip a 26 KB versioned file to change one string is a divergence bug waiting to
happen, and it dirties git on every profile switch. One file, one editor.

### 6.4 Param schema — inference-first, metadata-optional

The mechanism you asked for ("flexible, because adding modes is easy") has to work the day you add
a mode, without you writing any UI metadata. So:

- **Inference is the baseline.** For every param, the panel picks a widget from the value's type in
  the current profile (MEASURED D5: types are consistent, so this is reliable), and from the
  registry's `required`/`optional` lists for params that are declared but absent from this profile.
- **Metadata is an upgrade**, opt-in per param, in `modes_registry.json`:

```json
"slideshow": {
  "entrypoint": "modes.slideshow_mode:SlideshowMode",
  "required": ["folder", "duration"],
  "optional": ["font_size", "overlay_font_size", "weather_units", "crypto_ids", "..."],
  "params": {
    "font_size":   { "widget": "int",  "min": 8, "max": 400, "step": 1, "label": "Clock font px" },
    "duration":    { "widget": "float", "min": 1, "max": 600, "label": "Seconds per image" },
    "weather_units": { "widget": "choice", "choices": ["imperial", "metric"] },
    "folder":      { "widget": "path", "kind": "dir" },
    "crypto_ids":  { "widget": "list", "item": "str", "label": "Coin ids" }
  }
}
```

- Widget mapping (MEASURED D6 drives this table):

| Value shape | Widget |
|---|---|
| `bool` | toggle switch |
| `int` / `float` | number field (`step` from schema, else 1 / 0.05; min/max clamp) |
| `str` | text field; `choice` if schema lists choices; `path` if schema says so |
| `list[int]` len 3, values 0-255 | colour picker + hex field (`accent_rgb`, `bg_rgb`, ...) |
| `list[float]` len 2 | min/max pair (`*_range` params, e.g. `burst_duration_range`) |
| `list[str]` | one-per-line / chip list (`crypto_ids`, `status_labels`, `waypoint_labels`) |
| `list[list[int]]` | palette editor — a list of colours (`palette` on penrose tiling) |
| `list[dict]` | **raw JSON textarea**, validated on save (`devices` on network status wall) |

- **`scripts/scaffold_param_schema.py`** (Phase 2) generates a first-draft `params` block for all 53
  types by scanning every profile's values, plus the code-drift scan, so the review is "adjust these
  numbers", not "type 279 definitions". Also fixes D7: the 6 undeclared keys get added to `optional`
  so `validate_configs.py` stops warning about them and the form shows them.
- Nothing is mandatory: a param with no metadata still renders with an inferred widget. Adding a
  mode tomorrow = add the registry entry as you already do, and its params appear.

---

## 7. Write path (crash-safety, validation, conflicts)

Every save:

1. **Validate first, refuse before writing.** Reuse `validate_configs.py`'s rules (required keys
   present, type match, unknown-key warnings surfaced to you inline) plus schema min/max. A save
   that would break a mode is blocked, in the UI, with the reason.
2. **Conflict check.** The panel remembers the hash of the file it loaded. If the file changed on
   disk since (you hand-edited it), it **refuses to overwrite** and shows both versions' differing
   keys with "keep mine / reload theirs". Never silently clobber an edit.
3. **Atomic write.** Temp sibling → `flush` + `fsync` → `os.replace` → re-read and hash-verify
   (MEASURED D4). Power loss either keeps the old config or the new one, never a fragment.
4. **Backup.** Previous version kept as `configs/.backups/<name>.<UTCstamp>.json`, last N per file,
   so a bad tuning session is one "restore" click away.
5. **Apply in memory + refresh.** The loop swaps the parsed dict and rebuilds the live mode if the
   edited mode is the one on screen.

Formatting: rewritten with `indent=2` and a trailing newline, matching the existing files. Key order
is preserved (dict order from load, new keys appended) so diffs stay small and readable.

Note on the local override layer: `modes_config.local.json` (gitignored, per-host) is merged on top
of the profile, so a param can be *shadowed* — you edit the profile, save, and nothing changes on
screen because the override still wins. The panel therefore shows an origin badge per field
(`registry default` / `profile` / `local override`) and a banner when the mode you are editing has
shadowed keys, with a one-click "clear override for this key". (Not present on this machine today —
`modes_config.local.json` does not exist here — but the example file shows the pattern is in use.)

---

## 8. Panel UI

Pages (loopback by default; reachable from a laptop on the LAN only with `--panel-bind 0.0.0.0`
plus the token — confirmed at review):

- **`/` — Modes.** Active profile at the top (with a "switch profile" dropdown and its file path),
  live status (current mode number, fps, uptime, panel clients), then the profile's mode list:
  slot number, `name`/`title`, type, an **enable toggle** per row, and a "live now" marker on the
  mode currently playing. Buttons: **Refresh current mode**, **Reload from disk**, and a per-row
  **Open** that jumps to `/mode/<n>`.
- **`/mode/<n>` — the dynamic form.** Grouped: appearance (fonts, colours, alphas) / layout /
  data (folders, files, ids). Each field shows its widget, its origin badge, and its validation
  state. Buttons: **Save & Apply** (write + refresh if this mode is live), **Save**, **Revert**
  (reload from disk), and a collapsible **raw JSON** view for the whole mode. Because profiles are
  sparse, also: **+ add optional parameter** (picks from the registry's `optional` list) and a
  per-field delete — that is how you turn on `portrait_layout` or `scale_mode` for one profile
  without hand-editing.
- **`/raw` — the profile's whole JSON**, validated on save. Escape hatch for nested structures.
- **`/logs` (optional)** — a ring buffer of the app's stdout, so you can see a mode's
  `[Mode]` errors while tuning instead of SSHing in.

Keyboard-free by design (a wall kiosk has no keyboard): every action is a button; the panel is the
only place that needs a browser, and the display keeps running whatever the panel does.

Save/Cancel/Refresh semantics, precisely:

- **Cancel** = reload the form from disk. Nothing was written (the panel stages edits client-side
  until Save — no partial writes).
- **Save** = validate → write → swap in memory. Other modes pick the change up when they are next
  switched to, because the manager builds from the in-memory config.
- **Refresh** = re-instantiate the **currently playing** mode (`exit()` → build from updated config
  → `enter()`), at a frame boundary, i.e. literally the same path as a mode switch (MEASURED from
  code: `core/manager.py::_activate_now`). There is no separate "refresh all": modes you are not
  looking at are rebuilt on switch anyway.
- Refresh cost: same as a mode switch. Worst case is bounded by a mode's own `exit()`: the slideshow
  joins a network thread with a 1.0 s timeout (`modes/slideshow_mode.py:158`), so expect a
  sub-second hitch on that one, and a re-fetch of weather/coins (that is the point, when you are
  tuning its overlay). The fade to black already covers the switch visually.
- **Profile switch** = write `runtime/active_profile.json`, re-run `load_project_config()`, rebuild
  the playlist from the new profile's enabled slots, and activate its first enabled slot. Never a
  restart. `--config` on the command line still wins over the dropdown (the UI says so, and disables
  the dropdown when a CLI override is in force, so the panel can't lie about what is playing).

---

## 9. Compatibility contract (your "compatible with the pixel drift mode interfaces")

- The mode contract is untouched: `__init__(config: dict)`, `enter(manager)`, `exit()`,
  `handle_event(event)`, `update(dt)`, `render(screen)`. Every existing pixel_drift mode drops in
  unmodified; the mode files themselves are copied, not rewritten.
- Add-a-mode workflow is unchanged (registry entry + config instance + `validate_configs.py`), and
  the panel picks the new mode up on "Reload from disk" with zero UI work.
- `validate_configs.py` stays the single source of truth for validity and grows only additively
  (schema awareness); it must still pass on all 8 profiles.
- Existing CLI flags keep working (`--play`, `--auto`, `--config`, `--input rotary`, `--gc-seconds`),
  with `--panel-port` added.

---

## 10. Phased plan

Each phase is independently verifiable, and closes by handing you a URL plus what to click
(your usual check). The riskiest integration is first.

**Phase 1 — Fork, scaffold, panel on the wire (proof of life).**
Deliverables: pixel_dreams forked with full history; `.venv` with pygame + nicegui pinned in
`requirements.txt`; lazy-imported panel thread behind `--panel-port 8090` (loopback by default);
`--panel-only` (serve the panel with no pygame display at all); read-only `/` page listing profiles
+ modes + live status; ControlBus with a bounded drain.
Acceptance: (a) `python pixel_dreams.py --auto 30 --windowed --panel-port 8090` cycles modes while
`http://127.0.0.1:8090/` lists them; (b) fps before/after enabling the panel measured and reported;
(c) RSS with the panel on/off recorded; (d) panel OFF = nicegui never imported (assert it);
(e) `--panel-only` serves the same page with no display initialised.

**Phase 2 — Param schema + read-only dynamic form.** (DONE — see §10.2 for the measured record.)
Deliverables: `params` schema support in the registry (inference fallback); the scaffold script and
its generated draft for 53 types; the 6 drift keys added to `optional`; `/mode/<n>` rendering every
param with a plausible widget (no writes). Acceptance: automated check that **every** param present
in every profile renders (count matched, 100%), plus the drift keys now visible; you eyeball a
handful of real modes (slideshow, status ticker, control panel) and say the widgets are sane.

**Phase 3 — Editing, saving, toggles, refresh (the headline feature).**
Deliverables: staged edits + Save/Cancel; validation-before-write; conflict detection; atomic write
+ backups; `enabled` toggle end-to-end (config → playlist → auto-cycle); Refresh current mode;
+add/remove optional param; the "derived at runtime" tag on params whose mode computes its own value.
Acceptance, verified in a browser with the app running: change
`font_size` in the portrait profile → **Save & Apply** → the number on screen changes with no app
restart; disable a mode → it is skipped by `--auto` (and `--play N` still plays it); corrupt config
is refused with a reason; kill -9 the app mid-save and the file is still valid JSON.

**Phase 4 — Live profile switching + polish.** (LAN access and token auth moved into Phase 1
because `--panel-bind` shipped there; this phase keeps the service packaging and the rest.)
Deliverables: `runtime/active_profile.json` + precedence + live reload of a different profile;
`/raw`; optional `/logs`; "restore backup" action; packaging as a user service alongside the
existing kiosk setup. (Token auth and `--panel-bind` already shipped in Phase 1.)
Acceptance: switch from the laptop → the wall changes orientation profile, panel reports the new
file; a request without the token is rejected from a non-loopback address; documented as a systemd
user service alongside the existing kiosk setup.

**Phase 5 (optional) — parameter exposure audit.**
The panel can only tune what is a parameter. Widen the surface for trouble modes: the derived sizes
(ticker font from `self.w`), the hardcoded colours/alphas, and the params that currently exist only
in code. Output: a candidate list with a recommendation each, reviewed before anything changes.
This is where "adjust the appearance until it looks best" gets *fully* unlocked, and it is
deliberately separate from the panel work.

---

### 10.1 Phase 1 — implementation record (DONE, 2026-10-15)

Fork revision: `e0b0e16` → pixel_dreams commits `eabc5e3` (scaffold), `b703025` (core), `7cc2225`
(panel), plus the wiring commit. Host: Jetson/Tegra aarch64, Python 3.10.12 (venv), pygame 2.6.1,
NiceGUI 3.18.0.

| Step | Status | Measured evidence |
|---|---|---|
| 1. Fork + scaffold (entrypoint rename, deps, `.gitignore`) | DONE | history preserved; 141/141 inherited tests pass on the renamed tree |
| 2. `core/profiles.py` + `core/bus.py` | DONE | 38/38 new tests, incl. a 500-command real-thread handoff with no loss or duplication |
| 3. `panel/` (read-only page, token gate, status/ping endpoints) | DONE | 14/14 in-process UI tests; page renders real mode names |
| 4. Controller wiring (`--panel-port/--panel-bind/--panel-only/--frames`) | DONE | 8/8 process-level tests; full suite **200 passed** |

Measured acceptance numbers (same run shape, `--auto 4 --windowed --input none --frames 1500`,
25s each, headless SDL dummy driver):

| Metric | Panel OFF | Panel ON | Delta |
|---|---|---|---|
| frames / wall time | 1500 / 25.31s | 1500 / 25.50s | — |
| average fps | 59.3 | 58.8 | **−0.8%** |
| peak RSS | 41.3 MB | 87.1 MB | **+45.8 MB** |
| `nicegui` imported | no | yes | — |

Live behaviour confirmed on the running app: `/api/status` reported mode 1 `StatusTickerMode` then
transitioned 1 → 2 → 3 on the 4s auto-cycle; `/api/ping` moved `pong_count` 0 → 1 and
`commands_applied` 0 → 1 — i.e. a panel request reached the render loop. Eight profiles listed,
exactly one flagged active (`modes_config.json`, chosen via `registry`). RSS of +46 MB is the
number to watch on a Pi Zero-class host; the panel is opt-in and lazily imported, so it costs
nothing when off.

**Deviations from this doc, with reasons** (folded in above where they affect a decision):

1. **Token gate + `--panel-bind` shipped in Phase 1** (doc said Phase 4). `--panel-bind` exists as
   soon as the panel does, so shipping it unguarded for three phases was not acceptable. The gate
   is an HTTP **middleware**, not just a page check: a page-level guard still answers HTTP 200 with
   a refusal page, which reads as "served" to a script and to anyone auditing exposure. Found by
   the wiring test asserting 403 and getting 200.
2. **`--frames N` added** (not in the doc): a bounded-run flag is what makes the fps/RSS/import
   claims above verifiable, and it is what `tests/test_panel_wiring.py` uses.
3. **`/api/status` and `/api/ping` added** (not in the doc): gated, machine-readable views used by
   the acceptance runs. `/api/ping` posts the same command as the page button, which is how the
   panel→loop direction was proven against the real process.
4. **`?profile=<rel>` added**: the inspected profile is chosen by URL. NiceGUI 3.18's select cannot
   have its change event driven from the test harness (its handler reads front-end props), and a
   URL-chosen view exercises the same rendering path while being bookmarkable.
5. **Status labels are mutated in place; only the mode list rebuilds** — and only on a user action.
   A 1s page rebuild would delete anything a client is using and re-request content.
6. **`secrets.json` was not actually gitignored** in the inherited `.gitignore` (AGENTS.md claimed
   it was). Fixed here and recorded in AGENTS.md. Worth checking on the kiosk's copy of pixel_drift,
   since a real key file would otherwise be committable.
7. `modes/` is byte-identical to pixel_drift, so a few mode-file comments still say "pixel_drift".
   Deliberate: it keeps the two trees diffable.

Environment note (not a defect): the inherited profiles point at the kiosk's paths, so on this
machine `modes_config.json` modes 2 and 3 log
`[SlideshowMode] folder does not exist: /home/ubuntu/narrow_slideshow/...` and render nothing. That
is exactly the per-host case `modes_config.local.json` exists for, and the panel already badges
override-supplied values.

---

### 10.2 Phase 2 — implementation record (DONE, 2026-10-15)

Commits: `236ea29` (schema layer, crash-safe writes, drift fix), `9a1271b` (the generated form).
Same host and versions as Phase 1.

| Step | Status | Measured evidence |
|---|---|---|
| 1. `core/params.py` (inference + schema overlay) | DONE | 11 value shapes mapped; absent-key typing by whole-token name heuristics; secrets masked |
| 2. `core/store.py` (crash-safe writes) | DONE | backup → temp + fsync → `os.replace` → dir fsync → re-read/hash; a failed swap leaves the original byte-identical with no temp file |
| 3. `scripts/scaffold_param_schema.py` + registry merge | DONE | 53 types analysed, 580 schema entries applied, idempotent (2nd run: 0 merged, same sha256), structure verified against HEAD |
| 4. Drift fix (code-read keys declared) | DONE | 23 keys added to `optional` across 6 types; measured drift is now **0** |
| 5. `/mode/<n>` generated form (read-only) | DONE | 16 UI tests; every field read-only; secret values absent from the element tree |
| 6. Exhaustive completeness sweep | DONE | **8 profiles, 167 modes, 2508 fields, 0 missing** |

Widget mix over the real tree (what the form actually produces): number 1271, text 608, colour
256, switch 225, string list 68, range 36, path 30, palette 6, JSON 3, choice 3, secret 2.
Per profile: root 34 modes/500 fields, portrait 24/359, narrow_vert 24/354, windows 25/376,
narrow_horz 17/256, jetson 14/204, landscape 9/130, basic 20/329.

What the code-mining found and recorded (this is the part the panel could never have inferred):
577 code defaults, 81 widget corrections, 17 keys a mode computes at runtime ("derived", e.g.
status ticker's font size), 12 suggestion sets, 1 closed value set. Schema coverage: 52 of 53
types (the 53rd genuinely has no tunable keys).

**Deviations from this doc, with reasons:**

1. **`core/store.py` shipped in Phase 2**, not Phase 3. §7 assigns the write path to the profile
   editor, but the schema tool rewrites a 26 KB versioned registry file — doing that without the
   atomic-write contract would have been careless, and Phase 3 now inherits it.
2. **`choices` vs `suggestions`** (not in the doc). Code evidence comes in two strengths: a
   declared `VALID_*` set is CLOSED (safe as a dropdown); bare `==` comparisons are open-ended, so
   they become suggestions on a free-text field. The first draft emitted a one-option dropdown for
   `weather_units` ("imperial"), which would have trapped you in Phase 3.
3. **A secret's value never enters the model** (`resolve_params` masks it). The doc only required
   the UI not to show it; masking at the model layer means no future renderer can leak one.
4. **The schema records only what inference gets wrong.** Re-emitting all 409 keys would freeze
   today's inference into the registry, so a later improvement in `core/params.py` could never take
   effect. `--all-keys` exists if you ever want the explicit form.
5. **`--check` semantics changed**: it now checks schema *health* (every type has at least one
   entry) rather than demanding an entry for every type, because one type has no tunable keys.
6. **`default` values from code are fallbacks, not your tuned values.** They differ: status
   ticker's `pause` default is 0.35 while your profile sets 3.5. The form always shows the
   profile's value when the profile sets the key; the default only appears for unset keys.

Environment note: the form's path widget reports "not found on this machine" for the inherited
kiosk paths (e.g. `/home/ubuntu/narrow_slideshow/...`). That is the per-host case
`modes_config.local.json` exists for, now visible at a glance instead of as a log line.


---

### 10.3 Phase 3 — implementation record (DONE, 2026-10-15)

**What shipped.** Editing works while the kiosk runs: the generated fields are editors, Save &
Apply writes the file and tells the running app to reload and rebuild the mode, the enable switch
takes a mode out of the rotation immediately, and Refresh rebuilds the mode on screen from the
config in memory. Nothing needed a restart at any point.

**The write model is one tested module, not button handlers** (`core/editor.py`). It stages,
validates the whole profile, refuses what it can prove wrong, detects a file that moved underneath
it, and writes atomically with a backup. Three properties are worth naming because they are the
difference between a useful panel and a dangerous one:

- *Staging is free.* Nothing touches the disk before Save; Revert costs nothing; a Save with
  nothing staged does not rewrite the file or leave a backup.
- *Validation judges the schema, not the value just typed.* Field checks resolve their widget,
  type, range and allowed set from the schema and the file's CURRENT value. Inferring them from the
  staged value would make everything valid by construction — stage a number into a text field and
  the field would define itself as numeric. A test pins this.
- *A stale file is refused, not overwritten.* The page says what changed on disk and Save stays
  blocked until Reload. Two tabs, or an ssh edit, cannot be silently clobbered.

**Validation is shared, not duplicated** (`core/validation.py`). `validate_configs.py` keeps the
CLI and the report format and delegates every rule to the same module the panel uses. A test fails
if the check messages ever get copied back into the CLI, because two implementations would drift
and the panel is the one that can wreck a config at 2am.

**The `enabled` flag, end to end.** The rotation honours it from the first frame (so disabling
survives a restart), an apply rebuilds the rotation from the new enabled set while keeping its
place, and `--play N` still plays a disabled mode when asked for by name. The status reports the
PROFILE's answer and the ROTATION's answer separately: when every mode is disabled the fallback
plays them all to avoid a blank wall, and `enabled_fell_back` says so rather than letting the panel
claim the flag was respected.

**How "it applied" is answerable.** The controller records a digest of the config it BUILT the
current mode from (`mode_config_digest`) and publishes it. Comparing it with the file's hash says
whether the wall is running the edit; without it, "it should have picked it up" is all anyone could
say. The mode page compares the two and tells you when the wall is showing an older version.

**Decisions taken during implementation** (§12 Q7-Q11): the enable switch acts immediately; absent
keys are edited in place rather than through a separate "add a parameter" picker; `POST /api/apply`
and `/api/refresh` exist as the scripted form of Save & Apply; a refresh requested mid-fade is
queued rather than dropped; a mode that exists only in the local override is shown read-only with
the reason instead of being edited into the profile.

**Numbers.** 407 tests (was 397 at the end of Phase 2). `validate_configs.py --all`: 0 errors, the
same single pre-existing warning. The 2508 form fields across 167 modes are unchanged by this
phase; what changed is that they are editable. Live verification: a parameter edit reached a
running kiosk and changed what the live mode was built from, a disabled mode left the rotation and
was never shown by it, and disabling everything kept the wall alive with a warning in the log.


---

### 10.4 Phase 4 — implementation record (DONE, 2026-10-15)

**What shipped.** The profile loop closes: the panel can make a different profile active, live, and
the choice survives a restart. Plus the two safety nets a config-writing panel deserves — restore a
backup, and edit the raw file — and service packaging.

**One resolution, obeyed by everyone.** `resolve_active_profile` lives in `core/config.py` next to
the loader that must obey it, and `load_project_config` now calls it instead of reading the
registry's `settings.modes_config_file` directly. Before this the panel *reported* the active
profile through one path while the app *loaded* its config through another, and they agreed by
luck: a switch that changed the report but not the loaded config would have been worse than no
switch. `core/profiles.resolve_active_profile` is now a delegate.

**The record is derived state, so it can never break a boot.** A missing `runtime/active_profile.json`
is normal; malformed content reads as empty; a recorded profile that has since been deleted falls
through to the registry. The panel writes only this file — never the registry, which has an editor
already and holds the entrypoints and schemas.

**Refusals, because a switch changes what is on the wall:**
- a profile that does not validate is not made active (same rule as writing);
- an app started with `--config` cannot be switched from the panel, because that flag outranks the
  record at every restart and the switch would silently vanish on reboot;
- a missing or non-profile file is refused with a 404 rather than a traceback.

**Restoring a backup validates before it overwrites** (a backup may predate a type change) and then
writes through the atomic path, which backs the current file up first — so a restore is itself
undoable. The UI asks twice, because a restore replaces a live config and one mis-click next to a
list of timestamps is not a good way to make that decision.

**`/raw` is a view of the same write path, not a second one.** Whole-document staging
(`ProfileEditor.stage_document`) goes through the same validation, atomic write, backup and conflict
refusal as the generated form; it exists for restructuring and for what the form cannot express.
It supersedes per-mode staging on purpose: half-editing a file two ways means nobody can say what
is being saved. The mode page's JSON box stays read-only (the `/raw` page covers that need, and a
per-mode box would be a second path to the same staging).

**Packaging** (`deploy/`): two example user units matching the host's existing style — the kiosk with
the embedded panel, and `--panel-only` for tuning with no display — plus the install/log/token notes.
`systemd-analyze --user verify` passes on both; neither is installed or enabled.

**Numbers.** 444 tests (was 410). Live verification: a switch moved the running app from landscape
to portrait (its rotation, its mode's build digest and its applied file all changed, no restart),
the record survived a fresh process, and switching back restored the previous state.


---

### 10.5 Phase 5 — parameter exposure audit (DONE, 2026-10-15 — awaiting your review)

**What shipped.** An analyser (`core/param_audit.py`, CLI `scripts/audit_params.py`) and the report
it produced (`designs/PHASE_05_PARAMETER_AUDIT.md`). **No mode, registry entry or profile was
changed**: the design says the candidate list is "reviewed before anything changes", and that review
is the user's.

**The rules are the deliverable as much as the list.** Three exclusions keep it trustworthy, and each
one is pinned by a test:
- a literal the mode itself overwrites (`self.margin_x = 20` then `int(self.w * 0.06)`) is a
  PLACEHOLDER, not a knob — reporting it would send the reviewer to change a number with no effect;
- a value already fed from config is not a knob (that would be two controls for one behaviour), and
  neither is a value derived from another attribute (`1.0 / max(0.1, self.refresh_hz)`);
- a one-off coordinate is not a knob, and neither is `0/1/2/-1/0.0/1.0` (indexes, flags, state
  initialisers).

**What it found** (measured, and every number in the document is generated output): 53 modules, 487
raw values, **193 distinct knobs in the 39 modes a profile uses**. The dominant finding is a repeated
idiom rather than a scatter of magic numbers — **29 modes compute their padding as
`int(min(w, h) * X)`**, and the same shape recurs for font sizes — which is exactly the
orientation-sensitive surface this project exists to tune.

**Two false-positive classes were caught by verifying the draft against the tool's own output**: a
"fifteen modes" claim that was really twenty-nine, and a "four timing knobs" claim whose every
example was a state initialiser (`self._fade_t = 0.0`). The second became a code fix (skip
`0.0`/`1.0`) and removed 243 junk candidates. Writing the narrative before checking it against the
generated numbers is how audit documents end up quoting things that are not true.

**Recommendation put to the user**: per-mode params (`pad_scale`, `font_scale`, colour knobs with
one consistent name) rather than a profile-level scale factor, which would be a design change needing
its own review — with the runner-up recorded so the choice is visible.

**Open**: the review itself. Nothing in the exposure plan is scheduled until the user says so.

**A leftover from the previous phase's live check surfaced here.** The first full-suite run of this
phase failed two REAL-TREE tests: `runtime/active_profile.json` was present, pointing at the portrait
profile, so `resolve_active_profile` returned `runtime` where `tests/test_profiles.py` only expected
`registry`/`default`. Two things were wrong and both are now fixed:
- the record was removed again (the tree is back to the root profile via registry, which is how it
  was before Phase 4's live check);
- the test itself was out of date — `runtime` is a legitimate source since Phase 4, and that assertion
  would have failed the first time the user switched a profile for real.
The mechanism by which the record survived Phase 4's own cleanup is NOT explained (the script printed
and verified the removal, the post-commit check saw the directory absent, and the log that might have
shown a second write was overwritten by the script's next step), and this record says so rather than
guessing. What matters: the suite caught it, which is the point of the real-tree tests.

**Numbers.** 462 tests (was 444).


---

### 10.6 Addition after the phases — Next / Prev mode (DONE, 2026-10-15)

Asked for after Phase 5, and outside its scope: the request was to drive the rotation by hand rather
than relying on `--auto`.

- **Under Display status** on `/`: `◀ Prev` and `Next ▶`, one press per mode, with a hint line
  saying where we are and what is either side. The hint and the enabled state are updated by the
  existing status poll, in place — the buttons are never rebuilt under the cursor.
- **It is the keyboard path, not a second implementation.** The loop publishes its step handler as
  `step_mode`, which does exactly what a LEFT/RIGHT key press does: advance the playlist, request the
  switch, reset the mode timer. Every consequence of the keyboard behaviour is therefore inherited
  rather than re-derived — most importantly that **a press during a fade is queued, not dropped**, so
  a burst of clicks all land. The queued application now also republishes `pending_steps`, so the
  panel can show `N step(s) queued (mid-fade)` instead of looking stuck.
- **A manual step restarts the `--auto` interval**, so the mode you chose gets a full interval. This
  was written as a claim in the docs and then MEASURED, because it is the kind of claim that is easy
  to assert and wrong: with `--auto 6` and a step taken 3s into an interval, the next automatic change
  came ~6s later (an un-reset timer would have fired at ~3s). The first version of that test "passed"
  by measuring the switch completing, not the timer — the assertion is now on the gap.
- **Two cases disable the buttons and say why**: `--play N` (one mode, no rotation to step through —
  the loop refuses the command too, and says so in `last_step`, so the panel is not the only guard)
  and `--panel-only` (no display to step). Two new status fields make that knowable: `single_mode`
  (published from the first frame) and `pending_steps`.
- **`POST /api/step`** for scripts, token-gated like the rest. It reports `{"ok": true, "queued": 1}`
  and deliberately NOT the resulting mode: the loop applies the step on its next frame, so any
  `mode_index` read at request time is the position before the step — a number a script would act on
  wrongly. 400 for a delta that is not ±1, 409 for a locked app.
- **Verified**: 10 new process-level and in-process tests (`tests/test_transport.py`) — including the
  burst, the wrap in both directions, the auto-timer gap, the refusal, and the gate — plus a live run
  against the real 34-mode rotation over the LAN (next, next, prev, and a double-press that queued and
  wrapped 0→33). Left no trace, and this time the full suite ran AFTER the live check as an
  independent gate.
- **Not done, deliberately**: it does not pause the rotation, and it does not add a "jump to mode N"
  box. Both are easy to add on this plumbing; the request was two buttons.


### 10.7 Addition after the phases — New config (DONE, 2026-10-15)

Asked for next: "create a new config file with all known modes and add it to the drop down list".

- **`New config…` on the profile card**, dialog with a name, a seed tick box (default on) and a
  switch tick box (default off). The file lands in `configs/`, appears in the dropdown immediately,
  and the dialog stays open showing the full report.
- **What goes in it, and the reasoning is the deliverable as much as the code:**
  * a mode the active profile already configures is copied VERBATIM (tuned values, its own `type`
    spelling, its `enabled` state) — so a new orientation starts from work already done, which is the
    whole point of seeding it from what you are looking at;
  * a mode it does not mention gets its REQUIRED keys from the schema's recorded defaults and nothing
    else — an unset key is a key the mode itself decides, and the panel already shows those as "not
    set in this profile";
  * a required key that is EMPTY is written (the key must exist for the profile to validate) and
    reported as needing a value;
  * a required key with NO recorded default means the whole type is left out and NAMED. Guessing a
    value from the key's name is what the parameter layer refuses to do, and a fabricated value would
    look configured while doing nothing.
- **On the real registry**: 53 types → 49 modes written (20 carried over from the active profile, 29
  at registry defaults), 3 values needing a value, 4 types left out (`headlinesnews`,
  `animatedcityrain`, `chatreplay`, `antfarm` — required keys with no default). Validation: 0 errors,
  0 warnings. Every registry type is therefore either in the file or explained, which is asserted.
- **A create never overwrites**: an existing name is refused with the reason and nothing written —
  there is no backup to fall back on for a file that did not exist a second ago. Names are restricted
  (`[A-Za-z0-9._-]`, no separators, no leading dot, ≤100 chars) and REFUSED rather than sanitised, so
  the file is always where the typed name says; a resolved path that is not directly inside `configs/`
  is rejected as defence in depth.
- **`POST /api/profile/new`** for scripts; 409 with the reason on refusal, and the success body is the
  report (`carried_over`, `at_registry_defaults`, `needs_a_value`, `left_out`), not just `ok`.
- **A bug found by writing the tests, worth recording**: three shapes of "registry" meet at this
  boundary — the file on disk is `{"settings", "types"}`, the panel's `_load_registry` hands out the
  `types` MAPPING, and `validate_profile`/`switch_profile` want the mapping. Taking the wrong one is
  not loud: it reports every type as "unknown", or finds no types at all. Normalised in ONE place
  (`_type_specs`) instead of remembered per call site, and pinned by a test that both shapes give
  identical output.
- **Verified**: 32 tests (`tests/test_new_config.py`) — the generator rules on a synthetic registry,
  unsafe names, the overwrite refusal, determinism, document-vs-mapping equality, the refusal path
  when `--config` pins the app (file created, switch refused, and it says so), the distinct real-tree
  test, three page-level clicks, and one process-level run that creates over HTTP, switches, and makes
  the app PLAY the generated profile — "the file exists" would not have caught a mode the app cannot
  build. Plus a live run against the real registry over the LAN (49 modes, listed in
  `/api/profiles`, duplicate refused, wall untouched), whose probe file was removed afterwards.
  Suite: 504 passed.


### 10.8 Addition after the phases — Duplicate a mode (DONE, 2026-10-15)

Asked for next: "a Duplication button on each mode line that would duplicate the mode and add it to the
config. that way i can have variations of the mode with different parameters."

- **`duplicate` on every mode row.** It copies the mode into the next free slot and writes the profile;
  the copy then has its own params page, which is the whole point — variations of one mode.
- **The copy is verbatim**, including whether it is enabled, with one deliberate exception: the name
  becomes `<name> copy` (` copy 2`, ` copy 3` when taken). Two identical labels in a thirty-row list is
  a trap; a mode with no name is left unnamed rather than given an invented one.
- **It is a SAVE, not a special case.** The new slot rides through `prospective()` into the ordinary
  `save()`: same validation, same conflict refusal, same atomic write with a backup. Written
  immediately rather than staged because a pending copy would be a mode you cannot open yet.
- **New guard, for a real hazard**: a pending copy is a slot number chosen when it was made, and the
  file can gain that slot before the save lands (another tab, a hand edit, a reload). Without a check
  it would silently REPLACE that mode instead of adding one, so `save()` refuses and says which slot.
- **In the rotation only if its source was**: an enabled source means the copy plays immediately (twice,
  until you change it — the message says so), and a disabled source gives a disabled copy. Applied to
  the running display when the profile being changed is the one on the screen; a PREVIEW-ed profile is
  written without touching the wall.
- **`POST /api/duplicate`** — `{"index": 3}` plus optional `"profile"` — returns the new slot, the name
  given, whether it is enabled and whether it was applied. 400 for a junk index, 409 for a mode that is
  not in the profile or a refusal, nothing written in either case.
- **Verified**: 17 tests (`tests/test_duplicate.py`). The one that matters is
  `test_editing_the_copy_leaves_the_original_untouched`: duplicate, change the copy, save, then compare
  the ORIGINAL's entry with what it was — that is what makes "variations" true rather than hopeful.
  Also: next-free-slot with gaps, uniqueness of the generated names, a disabled source, the
  appeared-on-disk refusal, the raw-document refusal, a real `slideshow` type through the real registry,
  the row buttons, the preview case, and two process-level runs (the copy joins the rotation; a
  disabled copy does not; junk and absent modes raise 400/409 and write nothing).
- **Harness bug found and fixed**: the UI tests' `_click` helper iterated an element's listener dict
  live, and a handler that rebuilds the page (as duplicate does) mutates it — so the fix is a snapshot
  of the listeners. The failure looked like an app bug and was not one.
- Suite: 521 passed.


### 10.9 A mode bug the panel exposed (DONE, 2026-10-15)

Not a feature and not part of any phase: found by stepping through the real rotation with the new
Next/Prev buttons on a live instance. `modes/blinkenlights_mode.py` reads `self.status_states` in
`update()` while the attribute it sets (and uses everywhere else, lines 75/137/299) is
`self._status_states` — so that mode raised an AttributeError on EVERY frame, which the manager's
per-mode handler swallows into the log, leaving the mode effectively frozen while the file floods with
`[Mode] update() error: 'BlinkenlightsPanelMode' object has no attribute 'status_states'`.

Fixed by using the name that exists, and verified by driving the mode headlessly — `enter()`, 180
frames of `update()` + `render()`, `exit()` — with no exception. It is the kind of bug that only shows
up when someone actually plays every mode, which is exactly what the manual controls are for.


## 10.10 Phase 6A — the live alignment mechanism (DONE 2/3, 2026-10-16)

Approved at review with the answers: freeform layouts **plus** a way to start a new freeform layout
over a supplied PNG (Q1), `set_rect` hook (Q2), marker + freeze on the wall (Q3), a dedicated
`/layout` page (Q4), explicit Save (Q5).

Landed so far:

* **`Control.set_rect(rect)` + `_recompute_geometry()`** in the controlpanel package, with `__init__`
  calling the same hook so "geometry from the rect" has one code path. Seven classes moved their
  cached centre/pivot/radius into the hook; classes that draw through `_window()` needed nothing
  because `_window()` now remembers its default and the base hook recomputes it; TapeReelControl
  rebuilds its reel centres while deliberately leaving the angles alone. Found and fixed on the way:
  `KeypadControl` cached `entry_rect`/`grid_origin`/`grid_size` — the contract test caught that one,
  after a code review had already missed six similar cases.
* **Measured, both ways**: assigning `control.rect` moved 0/25 testable controls; `set_rect()` moves
  25/25. One-control rebuilds also move (57-116 µs against a 16000 µs frame) but a fresh
  lamp/readout/scope draws nothing until updated, which is why the hook won.
* **The mode's edit API**: `edit_rect` (with explicit refusals for an unknown index and for a
  static-only type, which has no animated overlay in a freeform layout), `select`, `freeze` (skip
  `update()`, because dt=0 does not hold every animation still), `marker_rects()`, `layout_report()`.
  The marker is drawn by the compositor in DESIGN space before the frame is scaled, so it lands
  exactly on the control whatever `scale_mode` does.
* **The bus command and the loop's handler**: `layout_edit`, applied to the mode on screen in memory
  — no disk, no rebuild, no mode switch — and refused when the mode is not a control panel or is
  showing a different layout than the command names (a nudge must never move something other than
  what the person is looking at). The outcome and the live rects are published in the status.
* **`POST /api/layout`**, the same command the page will post, so the mechanism is drivable and
  testable without a browser: 202 + the queued command, 400 for junk, 409 for "not a control panel"
  or "not the layout on screen".
* **12 tests** (`tests/test_layout_align.py`): the contract test over every catalogue class (any
  cache under ANY name is caught, by snapshotting the whole `__dict__` rather than a hand-written
  list of attribute names), the mode's edit/select/freeze/marker/report behaviour on a real layout,
  the static-only refusal on a synthetic one, and three process-level runs against a real controller
  on its own port — including the guard that a mismatched layout is refused without moving anything.
* Suite: 532 passed with one pre-existing test failing under full-suite load
  (`test_panel_apply.py::test_disabling_a_mode_takes_it_out_of_the_rotation_without_a_restart`, which
  passes 4/4 in isolation): a timing flake in a process-spawning test, not a regression — it was
  reproduced after the fact and is on the list to harden.

Remaining for 6A: nothing. Remaining for the phase (6B): the `/layout` page itself — the overlay
list, the PNG preview with clickable boxes, the nudge pad, add/remove, and Save/Reload through a new
`core/layout_edit.py` writer that validates with the package's own loader, plus the "start a new
freeform layout over a PNG of mine" flow from Q1.


### 10.11 Phase 6B — the alignment page, and the way into it (DONE, 2026-10-16)

The page the mode needed: /layout lists every overlay of a control panel's layout, shows the artwork
with a clickable box per overlay, and offers a nudge pad (1/5/10px steps, arrows, W/H, direct entry,
centre), add/remove, freeze, Save/Reload, and "new freeform layout over a PNG". Nudges edit an
in-memory DOCUMENT and post ONE bus command, so dozens of presses stay live and cost no writes;
structural changes (add/remove) write immediately and rebuild, like the enable switch and duplicate,
because a control that exists only on screen could not be tuned. Save writes through
core/layout_edit.py — the layout's only writer — validating with controlpanel.layout.layout_from_data,
the package's own loader, so the editor can never develop a second opinion about what a layout is.

Built and shipped in two steps, and the second is worth recording as a lesson in its own right: the
page existed for a while with nothing pointing at it. A page nobody can reach is not a feature. The
control panel's params page now carries an "Overlay alignment" card whose link is scoped to that mode,
and which reads the layout up front so it can say what you are about to find — the grid flavour has no
pixel positions to nudge, and an unreadable layout_file is named rather than swallowed. Both are said
before the click, because finding out after it is a poor welcome.

Three bugs came out of the tests rather than from reading the code: the page was registered with
FastAPI's app.get instead of @ui.page and so had no slot for UI at all; core/layout_edit.py imported
the controlpanel package (and through it pygame) at module level, which killed the panel thread in the
test sandboxes that copy core/ without controlpanel/ — core must not hard-require a mode package; and
the first fix for that used a module __getattr__, which does not serve bare name lookups inside the
module's own functions. The writer also refused to take basename() before validating the name, so
"../escape" is refused rather than silently renamed to "escape" — the same rule as profile names: a
file must always be where the name you typed says it is.

### 10.12 Addition after the phases — the panel's artwork is a mode parameter (DONE, 2026-10-16)

Asked for directly: "a parameter where i can set the path to the png background". The honest answer
was that it was neither a parameter nor hard-coded — it was a field in the LAYOUT file
(background_image), so changing the picture meant hand-editing layout JSON.

Now the layout names a DEFAULT and the mode overrides it with `background_image` (optional, so every
existing profile keeps validating). That direction was chosen deliberately: the artwork is what an
author changes often and per mode — one layout reused over different pictures — while the layout stays
the drawing spec that the alignment page edits and the thing that makes a panel reproducible.
Resolution follows the same rule as skin and layout_file: a bare name looks under
assets/control_panel/backgrounds/, a path with a separator (or an absolute one) is used as given,
which is how you point at artwork living anywhere on disk.

Two refusals, because a panel that quietly draws the wrong picture is worse than one that explains
itself: a missing file is named with the path you typed, and a grid layout refuses an artwork override
outright — it draws its panels from the skin and has no background image for the override to replace.
One consequence is worth the reader's attention rather than a surprise later: when a layout declares no
design_resolution its canvas is the artwork's size, so the parameter does not only change the picture,
it changes the coordinate space every overlay is measured in. The mode's layout_report now publishes
both what the profile asked for and the resolved path in use, so the page and the wall can be shown to
agree.

## 11. Risks and non-goals

Risks:

- **LAN exposure.** A panel that writes configs is a write surface; a 0.0.0.0 bind puts it on the
  network. Mitigation: loopback default, explicit `--panel-bind 0.0.0.0` plus a token from
  `secrets.json` (never in the UI), and no destructive actions in the panel (no reboot/shutdown).
  Measured in Phase 1: an unauthorised request gets a real 403 on every route, and the browser
  path (auth route → cookie → page) is covered by a test.
- **Pi memory.** NiceGUI + fastapi + uvicorn add real RSS. Mitigation: opt-in flag, lazy import,
  measured in Phase 1 so you can decide per host.
- **Invalid config reaching the kiosk.** Blast radius is contained by validate-before-write,
  atomic writes, and backups; the profile you are not editing is never touched.
- **Two configs in flight.** The panel edits *files*; the app holds a *snapshot*. If a mode's data
  file changes underneath (a quotes JSON, an image folder), only a mode switch/refresh re-reads it.
  Stated in the UI as "changes apply on Save & Apply / next switch".
- **Tuning a mode whose appearance is derived** (D7/§3): the form will show the configured value
  even where the mode computes its own. Labelled in the UI; fixed properly in Phase 5.

Non-goals: no mode rewriting, no remote kiosk administration, no multi-kiosk sync, no user accounts
(single-token only), no mode-authoring/no-code mode creation.

---

## 12. Decisions — settled at review

All six were answered on 2026-10-15. Nothing here is waiting on you.

| # | Question | Decision | Runner-up (recorded, not pursued) |
|---|---|---|---|
| Q1 | Fork or in-place | **New repo `pixel_dreams`**, forked with history; pixel_drift frozen as the fallback app | Panel as an opt-in module inside pixel_drift (one tree, but shares the kiosk's risky files) |
| Q2 | Panel reach | **Loopback default; LAN with `--panel-bind 0.0.0.0` + token in `secrets.json`** | Loopback only (safest, but then you tune on the kiosk) |
| Q3 | Sparse profiles | **The form adds and removes optional params per profile** (Phase 3) | Edit only params already present (simpler form, more hand-editing) |
| Q4 | `profile` metadata block | **Yes** — `label`/`resolution`/`notes` per profile; core ignores it, the dropdown uses it | Filenames only |
| Q5 | Derived/effective values | **Yes** — show the configured value with a "derived at runtime" tag; Phase 5 makes them real params | Skip the tagging |
| Q6 | `--panel-only` (no display) | **Yes** — moved into Phase 1, since it also makes Phases 2-3 testable without a display | Decide later |

Phase 3 raised five more, all settled during implementation:

| # | Question | Decision | Runner-up (recorded, not pursued) |
|---|---|---|---|
| Q7 | Does the disable switch stage or act? | **Acts immediately** (write + apply). A switch that silently waits for a Save button teaches the wrong thing about the config, and it is a one-key change with nothing to stage | Stage it like a parameter (uniform, but a switch that appears not to work) |
| Q8 | How do you add a parameter the profile does not set? | **Edit it in place**: absent keys are already listed and badged "not set in this profile", and editing one adds the key. `unset` removes one | A separate "add a parameter" picker (two ways to do one thing) |
| Q9 | Is there a scripted form of Save & Apply? | **Yes** — `POST /api/apply` (re-read a profile from disk and apply) and `POST /api/refresh`, token-gated, read-only on disk, same code path as the buttons | Buttons only (the apply path could then only be exercised with a browser) |
| Q10 | A refresh arriving mid-fade? | **Queued** and done at the next clean frame, and counted when it happens | Drop it (silent failure), or interrupt the fade (visible glitch) |
| Q11 | How does the panel know the change reached the wall? | **The controller publishes `mode_config_digest`** — a hash of the config the live mode was BUILT from — and the page compares it with the file | Assume it applied (unfalsifiable) |

Phase 4 raised four more:

| # | Question | Decision | Runner-up (recorded, not pursued) |
|---|---|---|---|
| Q12 | Where does the active profile live? | **`runtime/active_profile.json`**, one line, gitignored, atomic, written only by the panel. Precedence `--config > runtime > registry settings` | Write `settings.modes_config_file` in the registry (a second writer round-tripping 26 KB to change one string, dirtying git on every switch) |
| Q13 | Panel switch when `--config` was used? | **Refused, with the reason.** That flag outranks the record at every restart, so a switch would look like it worked and be gone on reboot | Allow it silently, or allow it with a warning (both leave a trap) |
| Q14 | Is restore a separate write path? | **No** — validate the backup, then write through the same atomic path, which backs up what it replaces so a restore is undoable. Two-step in the UI | Copy the file over the live one (one mis-click from an outage) |
| Q15 | Two units or one? | **Two**, in `deploy/`: the kiosk with the panel, and `--panel-only` for no-display tuning. The app needs a graphical session; the panel deliberately does not | One unit (simpler, but the panel-only case then needs a hand-run command) |

If any of these turns out wrong once you are using it, the doc is the place the reversal gets
written — not the transcript.


---

## Appendix A — Evidence

- Frozen pixel_drift revision the fork starts from: `e0b0e16`
  ("Shrink portrait cover to ~75% and make fraction configurable"), tree clean.
- Spike: `designs/arch_spike_probe.py`, run with `pixel_dreams/.venv/bin/python`, 6/6 checks PASS
  (results reproduced in §2 D1-D4).
- Drift scan: regex over `modes/*.py` for `config.get(...)`/`config[...]` keys vs registry
  `required`/`optional`/`type_config` — 6 types, keys listed in D7.
- Inventory: 53 `modes/*_mode.py`, 53 registry types, 34 instances in the root profile, 8 profile
  files, 279 distinct param keys, 0 cross-profile type conflicts, nested values in
  `devices` (network status wall) and `palette` (penrose tiling).

## Appendix B — Where the doc lives

`/mnt/ssd/projects/pixel_dreams/designs/PIXEL_DREAMS_DESIGN.md` (this file), spike alongside it.
Per-phase docs, if you want the finer granularity used in Daedalus, will land in the same folder as
`PHASE_0N_*.md`.
