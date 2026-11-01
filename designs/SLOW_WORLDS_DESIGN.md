# Slow Worlds

**Twenty gentle animated modes for pixel_dreams — design for review**

**Status:** DRAFT FOR REVIEW — the design collection. The Glass Castle (§5.13) is
implemented as `glasscastle` and Terraform (§5.15) as `terraform`; see
[`glass_castle_proto/README.md`](glass_castle_proto/README.md) and
[`terraform_proto/README.md`](terraform_proto/README.md). The other eighteen remain
design only; no mode code, registry entries or profile changes for them are included here.
Terraform's reviewed camera is the mountain-top overlook rather than the card's flat
plate.

**Target:** the Raspberry Pi kiosk (`configs/modes_config_narrow_horz.json`, 1280×400),
with the portrait wall (1080×1920) and a conventional 16:9 display as secondary targets.

**Related:** [`SPACE_STATION_DESIGN.md`](SPACE_STATION_DESIGN.md),
[`CYBERSPACE_DESIGN.md`](CYBERSPACE_DESIGN.md),
[`sunrise_proto/`](sunrise_proto/), [`PIXEL_DREAMS_DESIGN.md`](PIXEL_DREAMS_DESIGN.md).

**The proposal in one sentence.** Twenty standalone scenic modes — nine science-fiction,
six fantasy and five horror pieces (one of which is a science-fiction/horror hybrid) — each
with a distinct slow-motion engine, designed for the 1280×400 strip first, and none requiring
an external asset, a network feed, or audio.

**Review path.** Start with the table in §3 for the menu, open the cards that catch your eye
for the motion and build notes, then use §8 for the decisions that need a call before any
prototype starts.

---

## 1. The brief

The newest modes on the wall — **Sunrise**, **Space Station V**, **Cyberspace Matrix** and
**Trench Run** — share a quality that is easy to miss when listing their features: they are
places you can leave running. They move, but they do not demand attention. They are legible
from across the room, they reward a ten-second glance, and they still look composed when
nothing in particular is happening.

The request is to extend that feeling with twenty new modes in a science-fiction, fantasy or
horror register. This document is a menu, not a commitment: twenty concepts, each with a
distinct motion engine, a composition for the narrow kiosk, a palette, a parameter sketch and
a realistic build note. The intent is to review the ideas first, then choose a small first wave
to prototype.

The house style is not a single renderer. Sunrise is flat and illustrative; Space Station V is
transparent vector work; Cyberspace is neon wireframe; Trench Run is a moving line drawing.
What they have in common is restraint: a limited palette, a clear silhouette, a camera that
never hurries, and a HUD that knows when to stay out of the way. The new collection should sit
beside them without looking like a different product.

A useful visual reference for the intended bar:

- [Space Station V at 1280×400](../screenshots/space_station/hero_1280x400.png)
- [Cyberspace Matrix at 1280×400](../screenshots/narrow_horz/cyberspace_1280x400.png)
- [Trench Run at 1280×400](../screenshots/narrow_horz/trench_run_1280x400.png)
- [the four-season Sunrise study](sunrise_proto/seasons_sheet.png)

---

## 2. What "gentle" means here

Gentle is not the same as slow. A screensaver that is merely slow becomes a still image with
a blinking cursor. The modes in this collection should have a visible pulse — a breath, a
sweep, a drift, a light coming on — but the pulse should never become the subject.

The following envelope is proposed as a shared design rule. It is deliberately conservative;
individual modes may earn an exception, but the exception should be written down in the mode
card.

### 2.1 Motion envelope

| Element class | Typical | Ceiling at 1280 px wide | Notes |
|---|---:|---:|---|
| Camera drift | 0.5–2 px/s | 3 px/s | Continuous, eased, no handheld shake |
| Large subject (ship, creature, structure) | 2–8 px/s | 12 px/s | A full crossing takes 90–300 s |
| Small particle (snow, embers, motes) | 4–20 px/s | 30 px/s | Sparse, low contrast, never the focus |
| Beam or scan sweep | 1 revolution / 8–15 s | 1 revolution / 6 s | No strobe, no hard-edged flash |
| Flame or candle flicker | 1–2 Hz | 2 Hz, ≤3% of frame | Optional; horror modes can disable it |
| Full-frame luminance change | <1% per second | 3% per second | No cuts, no whip pans, no flashes |
| Notable event | 1 per 20–90 s | 1 per 10 s | One event at a time; let it finish |

At 1280 px, 12 px/s is a little under 1% of the screen width per second. A large object at
that speed takes over a minute and a half to cross the frame. That is the right order of
magnitude for this wall.

### 2.2 Composition rules

1. **A still frame is a poster.** Pause the mode at any moment and it should look intentional:
   a horizon, a subject, a light, a negative space. No mode should depend on motion to explain
   itself.
2. **One subject, two supports.** Three focal elements at most. The rest is atmosphere.
3. **The lower-left 80×32 px belongs to the controller.** The mode-number watermark is drawn
   there. Keep it darker than the subject and free of detail.
4. **HUD is a guest.** Default to `hud: "minimal"`: a title, a time, perhaps one telemetry
   line. No mode should become a dashboard. The existing console modes already cover that
   territory.
5. **The horizon is a composition tool, not a default.** Put it high for scale (Leviathan),
   low for sky (Aurora), or remove it entirely (Event Horizon, Orrery).
6. **Design for 1280×400 first.** The ultrawide frame is a strip, not a letterboxed 16:9.
   Compose in horizontal bands and avoid stacked UI. Then re-compose for 1080×1920; do not
   crop the strip.
7. **Read at three distances.** At one metre the detail should hold; at three metres the
   silhouette should hold; at ten metres the mood should hold.

### 2.3 The ten-second and five-minute tests

- **Ten seconds:** something should have changed — a breath, a beam, a ripple, a light.
- **Five minutes:** the loop should not be obvious. Use co-prime periods, seeded event
  sequences, and long cycles (90–600 s) for the major elements.
- **One hour:** returning to the mode should feel like returning to a place, not restarting a
  GIF. Modes may either continue their own clock or begin a new seed; the card says which.

### 2.4 Safety and comfort

- No strobing, no rapid cuts, no full-screen flashes. Horror is atmosphere, not assault.
- Flicker is localised (a candle, a failing sconce) and can be turned off.
- No mode depends on audio. The kiosk may have no speakers.
- No mode requires input to become interesting.
- Text is at least 12 px on the 1280×400 wall and 16 px on portrait. Titles can be larger.
- Bright highlights cover a small area; the average frame stays comfortable in a dark room.

---

## 3. The collection at a glance

Twenty modes, grouped into four families. The render column uses **W** = wireframe/line,
**F** = flat/illustrated vector, **A** = atmospheric/particle/gradient, **H** = hybrid.
Build size is relative (S/M/L), not a schedule. Wave is the recommended prototyping order.

| # | Mode | Theme | Render | Motion engine | Build | Wave |
|---:|---|---|:---:|---|:---:|:---:|
| 1 | The Orrery of Small Worlds | SF | W | Nested orbits on a brass instrument | M | 1 |
| 2 | Ringworld, Facing the Sun | SF | H | Curved landscape ribbon and moving terminator | L | 2 |
| 3 | Gravity Well | SF | W | Deforming spacetime mesh | M | 1 |
| 4 | Event Horizon | SF | A/H | Lensed accretion disk | L | 2 |
| 5 | The Slow Sail | SF | W/H | Convoy of solar sails across a nebula | M | 2 |
| 6 | Abyssal Bloom | SF | A | Bioluminescent drift and sonar | M | 1 |
| 7 | The Long Archive | SF | W | Gliding camera through floating monoliths | M | 3 |
| 8 | Aurora Relay | SF | A/F | Aurora curtains over a tracking antenna farm | M | 3 |
| 9 | The Wizard's Observatory | Fantasy | F/W | Clockwork armillary, glyph rings, candlelight | M | 2 |
| 10 | The Sleeping Dragon | Fantasy | F | Breath, embers, one opening eye | M | 2 |
| 11 | Lantern Procession | Fantasy | F | Lanterns on a spline through a forest | M | 1 |
| 12 | Runic Tide | Fantasy | F/A | Waves writing glyphs on black sand | M | 3 |
| 13 | The Glass Castle | Fantasy | H | Aurora, snow, crystal facets, slow parallax | L | 3 |
| 14 | Leviathan Passage | Fantasy | F | Silhouettes crossing a dusk horizon | M | 2 |
| 15 | Terraform | SF | F/H | Long-cycle world transformation | L | 3 |
| 16 | Descent | Horror/SF | A | First-person bathyscaphe descent | M | 2 |
| 17 | The Black Lighthouse | Horror | F/A | Sweeping beam, fog, something under the water | M | 1 |
| 18 | The Empty House | Horror | F | Cutaway rooms, candle, a door opening | M | 3 |
| 19 | The Orchard at 3 A.M. | Horror | F | Wind, fog, a figure at the treeline | S | 1 |
| 20 | The Long Corridor | Horror | W/F | One-point perspective dolly that never arrives | M | 3 |

The set deliberately mixes temperatures: six modes are bright or dawn-lit (Orrery, Ringworld,
Terraform, Leviathan, Glass Castle, Aurora Relay), while the horror modes are dark but never
empty. In a rotation, no two horror modes should run back to back.

---

## 4. Shared visual system

This section is a set of recommendations for all twenty, not a framework that must be built
first. Each mode can stand alone; the shared language is what makes them feel like a
collection.

### 4.1 Palette families

Each mode exposes a `palette` choice with two or three named variants. A palette has five
semantic roles — background, ink, structure, accent, glow — so a variant is a small table,
not a new renderer.

| Family | Background | Ink | Structure | Accent | Glow | Best for |
|---|---|---|---|---|---|---|
| **Brass & Ink** | `#0B0B0E` | `#E8DCC0` | `#C9A45C` | `#7FB7A3` | `#F2C879` | Orrery, Observatory |
| **Deep Blue & Bone** | `#03060F` | `#DCE6F2` | `#3E7CB1` | `#7FE0E8` | `#A9D8E8` | Ringworld, Archive |
| **Phosphor & Ash** | `#050A08` | `#CFE8D7` | `#6B7D72` | `#69F0AE` | `#B9FFD9` | Gravity Well, Relay |
| **Ember & Rust** | `#0C0706` | `#E9D3B4` | `#8E3B2E` | `#FF7A3C` | `#FFD08A` | Event Horizon, Dragon, Lighthouse |
| **Aurora & Ice** | `#050812` | `#E6F3F2` | `#8E7CFF` | `#58E0B8` | `#BFF7E4` | Glass Castle, Aurora, Runic Tide |
| **Moon & Moss** | `#070B08` | `#DDE6D0` | `#6F8757` | `#D9A05B` | `#E8D9A8` | Leviathan, Lanterns, Orchard |

Two rules:

- **Three saturated hues maximum.** Most scenes should read as one dominant colour with one
  accent and one warm light. A fourth hue is a special effect, not a default.
- **Near-black, not pure black.** A tinted background (`#03060F`, `#0C0706`) avoids banding,
  gives bloom something to sit on, and photographs better.

### 4.2 Finish

The house pattern is worth keeping:

1. cached background gradient;
2. far layer (stars, fog, skyline) with low contrast;
3. the subject, drawn at native resolution;
4. near particles or atmosphere;
5. one downscaled additive bloom pass;
6. one baked multiply map for vignette, scanlines and HUD bands;
7. crisp HUD text last.

The bloom is optional and should never be required for legibility. If a mode is paused with
bloom off, the drawing still has to read. Scanlines and grain are seasoning: 3–8% opacity,
not a filter that hides weak art.

### 4.3 Typography

Use the existing `manager.cache` and system fonts (`dejavusans`, `dejavusansmono`,
`dejavuserif`). No new font files are required for this collection.

- **Telemetry:** small mono, uppercase, generous letter spacing.
- **Titles:** serif or display for fantasy, mono for science fiction; one line only.
- **Lore:** one sentence, not a paragraph. The Long Archive and Runic Tide are the only modes
  where text is a primary element; both should be readable at a glance and then fade.
- **No fake UI for its own sake.** A frame around text is fine; twelve nested cards are not.

### 4.4 Time, seeds and determinism

Every mode should be a pure function of `(seed, elapsed time)`. That gives three benefits:

- pinning `seed` reproduces a scene for review and for preview frames;
- an unpinned seed makes re-entry feel like a new place;
- a mode can be paused, resized, or rebuilt without the scene jumping.

Use a stable integer mix for procedural choices, not Python's salted `hash`. Keep the
simulation independent of frame rate: accumulate time in `update(dt)`, never assume 60 fps.
Large cycles should use periods with common factors avoided where possible (e.g. 47 s, 71 s,
113 s) so the composition does not visibly repeat every few minutes.

### 4.5 Performance shape

The narrow kiosk is the constraint. The target is a comfortable 60 fps where possible and a
30 fps floor on the Pi; every mode gets an `auto` quality setting that changes detail, not
identity.

| Tier | What changes | What does not change |
|---|---|---|
| `low` | fewer particles, coarser grid, no bloom or 8× bloom, aliased far lines | composition, palette, timing |
| `medium` | full geometry, half-resolution bloom | composition, palette, timing |
| `high` | extra detail, 4× bloom, anti-aliased near lines | composition, palette, timing |

An exponential moving average of frame time, with hysteresis, is the existing pattern in
Space Station V and Cyberspace. Use it. Do not let a quality change alter the camera path or
the position of a planet; a viewer should not see the world "pop".

Draw-call budgets are approximate, but useful as a design target at 1280×400:

- **S:** under 1,000 line/segment draws, under 80 particles, no full-screen per-frame blur.
- **M:** under 2,500 draws, under 150 particles, one half-res bloom.
- **L:** under 4,000 draws, under 250 particles, one half-res bloom plus one cached layer.

If a mode needs more than that, it should cache the difference or reduce the number of
objects. The Pi is a kiosk, not a demo reel.

### 4.6 Failure behaviour

A missing optional data file, a failed font, or a malformed lore list must not stop the
kiosk. Each mode should:

- log once, with a stable prefix;
- fall back to a procedural or built-in variant;
- keep the composition and timing intact;
- never draw a traceback on the wall.

This is already the pattern in Space Station V's coastline loader and Sunrise's weather feed.
The new modes should follow it.

---

## 5. The twenty modes

Each card is a design sketch, not a specification. The positions and proportions are for the
1280×400 wall; the build notes name the parts that need the most care. The frame drawings are
schematic, not pixel-accurate.

### I. The long view

#### 5.1 The Orrery of Small Worlds

`orrery` · science fiction · render W · build M · wave 1

**Pitch.** A brass orrery of invented worlds turns in a dark observatory. Seven planets on
inclined elliptical rails, each with a moon and a name; a comet visits every few minutes; an
engraved plate gives the instrument a history it does not need to explain.

**Frame.**

```text
+------------------------------------------------------------------+
| ORRERY OF SMALL WORLDS                            INSTR. 03/09   |
|                                                                  |
|        .-~-.             .-~~~-.                 * Vela          |
|      /   o   \         /   o   \          .-~-.                  |
|     |   (S)   |-------|    .    |--------(  o  )      .-~-.      |
|      \       /         \       /          `-.-'      (  Mora )   |
|        `-.-'             `-.-'                          `-.-'     |
|   ~~~~~~~~~~~~~~~~~~  O R R E R Y  ~~~~~~~~~~~~~~~~~~~~~~~~~~     |
|   [SUN]                                                21:04     |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Worlds | Constant angular motion on inclined ellipses; no easing (mechanical) | 45–240 s per orbit |
| Moons | Small circular orbits around their world | 6–18 s |
| Comet | One long ellipse, visible for the middle of the pass | 1 pass / 90 s |
| Armature | Slow precession of the whole instrument | 300 s, ±0.5° |
| Dust | A few motes drifting through the light | 1 px/s |
| Camera | A barely perceptible drift, never a pan | 0.5 px/s |

**Signature.** When two worlds come into conjunction, a thin engraved line connects them and
a small label appears for eight seconds. It is the only time the orrery acknowledges the
viewer.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `world_count` | 7 | 5–9; more worlds make the plate crowded |
| `orbit_seconds` | 90 | Base period; each world multiplies it |
| `show_labels` | true | World names fade in on approach |
| `show_comet` | true | One comet on a long ellipse |
| `camera_drift` | 1.0 | px/s; 0 pins the view |
| `detail` | auto | Rail subdivision and moon count |
| `palette` | brass | `brass`, `verdigris`, `bone` |

**Build notes.** Project ellipses into 2D and cache their point lists; only the worlds and the
comet move. Depth-sort rails behind/in front of the sun by projected Y. Labels are cached
surfaces; fade them out when they collide. A small warm disc and a soft corona are enough for
the sun. This is one of the cheapest modes in the set and one of the most recognisable.

**Differentiation.** The existing `galacticnavigation`, `alienstarmapcartographer` and
`satellitetracker` modes are consoles that describe a sky. This is a physical instrument in a
room, with no data feed and no map. It is also not a solar system: the worlds and names are
invented.

---

#### 5.2 Ringworld, Facing the Sun

`ringworld` · science fiction · render H · build L · wave 2

**Pitch.** A view from inside a ringworld at dawn. The land and sea rise on both sides and
meet overhead; a sun hangs on the ring's axis; the terminator crawls across continents; city
lights come on in a wave as the dark reaches them.

**Frame.**

```text
+------------------------------------------------------------------+
| RINGWALL // DAY 1,204                            ALT 1,620 KM    |
|           \                                      /               |
|            \            ( sun )                 /                |
|             \__________________________________/                 |
|   ~~~~~ clouds ~~~~~   ~~~~~~~~~~~~   ~~~~~ clouds ~~~~~         |
|   ~~~ land ~~~ sea ~~~~~~~~~~~~~~~~~~~~ sea ~~~ land ~~~         |
|   ~~~ city ~~~ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ city ~~~          |
|    \__________________________________________________/          |
|      the far rim is the horizon; the near rim is overhead        |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Ring/sun phase | The ring's rotation carries the sun along the arch | 240 s |
| Terminator | A soft shadow band crosses the landscape | 120 s |
| Clouds | Two parallax layers, wrapping at the edges | 3 and 7 px/s |
| City lights | A wave of small warm points follows the terminator | 3–7 s twinkle |
| Moon transit | A small dark disc crosses the sun | Once every 60–90 s |
| Camera | A slow breath, no travel | 2 px/s |

**Signature.** The terminator reaches a coastal city and the lights ripple along the ring,
one district at a time, before the shadow moves on.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `cycle_seconds` | 240 | Full day/night phase |
| `sun_phase` | 0.18 | Where the day starts |
| `cloud_speed` | 1.0 | Multiplier on the two cloud layers |
| `city_lights` | true | The terminator wave |
| `show_moon` | true | A transit every 60–90 s |
| `palette` | dawn | `dawn`, `verdant`, `night` |
| `detail` | auto | Strip count and cloud density |

**Build notes.** This is the hardest composition in the set because it must read as a ring,
not a bowl. Build the interior as a set of horizontal strips whose vertical offset follows a
shallow arc; draw land, sea and cloud bands per strip, then a rim line at the top. The sun is a
disc on the axis with a corona. The terminator is a moving gradient wedge, not a texture. Keep
the strip count around 120 at medium; cache the static palette bands and redraw only the
terminator and clouds.

**Differentiation.** Space Station V looks at a station from outside; this looks at a world
from inside. The existing Earth/planet modes are discs; this is a curved environment with a
horizon overhead.

---

#### 5.3 Gravity Well

`gravitywell` · science fiction · render W · build M · wave 1

**Pitch.** A wireframe spacetime sheet suspended in the dark. Two or three invisible masses
orbit beneath it; their wells bend the grid; ripples travel outward; a handful of test
particles trace lazy orbits and leave faint trails.

**Frame.**

```text
+------------------------------------------------------------------+
| GRAVITY WELL // SHEET 2                            MASS 3 / 3     |
|   .   .   .   .   .   .   .   .   .   .   .   .   .   .   .     |
|     \    \    \    \    \   |   /    /    /    /    /            |
|       \    \     \    \  |  /    /    /    /    /                |
|   ------+-----+------\__|__/------+-----+------+-----             |
|         \      \    /  (o)  \    /      /                         |
|   --------+------+--|   M    |--+------+--------                  |
|           \       \  \      /  /       /                           |
|     .      \   .   \  \____/  /   .   /   .    .                  |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Masses | Slow orbits under the sheet; each drags its own well | 40–80 s |
| Ripples | Concentric waves propagate from each mass | 8 s travel |
| Test particles | Elliptical orbits with fading trails | 10–20 s |
| Camera | A few degrees of orbit around the sheet | 120 s |
| Sheet | Deformation follows the masses; no idle wobble | continuous |

**Signature.** Two wells drift close, merge into one deeper well for about ten seconds, then
separate; the whole sheet shivers and settles.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `well_count` | 2 | 1–3; three is busy but dramatic |
| `grid` | 40×24 | Point counts; quality scales this |
| `orbit_seconds` | 60 | Base orbital period |
| `ripple_strength` | 0.6 | How far the rings travel |
| `show_particles` | true | 10–20 test particles with trails |
| `camera_orbit` | 3.0 | Degrees over the full cycle |
| `palette` | blue | `blue`, `phosphor`, `mono` |

**Build notes.** A regular grid on a plane, deformed by `-mass / distance`, projected with a
fixed camera. The line index is prebuilt; only the point positions change. Color by depth and
distance. At 40×24 the sheet is about 1,800 segments, which is within the budget of the
existing wireframe modes. Avoid a full-screen bloom if frame time is tight; a subtle additive
pass on the wells is enough.

**Differentiation.** Cyberspace and Trench Run are built environments with a floor; this is an
abstract diagram where the deformation is the subject. No city, no traffic, no HUD beyond a
small legend.

---

#### 5.4 Event Horizon

`eventhorizon` · science fiction · render A/H · build L · wave 2

**Pitch.** A portrait of a black hole: a black disc, a thin photon ring, a lensed accretion
disk, a warped star field, and two faint jets. No labels, no telemetry, no explanation. The
object is the composition.

**Frame.**

```text
+------------------------------------------------------------------+
|                    .        *          .                         |
|         ______________  ____________                             |
|      .-'    ____     \/     ____    '-.        *                 |
|    .'      /    \    ||    /    \      '.                        |
|   /       |  ##  |===||===|  ##  |       \                       |
|   \       |  ##  |===||===|  ##  |       /                       |
|    '.      \____/    ||    \____/      .'                        |
|      '-.____________/  \____________.-'                          |
|              lensed disk around a black disc                     |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Accretion disk | Streaks rotate around the hole | 45 s |
| Photon ring | A 2% brightness pulse, no size change | 8 s |
| Jets | Faint vertical shimmer | 20 s |
| Infalling debris | A short stream spirals in | 1 event / 90–120 s |
| Star field | Static lens warp; slow twinkle | continuous |
| Camera | A 0.5% push and release | 90 s |

**Signature.** A star behind the hole appears twice, in two lensed arcs, and the two images
merge as the star moves. It is a quiet reminder of what the object is doing to the light.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `disk_tilt` | 18 | Degrees; low tilt reads more like a ring |
| `spin_seconds` | 45 | Disk rotation |
| `lens_strength` | 0.5 | Star-warp strength |
| `show_jets` | true | Two faint polar jets |
| `debris_chance` | 0.25 | Per cycle; 0 disables |
| `palette` | ember | `ember`, `ice`, `violet` |
| `bloom` | true | Half-res additive pass |

**Build notes.** Precompute the star field once and warp it around the center with a radial
displacement; that layer is static. The disk is a set of short additive arcs at different
radii and angles, colored from white-hot near the hole to dull orange at the rim. The photon
ring is a thin bright ellipse with a soft outer glow. The black disc is opaque and must sit
above the lensed stars but below the near-side disk. Bloom is important here; budget it at
half resolution and upscale.

**Differentiation.** Gravity Well is a diagram of deformation; Event Horizon is a cinematic
object portrait. The two are deliberately paired but should not share a renderer or a HUD.

---

#### 5.5 The Slow Sail

`sailcaravan` · science fiction · render W/H · build M · wave 2

**Pitch.** A convoy of solar sails crosses a deep indigo nebula. There are no engines and no
weapons; the ships are thin luminous kites with structural ribs and tiny gondolas. The light
comes from an off-frame sun, and the sails turn very slowly to catch it.

**Frame.**

```text
+------------------------------------------------------------------+
|  *        .        SAIL 01        .            *                  |
|        /\        .       /\             nebula                    |
|       /  \      /|      /  \        .-~~~-.                       |
|      /    \    / |     /    \      (  glow )                      |
|     /      \  /  |    /      \      `-...-'                       |
|    /   /    \/   |   /   /    \        |                          |
|   /___/______\___|__/___/______\_______|_______                   |
|    sail 01       sail 02       sail 03    sun ->                 |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Sails | Drift across the frame, holding formation | 3 px/s |
| Sail attitude | A slow yaw and roll into the light | ±2°, 40 s |
| Membranes | Ripple along the ribs | 6–9 s |
| Nebula | Two soft layers drifting | 0.2 px/s |
| Tether lights | A pulse runs along the convoy line | 20 s |
| Stars | Parallax against the sail motion | continuous |

**Signature.** The convoy crosses a dark dust lane; the sails dim to silhouettes, then relight
one by one as they reach the far side.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `sail_count` | 5 | 3–7; more becomes a fleet |
| `cruise_speed` | 3.0 | px/s; the whole convoy shares it |
| `nebula_density` | 0.5 | 0 = plain star field |
| `sun_side` | left | `left`, `right`, `behind` |
| `show_labels` | true | Small registry marks, not a HUD |
| `palette` | cream | `cream`, `rust`, `phosphor` |
| `detail` | auto | Rib count and nebula layers |

**Build notes.** The nebula is a cached, blurred cloud field, not per-frame noise. Sails are
polygons with a translucent fill and bright leading edges; the ribs are a handful of lines.
The membrane ripple is a vertex offset along the sail's short axis. Additive rim light on the
sunward edge sells the material. Keep the ships small enough that the nebula remains the
subject.

**Differentiation.** Trench Run and Cyberspace are about speed and destination. This is about
distance and patience. There is no destination on screen.

---

#### 5.6 Abyssal Bloom

`abyssalbloom` · science fiction / horror wonder · render A · build M · wave 1

**Pitch.** A deep-sea blossom: an enormous siphonophore drifting in a dark water column, its
bells pulsing in sequence, its tentacles trailing for metres. Marine snow falls. A sonar ring
sweeps out every twelve seconds. Somewhere beyond the light, an anglerfish waits.

**Frame.**

```text
+------------------------------------------------------------------+
| ABYSSAL BLOOM // 812 M                        SONAR 12 S         |
|        .   *        .          .    *        .                    |
|   .          .-~-.        .        .-~-.        .   *             |
|        *    (  o  )   .        *   (  o  )   .                    |
|   .        .-~-.-~-.       .      .-~-.-~-.       .               |
|        .-~   / | \   ~-.      .-~    |    ~-.                     |
|   *   (  bell  |  bell  )   (  bell  |  bell  )    .              |
|  ~~~~~  ~~~~~  |  ~~~~~ ~~~~~~  ~~~~~|~~~~~  ~~~~~~              |
|        .   .   *     .    .    *      .    .                     |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Siphonophore | A slow vertical pulse and a drift through the column | 7 s / 1 px/s |
| Bells | A pulse travels from the crown to the tail | 7 s |
| Tentacles | Sine-wave sway with a phase offset per strand | 11 s |
| Marine snow | Drifts downward, fading with depth | 4–8 px/s |
| Sonar | A ring expands and fades; a faint return follows | 12 s |
| Anglerfish | A silhouette at the edge of the light | 1 / 90 s |
| Camera | A barely perceptible sink | 0.5 px/s |

**Signature.** The sonar return draws a second, larger silhouette behind the visible creature
for a moment. Then the ring fades and the water is empty again.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `depth` | 812 | Readout only; also darkens the palette |
| `creature_count` | 4 | 2–6; the siphonophore is always present |
| `sonar_period` | 12 | Seconds per sweep; 0 disables |
| `glow` | 0.7 | Additive brightness of the creatures |
| `show_sonar` | true | The ring and its return |
| `palette` | abyss | `abyss`, `rose`, `bone` |
| `detail` | auto | Tentacle strands and particle count |

**Build notes.** The water column is a cached vertical gradient, darkest at the bottom. The
siphonophore is a chain of translucent ellipses along a bezier spine; the tentacles are
stroked beziers with a phase offset. Use additive blending for the bells and a small cached
glow sprite for each. Marine snow is a particle layer with a gentle horizontal drift. The
sonar ring is a stroked circle whose alpha falls as it expands; the return silhouette is the
same creature shape, scaled up and drawn at very low alpha. No external sprites or textures,
and no network.

**Differentiation.** `descent` is a first-person vehicle with a spotlight and a depth gauge;
this is an external, almost botanical view. It is not an aquarium: there is one composition,
one dominant creature, and no tank edges.

---

#### 5.7 The Long Archive

`longarchive` · science fiction · render W · build M · wave 3

**Pitch.** A deep-space vault of monoliths, each etched with the last lines of a civilization.
The camera glides past them in the dark; one slab at a time is lit by a traveling bar of
light; data motes drift between the slabs. There is no floor, no shelves, and no reader.

**Frame.**

```text
+------------------------------------------------------------------+
| THE LONG ARCHIVE // VAULT 9                     ENTRIES 1,204    |
|        .             *               .              *            |
|   +---------+   +---------+   +---------+   +---------+          |
|   |  ...    |   |  ...    |   |  ...    |   |  ...    |         |
|   |  ...    |   |  ...    |   |  ...    |   |  ...    |         |
|   +---------+   +---------+   +---------+   +---------+          |
|        .             .               .              .            |
|   "we kept the light on for whoever came next"                   |
|                  camera glides -->                               |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Camera | A slow glide past the slabs | 2 px/s |
| Slabs | Each drifts and turns a fraction of a degree | 0.3 px/s |
| Light bar | Travels across the lit slab, revealing text | 8 s per slab |
| Text | Recedes as the slab leaves the light | 14 chars/s reveal |
| Motes | Drift between the slabs | 1–3 px/s |
| Focus | One slab is bright; the rest are dim | changes every 30 s |

**Signature.** A slab's text is in an unknown script. As the light bar passes, one line
resolves into readable English, holds for a few seconds, then fades back into glyphs.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `slab_count` | 9 | 7–12; fewer reads as a monument |
| `drift_speed` | 2.0 | Camera glide |
| `text_speed` | 14 | Characters per second on the lit slab |
| `text_file` | unset | Optional JSON list; built-in lore otherwise |
| `show_labels` | true | Small catalog marks |
| `palette` | bone | `bone`, `amber`, `verdigris` |
| `detail` | auto | Text resolution and mote count |

**Build notes.** Slabs are projected rectangles with a thin edge and a dark face. Pre-render
each slab's text to a surface once, then mask it with the light bar. The camera glide can be
a simple offset along a shallow diagonal, with slabs placed on a sparse 3D lattice. Keep the
text small and high-contrast; do not animate letter positions per frame. If a text file is
missing, fall back to a built-in list and log once.

**Differentiation.** `imaginarylibrary` is an interior with books and readers;
`cosmiclibraryindex` is a console. This is an exterior monument in the dark, closer to a
memorial than a library.

---

#### 5.8 Aurora Relay

`aurorarelay` · science fiction · render A/F · build M · wave 3

**Pitch.** A remote arctic listening station under a green-violet aurora. Three dishes track
something invisible, snow falls, a beacon pulses, and every twenty seconds a faint signal
runs up the mast and disappears.

**Frame.**

```text
+------------------------------------------------------------------+
| AURORA RELAY // 78 N                          SIGNAL  -97 DBm     |
|       ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~            |
|    ~~~~~ aurora curtains ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~           |
|  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~       |
|       |\_/|        |\_/|         |\_/|        |\_/|              |
|      /|   |\      /|   |\       /|   |\      /|   |\             |
|     / |   | \    / |   | \     / |   | \    / |   | \            |
|  __/__|___|__\__/__|___|__\___/__|___|__\__/__|___|__\___        |
|        snow        snow         snow        snow                 |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Aurora | Vertical curtains undulate and change brightness | 45–90 s |
| Dishes | Track a slow arc across the sky | 180 s, a few degrees |
| Snow | Two parallax layers | 10–20 px/s |
| Beacon | A slow red pulse on the mast | 4 s |
| Signal | A bright pulse travels up the mast | 20 s |
| Meteor | A rare streak across the aurora | 1 / 2–3 min |

**Signature.** A meteor crosses the aurora and all three dishes move at once, as if the station
has noticed.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `aurora_intensity` | 0.7 | 0 = stars only |
| `dish_count` | 3 | 2–4 |
| `snow` | true | Two parallax layers |
| `tracking_speed` | 1.0 | Multiplier on the dish arc |
| `beacon` | true | Slow mast pulse |
| `palette` | aurora | `aurora`, `ice`, `ember` |
| `show_hud` | true | One small telemetry block |

**Build notes.** Aurora curtains are vertical ribbons: a set of columns with a sinusoidal
horizontal offset, drawn as translucent vertical strips with additive color. Cache the sky
gradient; animate only the ribbons. Dishes are simple silhouette geometry with a rim light.
Snow is a particle layer with a slow horizontal drift. This is a grounded scene, so avoid the
temptation to add orbital hardware.

**Differentiation.** Space Station V is orbital and metallic; this is Earth, weather, and a
warm hut window. It is the collection's "cozy science fiction" entry.

---

### II. The arcane

#### 5.9 The Wizard's Observatory

`wizardsobservatory` · fantasy · render F/W · build M · wave 2

**Pitch.** A tower room at night: an arched window full of invented constellations, a brass
armillary sphere, three floating glyph rings, candles, stacks of books, a sleeping cat, and
dust in the candlelight. The room is warm; the sky is cold.

**Frame.**

```text
+------------------------------------------------------------------+
| THE WIZARD'S OBSERVATORY                     CLEAR // MOONWAX     |
|      *       .        *          .       *        .              |
|   .-~~~~~~~~~~~-.     ____       .-~~~~~~~~~~-.                  |
|  (   night sky   )   /    \     (  constellation )               |
|   '-.__________.-'  |  (o)  |    '-.________.-'                  |
|          |           \______/           |                         |
|     .-~~~|~~~-.     candles       .-~~~|~~~-.                    |
|    (  armillary )    ( ( ) )     (  glyph ring )                 |
|  ___|___________|________________|___________|___________       |
|     books          desk                      cat                  |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Armillary | Inner and outer rings rotate on different axes | 120 s |
| Glyph rings | Counter-rotating circles of symbols | 40 s / 60 s |
| Candles | Slow flame sway and a small halo | 1–2 Hz |
| Dust | Motes in the candlelight | 0.5 px/s |
| Constellations | The ceiling chart turns with the night | 300 s |
| Cat | A slow breath, an occasional ear twitch | 5 s / 30 s |
| Page | A book page turns by itself | 1 / 90 s |

**Signature.** A constellation on the ceiling draws itself line by line, holds, then fades.
The armillary turns to align with it for a few seconds.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `palette` | candlelight | `candlelight`, `moon`, `verdigris` |
| `armillary_speed` | 1.0 | Multiplier; 0 freezes the instrument |
| `candle_count` | 3 | 1–5; more light, more flicker |
| `show_cat` | true | The sleeping cat |
| `show_constellations` | true | Ceiling chart |
| `dust` | true | Motes in the light |
| `detail` | auto | Ring subdivision and book detail |

**Build notes.** The room is a layered vector illustration, cached. The armillary is a set of
ellipse rings drawn with a simple 3D projection; the glyph rings are pre-rendered text
surfaces rotated as a whole, not per-glyph. Candlelight is a radial gradient sprite plus a
small flame. Do not animate the wallpaper or the books; stillness makes the moving parts read.
An optional background painting can replace the vector room later, but the vector version is
the fallback.

**Differentiation.** The Arcane Laboratory is a control-panel layout over a painting, with
interactive overlays. This is a scene with no controls, no gauges, and no UI; the magic is in
the objects, not the interface.

---

#### 5.10 The Sleeping Dragon

`sleepingdragon` · fantasy · render F · build M · wave 2

**Pitch.** A colossal dragon asleep on its hoard in a cavern. It breathes once every seven
seconds; embers drift; gold glints in the dark; the tail tip moves now and then. Once every
minute or two, one eye opens, reflects the embers, and closes again.

**Frame.**

```text
+------------------------------------------------------------------+
| THE SLEEPING DRAGON                           CAVERN 04 // 3 AM   |
|   *      .        *       .        *       .        *            |
|      ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~             |
|    .-~~~-.        .-~~~~~~~~~~~~~~~~~~~~-.         .-~~~-.       |
|   ( hoard )      /   coiled, breathing     \       ( hoard )     |
|    `-...-'      |   ~~~~~    ~~~~~    ~~~~~ |       `-...-'      |
|                  \        (o)  one eye       /                   |
|    embers  .  .   '-.____________________.-'   .  .  embers      |
|  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~     |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Breath | The body rises and settles by 1–2% | 7 s |
| Smoke | A thin plume from the nostrils | 9 s |
| Tail tip | A slow curl and release | 20 s |
| Embers | Drift upward and fade | 4–8 px/s |
| Gold glints | Small specular points in the hoard | 2–4 s |
| Eye | Opens, reflects, closes | 1 / 90 s, 4 s open |
| Drips | A cave drip and ripple | 15 s |

**Signature.** The eye opens. For four seconds the cavern has a second, amber light source;
then it closes and the room is dark again. Nothing else happens.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `breath_period` | 7.0 | Seconds per breath |
| `ember_rate` | 0.5 | Density of drifting embers |
| `eye_chance` | 0.5 | Probability per minute; 0 disables |
| `hoard` | true | Gold pile and glints |
| `palette` | ember | `ember`, `jade`, `moonstone` |
| `detail` | auto | Scale/rib detail and ember count |

**Build notes.** The dragon is a large silhouette with a rim light and a few dozen scale
lines, not a full mesh. Breath is a vertical scale around a pivot near the chest; the head
and tail can lag slightly for weight. Embers are tiny additive points. The eye is a small
ellipse with a bright slit, drawn only while open. Keep the cave simple: a dark arch, a few
stalactites, and a warm floor bounce.

**Differentiation.** Dungeon and Puppet Theatre are narrative machines. This is a single
tableau with no story beat other than the eye. The dragon is never a threat.

---

#### 5.11 Lantern Procession

`lanternprocession` · fantasy · render F · build M · wave 1

**Pitch.** A line of paper lanterns winds through a dark forest and along the edge of a stream.
Each lantern carries a small sigil; each has a reflection. The procession moves at walking
pace; fireflies drift between the trees; mist sits low over the water.

**Frame.**

```text
+------------------------------------------------------------------+
| LANTERN PROCESSION                          NIGHT // 412 STEPS   |
|    *        .          *         .          *          .         |
|  |||      |||       |||        |||        |||        |||         |
|  |||      |||       |||        |||        |||        |||         |
|   |   (o)   |    (o)   |    (o)   |    (o)   |    (o)   |        |
|   |    |    |     |    |     |    |     |    |     |    |        |
|  ~~~~~~~~~~~~~~~~~~~~~~~~ stream ~~~~~~~~~~~~~~~~~~~~~~~~~~       |
|   (o)    (o)     (o)     (o)     (o)     (o)   reflections       |
|  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~      |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Procession | Lanterns follow a cached spline through the trees | 6 px/s |
| Bob | Each lantern rises and falls slightly | 3 s, phase-offset |
| Flames | Small flame sway inside each lantern | 1–2 Hz |
| Reflections | Flipped, blurred, low-alpha copies in the stream | follows source |
| Fireflies | Slow blinking points between the trees | 4–9 s |
| Mist | Low bands drift across the water | 0.5 px/s |

**Signature.** One lantern leaves the line, drifts down to the stream, and goes out. Its
reflection remains for a few seconds after the lantern is gone.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `lantern_count` | 14 | 8–20 |
| `speed` | 6.0 | px/s along the path |
| `sigil_set` | built-in | Optional JSON list of glyphs |
| `reflection` | true | Stream reflections |
| `mist` | true | Low fog bands |
| `palette` | moss | `moss`, `indigo`, `mono` |
| `detail` | auto | Lantern detail and tree count |

**Build notes.** The path is a Catmull-Rom spline in screen space, cached once. Lanterns are
small polygons with a warm core and a paper-colored rim; the glow is an additive sprite. The
reflection is the same sprite flipped and blurred, drawn at low alpha. Trees are layered
silhouettes, not individual leaves. Keep the procession small; the forest should feel larger
than the line.

**Differentiation.** This is not a festival scene: there are no people, no crowd, no music.
The lanterns are the only inhabitants, and the forest is the subject.

---

#### 5.12 Runic Tide

`runicide` · fantasy · render F/A · build M · wave 3

**Pitch.** A black-sand beach at night. Each wave arrives with a line of luminous runes in the
foam; the runes hold for a few seconds, then fade as the water pulls back. The tide rises
slowly over six minutes; the moon moves; a sea stack stands offshore.

**Frame.**

```text
+------------------------------------------------------------------+
| RUNIC TIDE // HIGH WATER 03:12                 MOON WANING       |
|        .          *             .         *          .           |
|                        (  moon  )                                |
|  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~      |
|  ~~~~~~  F E A R   N O T   T H E   D E E P  ~~~~~~~~~~~~~~      |
|  ~~~~~~  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~        |
|  ~~~~~~  ~~~~~  [runes]  ~~~~~  [runes]  ~~~~~~~~~~~~~~         |
|  ________________________________________________________________|
|  black sand   .   .   .   .   .   .   .   .   .   .   .         |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Waves | Bands advance, curl, and retreat | 9–14 s |
| Runes | Appear in the foam, brighten, fade | 6 s |
| Tide | The shoreline advances up the sand | 360 s |
| Moon | A slow arc across the sky | 600 s |
| Sea stack | Static silhouette with a light at the top | 0.5 Hz pulse |
| Stars | Slow twinkle | continuous |

**Signature.** A full line of runes forms a readable sentence — one line of invented prophecy
— and stays legible for five seconds before the next wave takes it.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `tide_period` | 360 | Full tide cycle |
| `wave_count` | 4 | Overlapping wave bands |
| `rune_alphabet` | built-in | Optional JSON glyph set |
| `show_moon` | true | Moon and its reflection |
| `palette` | moon | `moon`, `ember`, `verdigris` |
| `detail` | auto | Glyph complexity and spray |

**Build notes.** Waves are wide bezier bands with a bright foam edge; the runes are line
glyphs drawn into the foam band and masked to it. Spawn glyphs as the wave crosses a threshold,
then fade them with the retreat. The tide is a single shoreline offset, not a simulation. The
prophecy lines come from a short original list; never quote a real text.

**Differentiation.** The console modes use text as interface. Here the text is environmental:
it arrives with the sea, is read for a moment, and is taken away.

---

#### 5.13 The Glass Castle

`glasscastle` · fantasy · render H · build L · wave 3

**Pitch.** A castle grown from crystal stands on a cliff under an aurora. Snow falls; windows
glow; detached shards orbit the towers; the whole scene drifts past at half a pixel per
second. It is a fairy tale, not a dungeon.

**Frame.**

```text
+------------------------------------------------------------------+
| THE GLASS CASTLE                              AURORA 07 // -12C  |
|     ~~~~~ aurora ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~         |
|      /\/\/\      /\      /\      /\      /\      /\/\/\          |
|     /  ||  \    /  \    /  \    /  \    /  \    /  ||  \         |
|    /   ||   \  /    \  /    \  /    \  /    \  /   ||   \        |
|   /    ||    \/      \/      \/      \/      \/    ||    \       |
|  ============ crystal spires ============== snow ===========     |
|   *   snow   *    *    snow   *   *   snow   *   *   snow   *    |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Camera | A slow lateral drift past the castle | 0.5 px/s |
| Aurora | Curtains undulate and shift hue | 60 s |
| Snow | Two parallax layers | 8–16 px/s |
| Windows | Warm lights flicker on and off | 3–7 s |
| Shards | A few crystal fragments orbit the towers | 20–40 s |
| Reflections | The aurora shimmers in the glass | follows aurora |

**Signature.** The aurora brightens and its reflection doubles the color inside the castle's
glass for a few seconds, as if the building is lit from within.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `aurora` | true | Curtains and reflections |
| `snow` | true | Two parallax layers |
| `camera_drift` | 0.5 | px/s |
| `window_lights` | true | Warm windows |
| `shard_count` | 6 | 0–10 |
| `palette` | ice | `ice`, `aurora`, `rose` |
| `detail` | auto | Facet count and tower detail |

**Build notes.** The castle is a layered silhouette with facet lines, not a 3D model. Build
three depth layers — far towers, main keep, near cliff — and move them at slightly different
speeds. The glass read comes from a cool fill, a bright edge, and a few internal facet lines.
Aurora reflections are a second, low-alpha ribbon clipped to the castle silhouette. Snow is a
particle layer; shards are small polygons with a glint.

**Differentiation.** The fantasy modes already have maps, dungeons, a library and a puppet
theatre. This is a pure vista with no narrative system and no UI.

---

### III. Living worlds

#### 5.14 Leviathan Passage

`leviathan` · fantasy · render F · build M · wave 2

**Pitch.** At dusk, a pod of leviathans crosses the horizon. They are so large that the sea
barely notices them; a small boat gives the scale. Mist, a low moon, and a long wake are the
only evidence that anything is moving.

**Frame.**

```text
+------------------------------------------------------------------+
| LEVIATHAN PASSAGE                    DUSK // MIGRATION 07        |
|      *       .          *            .        *                  |
|  ~~~  ~~~~~~~~~~~~~  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~  ~~~          |
|  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~      |
|        __       __            __                                  |
|      .'  '.   .'  '.        .'  '.        __                       |
|   __/      \_/      \______/      \______/  \___                  |
|  (        huge, slow silhouettes       )     (boat)               |
|  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~      |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Pod | Silhouettes cross the horizon | 120 s |
| Bodies | A slow vertical undulation | 12 s |
| Spouts | A mist plume rises and disperses | 20 s |
| Mist | Layered bands drift | 0.5 px/s |
| Waves | A few long swell lines | 1 px/s |
| Moon | Static or a very slow arc | 600 s |

**Signature.** The largest leviathan passes behind the moon and eclipses it for four seconds.
The sea keeps moving.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `pod_size` | 3 | 2–5 |
| `crossing_seconds` | 120 | Time to cross the frame |
| `mist` | true | Layered horizon fog |
| `moon` | true | Low moon, optional eclipse |
| `scale_reference` | boat | `boat`, `lighthouse`, `none` |
| `palette` | dusk | `dusk`, `bone`, `ember` |
| `detail` | auto | Body ribs and wake detail |

**Build notes.** Each leviathan is a bezier spine with a few ribs and a tail; the body moves as
a wave along the spine, not as a sprite. Draw them as near-black silhouettes against a dusky
gradient, with one rim light. Reflections are flipped, low-alpha copies under the waterline.
The boat is four lines and a dot; it does all the scale work.

**Differentiation.** This is not a monster attack and not a natural-history diagram. The
creatures are indifferent, the sea is calm, and the mood is wonder rather than threat.

---

#### 5.15 Terraform

`terraform` · science fiction · render F/H · build L · wave 3

**Pitch.** A world is terraformed over three minutes. Ice retreats, rivers branch toward the
sea, green spreads from the coasts, and city lights appear along the new waterways. A thin
timeline at the bottom marks the year. The camera never moves; the world changes.

**Frame.**

```text
+------------------------------------------------------------------+
| TERRAFORM // YEAR 041                      STAGE 03: BIOSPHERE   |
|   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~   |
|   ~   .-~~~-.        ~~~~~~~~~~~       .-~~~-.        ~~~~~~   ~ |
|   ~  (  ice  )      ~~~ ocean ~~~     ( forest )      ~~~~~~   ~ |
|   ~   `-...-'        ~~~~~~~~~~~       `-...-'                 ~ |
|   ~      |  river --->  ~~~~~~~~~~~~~~~~~~~  <--- river  |      ~ |
|   ~   .-~~~-.        ~~~~~~~~~~~       .-~~~-.                 ~ |
|   ~  (  city  )      ~~~ cloud ~~~     (  ice  )               ~ |
|   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~   |
|   YEAR 000 ==============|======================== YEAR 120       |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Terraforming stage | Ice → water → algae → forest → cities | 45 s per stage |
| Palette | Slow interpolation between stage palettes | 20 s crossfade |
| Rivers | Branch outward from the highlands | 1 px/s growth |
| Clouds | Two soft bands drift | 2 px/s |
| City lights | Appear along rivers in a wave | 6 s |
| Mirror glint | A bright reflection crosses the terminator | 1 / 90 s |

**Signature.** The first river reaches the sea; the ocean shifts from gray to blue, and the
first city lights appear along its delta.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `cycle_seconds` | 180 | Full transformation |
| `start_stage` | 0 | 0–4; useful for previews |
| `show_timeline` | true | The year bar |
| `seed` | unset | Pinned world shape |
| `palette` | biosphere | `biosphere`, `ice`, `desert` |
| `detail` | auto | Contour count and river detail |

**Build notes.** Generate a low-resolution height field once; derive contour bands, rivers
and a vegetation mask. Render eight keyframes at a reduced internal resolution (for example
640×200), cache them, and crossfade between stages. Animate only the rivers, clouds, city
lights and mirror glint in between. This is a compositing mode, not a per-pixel simulation;
the expensive work happens once per stage.

**Differentiation.** `inkmap` and `fantasymapgenerator` are cartography with a historical or
fantasy voice. This is a scientific process over time, with a timeline and a palette that
changes because the world is changing.

---

#### 5.16 Descent

`descent` · horror / science fiction · render A · build M · wave 2

**Pitch.** The view from a bathyscaphe descending into a trench. A spotlight cone sways ahead
of the hull; particles stream upward; the depth gauge climbs; bioluminescent flashes appear
and vanish. At rare intervals, something enormous passes the edge of the light.

**Frame.**

```text
+------------------------------------------------------------------+
| DESCENT // DSV-9                              DEPTH 4,120 M     |
|  +------------------------------------------------------------+  |
|  |  .   *      .        .       *       .       .    *        |  |
|  |        .-~~~~~-.          .          .-~~~~~-.             |  |
|  |   *   (  glow   )    .         *    (  glow   )    .       |  |
|  |        `-.....-'          .          `-.....-'            |  |
|  |    .        *       .        .    *       .        .      |  |
|  |                  \   |   /                                  |  |
|  |                   \  |  /  <-- spotlight cone               |  |
|  +------------------------------------------------------------+  |
|   HULL TEMP 2.1 C     PRESSURE 412 ATM     O2 18%               |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Particles | Stream upward past the camera | 10–20 px/s |
| Spotlight | A slow sway at the end of the cone | 4 s |
| Sonar | A ring pulse and a faint return | 8 s |
| Bioluminescence | Small flashes in the dark | 1–5 s, sparse |
| Hull | A tiny roll and settling | 0.3°, 9 s |
| Creature | A silhouette passes the light | 1 / 60–120 s |
| Depth | The gauge climbs continuously | forever |

**Signature.** The spotlight catches a wall of pale scales. For two seconds it looks like a
surface; then the surface blinks, and the light is alone again.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `descent_speed` | 1.0 | Gauge rate and particle speed |
| `visibility` | 0.5 | 0 = almost dark, 1 = clear water |
| `creature_chance` | 0.4 | Per minute; 0 disables |
| `show_hud` | true | Depth and pressure only |
| `palette` | abyss | `abyss`, `amber`, `bone` |
| `detail` | auto | Particle count and hull detail |

**Build notes.** The water column is a cached vertical gradient. The spotlight cone is a
translucent polygon with an additive core; particles are small, slow points that fade with
depth. The creature is a low-alpha silhouette drawn *behind* the light cone, so it is never
fully visible. The hull frame at the edges is four or five lines. Keep the HUD to one line;
the screen is the viewport.

**Differentiation.** `abyssalbloom` is an external view of creatures. This is first-person,
inside a vehicle, with a depth gauge and a limited cone of light. The two can coexist without
sharing a renderer.

---

### IV. Quiet dread

#### 5.17 The Black Lighthouse

`blacklighthouse` · horror · render F/A · build M · wave 1

**Pitch.** A black lighthouse on a basalt rock, wrapped in fog. Its beam sweeps the sea every
ten seconds. The keeper's window is lit. On some sweeps, the beam finds a ridge in the water
that was not there before.

**Frame.**

```text
+------------------------------------------------------------------+
| THE BLACK LIGHTHOUSE                       FOG // BEARING 000    |
|          .-~~~~-.                                                |
|         /  beam  \_____________                                  |
|        /    |     \             \                                |
|       |     |      \             \                               |
|  ~~~~~|~~~~~|~~~~~~~\~~~~~~~~~~~~~\~~~~~~~~~~~~~                 |
|       |   [X]        \              \                            |
|  ~~~~~|~~~~~~~~~~~~~~~~\~~~~~~~~~~~~~~\~~~~~~~~~~                |
|   ~~~~ rock ~~~~   ~~~~~ sea ~~~~~~  ~~~~~ shape? ~~~~           |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Beam | A cone sweeps across the water | 10 s per revolution |
| Fog | Layered banks drift | 0.8 px/s |
| Waves | Long swell lines and a foam edge | 3–5 s |
| Keeper's window | A warm light, with a rare shadow | 4 s / 2–3 min |
| Sea shape | A ridge under the water, visible only in the beam | 1 / 90–150 s |
| Beacon | The lamp itself pulses at the top | 10 s |

**Signature.** The beam passes over the water and, for one sweep, reveals a long ridge that
runs parallel to the shore. The next sweep finds only waves.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `sweep_seconds` | 10 | One full beam rotation |
| `fog_density` | 0.6 | 0 = clear night |
| `manifestation_chance` | 0.5 | Per minute; 0 disables the shape |
| `show_log` | false | A one-line keeper's log, optional |
| `palette` | ash | `ash`, `cold`, `mono` |
| `detail` | auto | Beam softness and fog layers |

**Build notes.** The beam is a triangle with an additive gradient, a bright leading edge, and
a slow fade. Fog is four or five horizontal bands of translucent noise, cached and scrolled.
The lighthouse is a simple silhouette with a lit lamp and a few window rectangles. The sea
shape is a low-alpha polygon under the waterline; it should never be sharp. Do not add a
monster reveal; the ambiguity is the effect.

**Differentiation.** The registry has ominous consoles and threat maps, but no dedicated
horror scene. This is atmosphere and omission, not a threat display.

---

#### 5.18 The Empty House

`emptyhouse` · horror · render F · build M · wave 3

**Pitch.** A cutaway of a Victorian house at three in the morning. Most rooms are dark; one
has a candle. A door at the end of the hall is ajar and opens very slowly. A curtain moves.
Once every few minutes, a silhouette crosses an upstairs window.

**Frame.**

```text
+------------------------------------------------------------------+
| THE EMPTY HOUSE                                  3:07 AM         |
|   ______________________________  ______________________________  |
|  |   |     |      |     |      | |      |     |     |     |    | |
|  |   |     |  [candle]  |      | |      |     |     |     |    | |
|  |   |     |   (o)      |      | |      |     |     |  door|    | |
|  |___|_____|____________|______| |______|_____|_____|_____|    | |
|  |   |     |            |      | |      |     |     |     |    | |
|  |   |     |            |      | |      |     |     |     |    | |
|  |___|_____|____________|______| |______|_____|_____|_____|    | |
|      cross-section; one window lit, one door ajar                 |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Candle | Flame sway and a small pool of light | 1–2 Hz |
| Curtain | A slow lift and fall at the window | 6 s |
| Door | Opens a few degrees at a time | 30 s |
| Dust | Motes in the candle room | 0.5 px/s |
| Silhouette | Crosses an upstairs window | 1 / 2–3 min |
| Clock | A pendulum or a clock hand | 60 s |
| House | Static; no camera move | — |

**Signature.** The ajar door opens fully. A moment later, the candle in that room goes out.
The rest of the house is unchanged.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `room_count` | 6 | 4–8; more rooms, more detail |
| `event_rate` | 0.5 | Silhouette/door events per minute |
| `show_caption` | false | A single line of text, off by default |
| `palette` | sepia | `sepia`, `night`, `mono` |
| `detail` | auto | Wallpaper and furniture detail |
| `flicker` | true | Candle flicker; can be disabled |

**Build notes.** The house is a vector cross-section: walls, floors, wallpaper bands, a few
pieces of furniture. Cache the static rooms. Animate only the candle, the curtain, the door,
the dust and the silhouette. The cutaway is the joke and the charm; keep the rooms readable
rather than cluttered. The silhouette should be a shape, never a detailed figure.

**Differentiation.** This is not a haunted-house ride. There is one impossible detail at a
time, and the house is mostly still.

---

#### 5.19 The Orchard at 3 A.M.

`orchard3am` · horror / folk · render F · build S · wave 1

**Pitch.** A moonlit orchard in late autumn. Bare branches move in the wind, ground fog
crosses the rows, and a scarecrow stands by the fence. At the edge of the treeline, a figure
is visible — but only while the fog is thick. When it clears, the figure is somewhere else.

**Frame.**

```text
+------------------------------------------------------------------+
| THE ORCHARD, 3 A.M.                          MOON // WIND 4 KT    |
|      *        .          *            .         *        .       |
|   (  moon  )                                                     |
|     |||      |||       |||        |||       |||       |||        |
|     |||      |||       |||        |||       |||       |||        |
|     |||      |||       |||        |||       |||       |||        |
|  ~~~~~~~~~~~~~~~~ fog ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~        |
|     scarecrow                 figure?                  fence      |
|  ________________________________________________________________ |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Branches | A slow sway, phase-offset per tree | 4–7 s |
| Fog | Two low layers drift across the rows | 0.5 px/s |
| Grass | A faint ripple at the bottom edge | 3 s |
| Moon | Static or a very slow arc | 600 s |
| Figure | Changes position while obscured by fog | 1 / 40–80 s |
| Scarecrow | A coat, a hat, a slow creak | 20 s |

**Signature.** The fog clears. The figure is gone, and the scarecrow is wearing a different
coat. Nothing else in the frame has changed.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `wind` | 0.5 | Branch sway amplitude |
| `fog` | 0.6 | Fog density and speed |
| `figure_frequency` | 0.5 | Moves per minute; 0 disables |
| `show_moon` | true | Moon and halo |
| `palette` | moon | `moon`, `rust`, `mono` |
| `detail` | auto | Tree branch and grass detail |

**Build notes.** The orchard is four or five layers of silhouettes, from far treeline to near
grass. Branch sway is a small rotation around the trunk base. Ground fog is a translucent
horizontal band with a soft edge; use it to hide the figure's position changes. The figure is
a simple dark shape; never give it a face. This is the cheapest horror mode in the set and
one of the most effective.

**Differentiation.** No chase, no gore, no jump scare. The horror is in what the fog chooses
not to show.

---

#### 5.20 The Long Corridor

`longcorridor` · horror · render W/F · build M · wave 3

**Pitch.** A one-point-perspective corridor with repeating doors, sconces and carpet. The
camera dollies forward at a walking pace but never arrives. One door is ajar. A shadow at the
far end is always the same size, until it isn't.

**Frame.**

```text
+------------------------------------------------------------------+
| THE LONG CORRIDOR                             DOOR 08 OF 08      |
|  |==============================================================|  |
|  |  ||      ||      ||      ||      ||      ||      ||      ||  |  |
|  |  ||      ||      ||      ||      ||      ||      ||      ||  |  |
|  |  ||  ()  ||  ()  ||  ()  ||  ()  ||  ()  ||  ()  ||  ()  ||  |  |
|  |  ||      ||      ||      ||      ||      ||      ||      ||  |  |
|  |  ||      ||      ||      ||      ||      ||      ||      ||  |  |
|  |______________________  vanishing point  ____________________|  |
|         sconce     sconce    carpet      sconce     sconce       |
|                          camera -->                              |
+------------------------------------------------------------------+
```

**What moves.**

| Element | Motion | Period |
|---|---|---|
| Camera | A slow dolly down the corridor | 6–10 px/s |
| Corridor | Door frames scale and pass; the pattern loops | 40 s |
| Sconces | Local flicker; one is weaker than the rest | 0.5–1 Hz |
| Door | The ajar door opens a little more | 20 s |
| Shadow | A dark shape at the vanishing point | 0.5 px/s |
| Light | A pool of light travels with the camera | continuous |

**Signature.** The camera passes a door and the corridor beyond is one door shorter than it
was. The shadow at the end is closer.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `dolly_speed` | 8.0 | px/s; higher feels like a game |
| `flicker` | 0.3 | Sconce flicker; 0 disables |
| `event_rate` | 0.5 | Door/shadow events per minute |
| `palette` | sepia | `sepia`, `green`, `mono` |
| `show_caption` | false | Optional room number |
| `detail` | auto | Door and carpet detail |

**Build notes.** Build the corridor from perspective quads: a floor, a ceiling, two walls,
and a repeating set of door frames. The camera position drives the scale of each frame. Pre-
render one segment, but vary which doors are lit so the repetition is not obvious. The
shadow is a low-contrast silhouette at the vanishing point. Keep the vanishing point slightly
off-center for unease.

**Differentiation.** No monster chase, no weapons, no map. The dread is architectural and
cumulative, and the camera never stops.

---

## 6. Build order and rotation

### 6.1 Recommended waves

**Wave 1 — prove the range (six modes).** Orrery, Gravity Well, Abyssal Bloom, Black
Lighthouse, Lantern Procession, Orchard at 3 A.M. These cover wireframe, abstract, atmospheric,
illustrated, fantasy and horror, and all are small enough to prototype without a new package.
If the first wave works, the collection has a credible identity.

**Wave 2 — the vistas (seven modes).** Ringworld, Event Horizon, Slow Sail, Leviathan,
Wizard's Observatory, Sleeping Dragon, Descent. These are the larger compositions and the
ones most likely to need an art-direction pass before code.

**Wave 3 — the long cycles (seven modes).** Terraform, Long Archive, Aurora Relay, Runic Tide,
Glass Castle, Empty House, Long Corridor. These either need cached keyframes or a more
involved layered illustration, and they benefit from the lessons of the first two waves.

This is a recommendation, not a dependency graph. No mode requires another to exist.

### 6.2 A rotation recipe

The current narrow profile runs 21 modes (slots 0–20). The new collection should not be
dropped in as a contiguous block; it should be sequenced for contrast. A suggested 30–40
minute set:

1. **Dawn:** Sunrise → Ringworld → Aurora Relay
2. **Day:** Terraform → Orrery → Slow Sail
3. **Dusk:** Leviathan → Lantern Procession → Glass Castle
4. **Night:** Event Horizon → Long Archive → Abyssal Bloom
5. **Late:** Black Lighthouse → Gravity Well → Empty House → Lantern Procession → Orchard
   at 3 A.M. → Aurora Relay → Descent → Orrery → Long Corridor

Rules for the sequence:

- Never two horror modes back to back; put a bright or abstract mode between them.
- Give the scenic modes a longer dwell than the console modes. 90–180 seconds is a better
  default for this collection than the 30-second auto-cycle.
- Alternate render styles (wireframe, flat, atmospheric) so the wall does not feel like one
  filter.
- Keep at least one bright mode in every four.

### 6.3 Profile placement

- The 1280×400 profile has free slots from 21 upward. Proposed additions go there first;
  exact numbers are deferred until the review chooses which modes to build.
- Do not renumber existing slots. Do not merge the portrait and landscape profiles.
- Accepted modes can be mirrored into `configs/modes_config_vert.json`,
  `configs/modes_config_portrait.json`, or the 16:9 profiles at their next free slots.
- A mode is not "in the collection" until it has a registry entry, at least one instance, and
  a validated profile. The design document is not a config change.

---

## 7. Relationship to existing modes

The registry is already large (58 types). The new collection is deliberately adjacent to it,
not overlapping. The closest existing modes and the distinction:

| Existing | Closest new mode | Why they do not collide |
|---|---|---|
| `galacticnavigation`, `alienstarmapcartographer`, `satellitetracker` | Orrery, Ringworld | Those are consoles and charts; the new ones are physical places or instruments, with no data feed |
| `spacestation`, `cyberspace`, `trenchrun` | Gravity Well, Event Horizon, Slow Sail | Existing modes are built environments or vehicles; the new ones are an abstract diagram, an object portrait, and a convoy |
| `cosmiclibraryindex`, `imaginarylibrary` | Long Archive | Index console and library interior versus an exterior monument in the dark |
| `inkmap`, `fantasymapgenerator` | Terraform | Ink/fantasy cartography versus a scientific process over time |
| `controlpanel` (including the Arcane Laboratory layout) | Wizard's Observatory | A control-panel layout with interactive overlays versus a scene with no controls |
| `antfarm`, `sunrise` | Leviathan, Lantern Procession | Different biome, scale and motion language; no shared assets |
| `dungeon`, `puppetheatre` | Sleeping Dragon, Glass Castle | Adventure/theatre systems versus a single tableau or vista |
| `globalthreatmap`, `rbmkreactorsimulation` | Black Lighthouse, Empty House | Ominous dashboards versus atmospheric horror scenes with no data |
| — | Descent, Orchard, Long Corridor | The registry currently has no dedicated first-person or folk-horror scene |

The existing modes also set a useful constraint: this project already has plenty of consoles.
The new collection should lean scenic. If a concept needs a dashboard to be interesting, it is
probably the wrong concept for this set.

---

## 8. Risks and open questions

### 8.1 Risks

| Risk | Mitigation |
|---|---|
| **Horror is unwelcome in a shared space** | Keep the register to "quiet dread"; no gore, no jump scares, no audio. Give every horror mode an `intensity` or `flicker` switch and a calm default. |
| **Twenty is a lot of surface area** | Treat this as a menu. Build wave 1, review the look, then decide. Do not start twenty branches. |
| **The Pi cannot hold 60 fps** | Design to the S/M/L budgets, use `auto` quality, cache static layers, and accept a 30 fps floor for the largest modes. |
| **Dark scenes read as empty** | The poster-frame rule: every mode needs a clear silhouette and one warm or bright anchor. Test a still frame before adding motion. |
| **Loops become obvious** | Co-prime periods, seeded variation, one-shot events, and 90–600 s cycles. Review a five-minute capture, not a ten-second one. |
| **HUD creep** | Default to `hud: "minimal"`; no fake cards or nested panels. The existing console modes already own that language. |
| **Art quality varies across twenty modes** | Do an art-direction pass per mode before code: one still frame, one palette, one motion test. Reject a mode at the still-frame stage if it does not read. |
| **Text and lore become a writing project** | Keep lore to one or two original lines per mode; built-in fallbacks; no copyrighted quotations. |
| **Assets and licensing** | All modes can be fully procedural. Optional paintings or data files must be original or cleared, and must fail soft if absent. |
| **Profile clutter** | Add only accepted modes; keep the existing slot numbering; mirror selectively into the other profiles. |

### 8.2 Questions for review

1. **Horror register.** Is "quiet dread" the right ceiling — atmospheric, no gore, no jump
   scares, no audio — or does the wall want something more overt? *Recommendation: quiet
   dread, with a per-mode intensity switch.*
2. **Brightness.** The house style is dark. Six of these are deliberately bright or dawn-lit.
   Is that the right balance, or should the collection stay uniformly nocturnal?
   *Recommendation: keep the six; a rotation needs contrast.*
3. **HUD.** Should these be scene-first with a minimal HUD, or do you want the telemetry
   language of the existing console modes? *Recommendation: scene-first; HUD off or minimal
   by default.*
4. **Render mix.** The set is roughly 9 wireframe/hybrid, 7 flat/illustrated, 4 atmospheric.
   Is that the right ratio, or should the next collection lean harder into wireframe?
5. **Real data.** Should any mode use the real clock, moon phase, or weather? *Recommendation:
   fictional time in v1; real moon phase is a possible later option for Runic Tide, not a
   dependency.*
6. **Shared code.** Should the first wave share a scene kit (palette, bloom, stars), or stay
   standalone one-file modes? *Recommendation: standalone first; extract a kit only after
   three modes need the same thing.*
7. **First wave.** Are the six wave-1 modes the right first bet, or is there a different
   priority? *Recommendation: build Orrery and Black Lighthouse first; they are the clearest
   statements of the two halves of the collection.*
8. **Names.** The titles are placeholders with a particular voice. Do you want a naming pass
   before the registry entries, or should the type keys and titles be settled during build?

---

## 9. What this document is not

- Not twenty finished modes. It is a menu for review.
- Not a shared framework. The collection shares a visual language, not necessarily a module.
- Not a change to the controller, registry, or profiles.
- Not a commitment to external art, video, audio, network data, or new dependencies.
- Not a game. No mode has controls, goals, scores, or fail states.
- Not a horror attraction. The horror modes are atmospheric, not assaultive.

---

## Appendix A — Common parameters

Every mode should support the same small set of common keys, in addition to its signature
parameters. This keeps the control panel predictable and the registry entries consistent.

| Key | Type | Default | Notes |
|---|---|---|---|
| `seed` | integer or null | null | Unset = a new scene on entry; pinned = reproducible |
| `palette` | choice | per mode | Two or three named variants |
| `hud` | choice | `minimal` | `none`, `minimal`, `full` where the mode supports it |
| `quality` | choice | `auto` | `auto`, `low`, `medium`, `high` |
| `title` | text | mode name | Optional override for the HUD |
| `subtitle` | text | per mode | Optional secondary line |
| `intensity` | choice | `calm` | Horror modes only: `calm`, `uneasy` |
| `flicker` | switch | true | Candle/sconce flicker; horror modes may default off |

Registry conventions for each accepted mode:

- `required`: normally empty; a mode should start with defaults.
- `optional`: the common keys plus every signature key the mode reads.
- `params`: widgets, ranges, choices and help text for the keys that benefit from tuning.
  Values are inferred for keys without a `params` block, but a little schema goes a long way
  on the panel.
- The type key is lowercase, with no spaces or underscores. The instance title is free text.
- All defaults must produce a complete scene without a data file or an external asset.

## Appendix B — Acceptance checklist

Before a mode is considered finished:

- [ ] It renders a composed still frame at 1280×400 with the mode-number area clear.
- [ ] It renders natively at 1080×1920 and 1920×1080; the composition is re-anchored, not
      stretched or cropped from the strip.
- [ ] A ten-second glance shows motion; a five-minute capture does not reveal an obvious loop.
- [ ] All motion is inside the envelope in §2.1, or the exception is documented.
- [ ] `seed` reproduces the scene exactly; `seed` unset gives a new one.
- [ ] `palette` variants change the mood without changing the layout.
- [ ] `auto` quality changes detail, not composition or timing.
- [ ] Missing optional data falls back to a complete built-in scene and logs once.
- [ ] No network, no audio, no external asset is required.
- [ ] `exit()` releases surfaces and any threads; no per-frame logging.
- [ ] The registry entry lists `required`/`optional` accurately; `validate_configs.py --all`
      is green.
- [ ] The panel exposes the signature parameters with sensible widgets and ranges.
- [ ] A preview still at 1280×400 and a short motion capture are attached for review.
- [ ] Horror modes pass the "quiet dread" test: no gore, no jump scare, no strobing, and the
      flicker switch works.

## Appendix C — Naming and file conventions

Suggested file and type names, following the existing registry style:

| Mode | Type key | Suggested file |
|---|---|---|
| The Orrery of Small Worlds | `orrery` | `modes/orrery_mode.py` |
| Ringworld, Facing the Sun | `ringworld` | `modes/ringworld_mode.py` |
| Gravity Well | `gravitywell` | `modes/gravity_well_mode.py` |
| Event Horizon | `eventhorizon` | `modes/event_horizon_mode.py` |
| The Slow Sail | `sailcaravan` | `modes/sail_caravan_mode.py` |
| Abyssal Bloom | `abyssalbloom` | `modes/abyssal_bloom_mode.py` |
| The Long Archive | `longarchive` | `modes/long_archive_mode.py` |
| Aurora Relay | `aurorarelay` | `modes/aurora_relay_mode.py` |
| The Wizard's Observatory | `wizardsobservatory` | `modes/wizards_observatory_mode.py` |
| The Sleeping Dragon | `sleepingdragon` | `modes/sleeping_dragon_mode.py` |
| Lantern Procession | `lanternprocession` | `modes/lantern_procession_mode.py` |
| Runic Tide | `runicide` | `modes/runic_tide_mode.py` |
| The Glass Castle | `glasscastle` | `modes/glass_castle_mode.py` |
| Leviathan Passage | `leviathan` | `modes/leviathan_mode.py` |
| Terraform | `terraform` | `modes/terraform_mode.py` |
| Descent | `descent` | `modes/descent_mode.py` |
| The Black Lighthouse | `blacklighthouse` | `modes/black_lighthouse_mode.py` |
| The Empty House | `emptyhouse` | `modes/empty_house_mode.py` |
| The Orchard at 3 A.M. | `orchard3am` | `modes/orchard_3am_mode.py` |
| The Long Corridor | `longcorridor` | `modes/long_corridor_mode.py` |

Modes that grow beyond roughly 600 lines, or need a procedural mesh/lore module, should get a
package directory alongside the wrapper, following `space_station/`, `cyberspace/` and
`sunrise/`. Do not start with a package; start with one file and split when the file tells you
to.

---

*End of design.*
