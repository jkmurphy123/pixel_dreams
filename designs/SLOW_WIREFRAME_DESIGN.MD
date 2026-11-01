# Slow Wireframe

**Twenty science-fiction wireframe modes for pixel_dreams — design for review**

**Status:** DRAFT FOR REVIEW — design only. No mode code, registry entries, or profile
changes are included in this document.

**Target:** the Raspberry Pi kiosk (`configs/modes_config_narrow_horz.json`, 1280×400),
with the portrait wall (1080×1920) and a conventional 16:9 display as secondary targets.

**Related:** [`SLOW_WORLDS_DESIGN.md`](SLOW_WORLDS_DESIGN.md),
[`CYBERSPACE_DESIGN.md`](CYBERSPACE_DESIGN.md),
[`SPACE_STATION_DESIGN.md`](SPACE_STATION_DESIGN.md),
[`GEOMETRIC_DETAIL_STUDY.md`](GEOMETRIC_DETAIL_STUDY.md).

**The proposal in one sentence.** Twenty new science-fiction scenes built from line, depth and
light — five star-scale engineering projects, four orbital infrastructure projects, four ships
or voyages, three worlds or fields, and four instruments or minds — all meant to sit beside
Trench Run and Cyberspace Matrix without repeating either.

**Review path.** Start with the table in §3 for the menu, open the cards that catch your eye
for the camera and motion notes, then use §7 for the decisions that need a call before any
prototype starts.

---

## 1. The brief

Trench Run and Cyberspace Matrix are the two clearest statements of the wireframe direction so
far. Trench Run is a ride: a first-person camera, a surface scrolling underneath, a ship, and a
vanishing point that pulls the eye forward. Cyberspace is a drift: a city seen from just above
the street, towers passing at different depths, a route that turns only at intersections. One
is speed; one is altitude. Both are built from lines, and both trust the viewer to fill in the
solid.

The request is for twenty more modes in that register. All of them should be science fiction,
all of them wireframe-first, and all of them gentle enough to leave running on a wall. The set
should not become twenty variants of the same tunnel. The interesting question is not "what
else can we draw in neon?" but "what other kinds of place can a line drawing become?"

The answers here are deliberately spread across scale and camera behaviour:

- a star surrounded by a civilization's collectors;
- a shipyard where a hull is being assembled;
- the inside of a hollowed asteroid;
- a generation ship opened like a diagram;
- a dead capital ship turning in the dark;
- an instrument that listens for a ripple in spacetime.

The document is a menu, not a commitment. Each card is a design sketch: a composition, a
motion engine, a palette, a parameter sketch, and a build note. The next step is to choose a
small first wave, prototype the look, and let the still frame decide.

The visual bar is the existing wireframe work:

- [Cyberspace Matrix at 1280×400](../screenshots/narrow_horz/cyberspace_1280x400.png)
- [Trench Run at 1280×400](../screenshots/narrow_horz/trench_run_1280x400.png)
- [Space Station V at 1280×400](../screenshots/space_station/hero_1280x400.png)

---

## 2. The wireframe contract

Wireframe is not a filter applied to a finished scene. It is a way of deciding what the viewer
is allowed to see: structure, edge, orbit, scan, and annotation, with the surfaces left to the
imagination. That restraint is what makes the existing modes feel spacious.

This section is the shared language for the twenty. It is not a framework that must be built
first, but every concept assumes it.

### 2.1 Line is the material

- **No textures.** A line drawing can have fills, but a fill is a deliberate mode (`xray`,
  `panel`), not a photograph under the lines.
- **No depth buffer.** Depth is carried by distance fade, line weight, occlusion, bloom and the
  order in which lines are laid down. The existing modes do this well; keep it.
- **One hero edge.** Each scene has a subject edge that is brighter and slightly heavier than
  everything else. If every line is a hero, nothing is.
- **Negative space is part of the drawing.** A wireframe scene should be mostly dark. The empty
  area is what gives the lines scale.
- **A still frame is a poster.** Pause the mode and it should still read as a place, an object,
  or an instrument.

### 2.2 Line roles

| Role | Typical weight | Brightness | What it does |
|---|---:|---|---|
| **Hero** | 1.5–2 px | 85–100% | The near edge of the subject; the one line the eye follows |
| **Structure** | 1 px | 45–70% | Hull, frame, truss, lattice, machinery |
| **Guide** | 1 px, often dashed | 20–35% | Orbits, scan planes, construction lines, measurements |
| **Far** | 1 px | 10–25% | Depth layers, distant swarm, star field rules |
| **Annotation** | 1 px + small type | 50–80% | Brackets, ticks, labels, bearings |
| **Fill** | face or panel | 5–15% | Optional x-ray or panel fill; never a texture |

A useful budget: for every bright hero edge, there should be five to ten quiet structure edges
and a large amount of darkness. The eye needs a hierarchy before it needs more geometry.

### 2.3 Camera taxonomy

The collection is organised around six camera behaviours. This is the main defence against
making twenty Trench Runs.

| Camera | Behaviour | Speed guide | Modes |
|---|---|---|---|
| **Orbit** | Camera arcs a few degrees around a fixed subject | 2–8° over 120–300 s | Stellar Engine, Planet Cracker, Solar Ring, Accelerator Ring, Derelict, AI Core, Gravitational Wave Triangle, Magnetosphere |
| **Survey** | Camera glides laterally past a wide field | 0.5–2 px/s | Dyson Swarm, Mirror Array, Von Neumann Swarm, Aerostat |
| **Track** | Camera follows a moving car, hull or structure | 1–4 px/s | Space Elevator, Generation Ship, Shipyard |
| **Ride** | Camera moves through the structure from a first-person viewpoint | 3–10 px/s | Asteroid Foundry, Neutrino Lattice |
| **Follow** | Camera trails a moving object | 4–8 px/s | Ramjet |
| **Scan / descent** | Camera holds or descends while the subject is interrogated | 1–3 px/s | Artifact Scan, Cryovolcano |

The ride and follow modes are the closest to Trench Run. They should be the minority. The
collection needs the composure of an orbit as much as the momentum of a ride.

### 2.4 Motion envelope

| Element | Typical | Ceiling at 1280 px wide | Notes |
|---|---:|---:|---|
| Camera orbit | 2–8° total | 15° total | A slow arc, not a turntable |
| Camera ride / follow | 3–8 px/s | 12 px/s | Fast enough to read, slow enough to stay calm |
| Object rotation | 0.2–2°/s | 4°/s | Large structures turn slower |
| Swarm / debris drift | 0.2–1 px/s | 2 px/s | Individual pieces can move faster |
| Pulse along a line | 40–100 px/s | 160 px/s | Small area; the line carries it |
| Dust / particles | 10–40 px/s | 60 px/s | Sparse; never the subject |
| Transit / occlusion | 15–30 s | 8 s | A planet or collector crossing the star |
| Notable event | 1 per 15–60 s | 1 per 8 s | One event at a time |

No strobing, no full-frame flashes, no rapid cuts. A pulse is allowed to be bright because it
is small. A whole screen is not.

### 2.5 Composition for the strip

- **One subject, one guide, one light.** The subject can be a star, a hull, a ring, a lattice or
  a tether. The guide is an orbit, a scan plane, a construction line or a beam. The light is
  the one warm or bright element that gives the palette a centre.
- **Compose in horizontal bands.** The 1280×400 wall is 3.2:1. A centred stack of objects
  wastes the sides. Put the subject off-centre and let the guide lines run.
- **Keep the lower-left 80×32 px clear** for the controller's mode number.
- **Keep the top corners quiet** for a title and one telemetry line.
- **Use three depth layers.** Near hero, middle structure, far drift. If everything is at the
  same distance, the wireframe flattens.
- **Portrait is a re-composition, not a crop.** Stack the subject above the guide; let the
  tether, ring or lattice run vertically. Do not letterbox the strip.

### 2.6 HUD

The existing wireframe modes have a restrained console language: a title, a coordinate or
telemetry block, a small reticle, and a footer. Keep that, but do not let it become the subject.

- Default `hud: "minimal"`: title, one telemetry block, one status line.
- `hud: "off"` must still leave a complete scene.
- No nested cards, no bar charts, no fake dashboards. The console modes already own that.
- Labels may be anchored to objects with a leader line; that is part of the drawing, not a UI.
- Use small mono type, uppercase, wide tracking. 12 px minimum at 1280×400.

### 2.7 Palettes

The existing vector palettes are a good starting point. Each mode should expose a `palette`
choice with two or three variants; a variant changes the role colours, not the geometry.

| Palette | Background | Structure | Hero | Accent | Glow |
|---|---|---|---|---|---|
| **vector_blue** | `#020814` | `#2E6FA3` | `#D8F2FF` | `#5BD6E8` | `#8FE8FF` |
| **phosphor** | `#030A06` | `#2E7D5B` | `#D9FFE8` | `#69F0AE` | `#A8FFD0` |
| **magenta** | `#0A0410` | `#7A3E9E` | `#FFE6FF` | `#FF5BD6` | `#FF9BEA` |
| **amber** | `#0C0704` | `#8A5A2B` | `#FFE8C7` | `#FFB45B` | `#FFD08A` |
| **ice** | `#03070C` | `#4D7F96` | `#E8FBFF` | `#9BE8FF` | `#D4F8FF` |
| **mono** | `#070707` | `#555555` | `#F2F2F2` | `#AAAAAA` | `#DDDDDD` |

Three rules:

- **Hero and structure are different values, not just different hues.** The hero should read in
  a grayscale screenshot.
- **One warm accent per scene at most.** The rest is the palette's family.
- **Bloom is a finish, not a crutch.** A scene must read with `glow_strength: 0`.

### 2.8 Performance shape

The Pi is the constraint. The existing wireframe modes draw a few thousand segments and one
half-resolution bloom pass. Stay in that country.

| Tier | Edge ceiling | Bloom | Particles | Notes |
|---|---:|---|---:|---|
| `low` | 1,500 | 8× downscale | 40 | Aliased far lines; fewer swarm instances |
| `medium` | 3,000 | 5× downscale | 100 | The default look |
| `high` | 5,000 | 4× downscale | 180 | Anti-aliased near lines; extra detail |

- Prebuild meshes and line indices. Animate transforms, not topology.
- Cache the star field, the background gradient and any static planet limb.
- Cull off-screen segments with a margin. The existing modes do; it is worth more than a
  clever optimisation.
- Use instancing for swarms and lattices: one glyph, many transforms.
- Do not lay out text per frame. Cache labels and numbers.
- `auto` quality changes detail, never camera path or subject identity.
- Target 60 fps, accept a 30 fps floor on the Pi.

### 2.9 Determinism and failure

- Every mode is a function of `(seed, elapsed time)`. Pinning `seed` reproduces a still frame;
  an unset seed gives a new scene on entry.
- Missing optional data falls back to a built-in scene and logs once.
- No network, no audio, no external textures, no new dependencies.
- A malformed lore or label file must not stop the wall.

---

## 3. The collection at a glance

The render is wireframe in every case. "Camera" uses the taxonomy in §2.3. Build size is
relative (S/M/L), not a schedule.

| # | Mode | Subject | Camera | Motion engine | Build | Wave |
|---:|---|---|---|---|:---:|:---:|
| 1 | Dyson Swarm | A star inside a civilization's collector swarm | Survey | Orbiting collectors, transits, shadow bands | M | 1 |
| 2 | Stellar Engine | A star with a planet-sized mirror | Orbit | Mirror precession, beam, dust | M | 2 |
| 3 | Orbital Mirror Array | A field of mirrors focusing light on a world | Survey | Banking mirrors, glints, converging beams | L | 3 |
| 4 | Planet Cracker | A world being dismantled by a ring of rigs | Orbit | Rotating rigs, separating crust, drifting chunks | L | 3 |
| 5 | Solar Observatory Ring | A scientific ring around a star | Orbit / track | Ring orbit, coronal loops, crossings | L | 3 |
| 6 | Space Elevator | A tether from a planet to orbit | Track / climb | Climber ascent, tether sway, planetary horizon | M | 1 |
| 7 | Orbital Shipyard | A capital hull under construction | Track / crane | Gantry arms, growing hull, sparks | M | 2 |
| 8 | Asteroid Foundry | The inside of a hollowed asteroid | Ride | Conveyors, crucibles, a shaft of sunlight | M | 2 |
| 9 | Accelerator Ring | A particle accelerator around a moon | Orbit | A pulse of light circling the ring | L | 3 |
| 10 | Generation Ship | A generation ship opened in cutaway | Track | Decks, habitat ring, tiny traffic | L | 3 |
| 11 | Derelict | A dead capital ship adrift | Orbit | Slow tumble, debris, one flickering light | M | 1 |
| 12 | Ramjet | An interstellar ramjet scooping gas | Follow | Magnetic funnel, dust streaks, wake | M | 2 |
| 13 | Von Neumann Swarm | Probes replicating across an asteroid field | Survey | Assembly, copies, laser links | L | 3 |
| 14 | Aerostat | A floating city in a gas giant | Survey / drift | Cloud bands, balloons, a storm below | M | 2 |
| 15 | Magnetosphere | A planet's field in the solar wind | Orbit | Field lines, bow shock, aurora ovals | M | 2 |
| 16 | Cryovolcano | A probe descending an ice moon's vent | Descent | Ice walls, plume, subsurface glow | M | 3 |
| 17 | Gravitational Wave Triangle | Three spacecraft and their laser links | Orbit | Triangle rotation, wave ripples | S | 1 |
| 18 | Neutrino Lattice | A cubic detector under the ice | Ride | Strings of sensors, a track of light | M | 2 |
| 19 | AI Core | A suspended neural lattice | Orbit | Pulses, memory motes, cooling rings | M | 1 |
| 20 | Artifact Scan | An impossible object under a scan plane | Scan / orbit | Sweeping slices, brackets, a pause | M | 1 |

The set deliberately varies its **scale of subject**: five star-scale projects, four orbital
structures, four ships, three planetary fields, four instruments. Most of the set is orbit or
survey; tracks, rides, follow shots and scans are the minority. That is the balance that keeps
the collection from becoming one long tunnel.

---

## 4. The twenty modes

Each card is a design sketch, not a specification. The frames are schematic, not pixel-accurate.

### I. Star-scale engineering

#### 4.1 Dyson Swarm

`dysonswarm` · survey · build M · wave 1

**Pitch.** A star surrounded by a civilization's collectors: thousands of thin polygonal sails on
nested orbits, catching the light, occasionally crossing the star and throwing a shadow band
across the swarm. The camera drifts through the outer shell; the star is the only warm thing in
the frame.

**Frame.**

```text
+------------------------------------------------------------------+
| DYSON SWARM // SHELL 4                       COLLECTORS 1.2M     |
|        .-~~~-.        o    .    o    .    o    .    o            |
|      /  STAR  \     .    o    .    o    .    o    .    o         |
|     |   ( )    |   o    .    o    .    o    .    o    .          |
|      \        /     .    o    .    o    .    o    .    o         |
|        `-...-'     o    .    o    .    o    .    o    .          |
|        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~      |
|   a foreground sail crosses the star; its shadow sweeps         |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Collectors | Nested orbits, slightly inclined | 120–300 s |
| Foreground sail | A slow drift across the camera | 0.5 px/s |
| Transits | A sail crosses the star and dims a path of light | 15–30 s |
| Shadow bands | Move outward across the swarm | follows transit |
| Star | Slow rotation and a soft corona | 120 s |
| Camera | A lateral drift through the outer shell | 0.5 px/s |

**Signature.** A foreground sail crosses the star. For a few seconds the swarm is backlit, every
line dark against the light, and a shadow band travels outward through the collectors.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `collector_count` | 900 | Displayed catalogue count; actual draw is capped by quality |
| `shells` | 3 | Nested orbit families |
| `orbit_seconds` | 180 | Base period; each shell multiplies it |
| `transit_chance` | 0.5 | Per minute; 0 disables the eclipse |
| `camera_drift` | 0.5 | px/s |
| `palette` | vector_blue | `vector_blue`, `amber`, `ice` |
| `detail` | auto | Sail subdivision and draw cap |

**Build notes.** Generate collectors once on a few inclined orbit families. Each is a simple
quad or triangular sail; draw only those inside a distance band and cull the rest. Depth-sort by
projected distance. The star is a bright disc with a faint wireframe graticule and a corona. The
shadow band can be a darker overlay on the collectors, not a lighting simulation. Cap the actual
drawn sails around 600 at medium; the "1.2M" is a fiction, not a draw count.

**Differentiation.** The Orrery in `SLOW_WORLDS_DESIGN.md` is a brass instrument with a handful
of worlds. This is a civilization-scale swarm: no instrument frame, no named planets, no
mechanical precision.

---

#### 4.2 Stellar Engine

`stellarengine` · orbit · build M · wave 2

**Pitch.** A star with a planet-sized mirror held over one hemisphere by a truss. The mirror
reflects the star's light into a beam; the star's surface is a faint grid of convection cells;
the whole engine precesses so slowly that the motion is only obvious when the beam crosses a
dust lane.

**Frame.**

```text
+------------------------------------------------------------------+
| STELLAR ENGINE // MIRROR 1                     THRUST 0.004 C     |
|          .-~~~-.         ______________________                   |
|        /  STAR  \     .-'       mirror          '-.               |
|       |   (o)    |   /   ////////////////////     \               |
|        \        /   |   ////////////////////       |  -> beam    |
|          `-...-'     \   ////////////////////     /               |
|                       '-.____________________.-'                  |
|     truss  |  |  |  |  |  |  |  |  |  |  |  |  |                 |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Mirror | A slow precession around the star | 300 s, a few degrees |
| Star surface | Convection-cell shimmer | 60 s |
| Beam | A soft cone of reflected light | follows mirror |
| Truss | Slight thermal flex | 40 s |
| Dust lane | Drifts through the beam | 0.5 px/s |
| Camera | A 3° arc around the engine | 180 s |

**Signature.** The mirror tilts a fraction of a degree; the beam sweeps across a dust lane and
lights it from the side, revealing the engine's scale for a few seconds.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `mirror_span` | 0.7 | Fraction of the star's disc covered |
| `precession_seconds` | 300 | Full mirror cycle |
| `beam_width` | 0.4 | 0 = no beam, just the mirror |
| `show_star` | true | Star disc and convection grid |
| `palette` | amber | `amber`, `vector_blue`, `mono` |
| `detail` | auto | Mirror facet count and truss detail |

**Build notes.** The star is a filled disc only if `fill` is on; by default it is a bright radial
ring and a graticule. The mirror is a shallow curved lattice of quads; the truss is a few
triangles and struts. The beam is a translucent additive cone with a soft edge. No real optics;
the read is more important than the physics.

**Differentiation.** The Dyson Swarm is many small collectors. This is one enormous engine
holding a single mirror. The visual subject is the mirror's relationship to the star, not the
swarm.

---

#### 4.3 Orbital Mirror Array

`orbitalmirrorarray` · survey · build L · wave 3

**Pitch.** A field of orbital mirrors above a planet's night side, banking to focus sunlight onto
a city. Each mirror is a thin lozenge with a bright edge; the beams converge below; the planet's
limb and the city lights sit at the bottom of the frame.

**Frame.**

```text
+------------------------------------------------------------------+
| ORBITAL MIRROR ARRAY // 47 SAILS               FOCUS 98.2%       |
|    /|    /|    /|    /|    /|    /|    /|    /|                  |
|   / |   / |   / |   / |   / |   / |   / |   / |                  |
|  /  |  /  |  /  |  /  |  /  |  /  |  /  |  /  |                  |
|  \  |  \  |  \  |  \  |  \  |  \  |  \  |  \  |                  |
|   \ |   \ |   \ |   \ |   \ |   \ |   \ |   \ |                  |
|    \|    \|    \|    \|    \|    \|    \|    \|                  |
|   ~~~~~~~~~~~~~~~ planet limb / city lights ~~~~~~~~~~~~~~~~     |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Mirrors | Bank and tilt to hold focus | 20–40 s |
| Glints | A bright point travels across each mirror | 3–6 s |
| Beams | Converge on a moving city spot | follows focus |
| Camera | A lateral glide above the array | 1 px/s |
| Planet | Slow rotation and a terminator | 180 s |
| City lights | A warm cluster below the focus | 4–8 s twinkle |

**Signature.** One mirror loses lock; its beam drifts across the planet's limb, then snaps back.
The city below flickers once and steadies.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `mirror_count` | 47 | 20–80; draw cap by quality |
| `focus` | 0.6 | Position of the focal city along the limb |
| `beam_strength` | 0.5 | 0 = mirrors only |
| `camera_drift` | 1.0 | px/s |
| `palette` | ice | `ice`, `amber`, `vector_blue` |
| `detail` | auto | Mirror facets and beam segments |

**Build notes.** Mirrors are instanced lozenges on a shallow orbital shell. Each has a small
rotation and a glint that travels along its edge. Beams are additive lines from mirror to focus;
draw them only for the nearest ring of mirrors to keep the cost down. The planet limb is a cached
arc with a few cloud strokes; city lights are small warm points. The scene is mostly negative
space above the limb.

**Differentiation.** The Slow Sail is a convoy of traveling sails. This is fixed orbital
infrastructure doing a job; the mirrors do not go anywhere, they aim.

---

#### 4.4 Planet Cracker

`planetcracker` · orbit · build L · wave 3

**Pitch.** A world is being taken apart. A ring of mining rigs orbits the equator; a lattice of
cuts glows on the surface; huge crustal plates drift away from the core; the camera orbits the
work site. There is no explosion, only extraction.

**Frame.**

```text
+------------------------------------------------------------------+
| PLANET CRACKER // SITE 12                       YIELD 4.1 GT      |
|                 .-~~~-.                                          |
|              .-'  cut  '-.         o   o   o                      |
|             /   ///////   \      o   rigs   o                     |
|            |   // planet //  |    o   o   o                       |
|             \   ///////   /                                      |
|              '-.  __  .-'         drifting chunks                 |
|                 '-.__.-'                                          |
|   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~       |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Rigs | Orbit the planet in a slow ring | 60–120 s |
| Planet | Rotates under the cut lattice | 300 s |
| Cuts | Pulse with extraction heat | 4–8 s |
| Crust plates | Drift away from the core | 0.2 px/s |
| Debris | A sparse ring of fragments | 0.3 px/s |
| Camera | A 2° orbit around the site | 180 s |

**Signature.** A crustal plate separates and the cut line goes dark; a moment later it relights
deeper in the planet, and the rigs shift to follow it.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `rig_count` | 8 | 4–16 |
| `fracture_stage` | 0.4 | 0 = intact, 1 = mostly gone |
| `chunk_drift` | 0.2 | px/s |
| `camera_orbit` | 2.0 | Degrees over the full cycle |
| `palette` | amber | `amber`, `vector_blue`, `mono` |
| `detail` | auto | Cut lattice and chunk count |

**Build notes.** The planet is a wireframe sphere or a ring-graticule disc, depending on the
camera. The cut lattice is a set of great-circle arcs and radial lines; the plates are polygon
shards whose vertices are precomputed. Rigs are small boxes with a bright working light. The
debris ring is instanced. This is a medium-heavy mode because of the shards; cache them and
animate only their transforms.

**Differentiation.** Terraform in `SLOW_WORLDS_DESIGN.md` is a world being made. This is a world
being unmade. The camera is an industrial observer, not a natural-history view.

---

#### 4.5 Solar Observatory Ring

`solarobservatory` · orbit / track · build L · wave 3

**Pitch.** A ring of scientific satellites orbits close to a star, each carrying an instrument
package and a thin sunshield. Coronal loops arc above the surface; the ring's shadow crosses the
star; the camera rides the ring for a slow pass.

**Frame.**

```text
+------------------------------------------------------------------+
| SOLAR OBSERVATORY RING // 12                   FLUX 7.4e9        |
|        .-~~~~~~~~~~~~~~~~~~~~~~~~-.                              |
|      /   ////////////////////////   \        o--o--o--o          |
|     |   ////////  STAR  //////////   |      /  ring  \            |
|      \   ////////////////////////   /      o--o--o--o            |
|        '-.______________________.-'                              |
|      ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~                 |
|   satellites in foreground; coronal loops above                   |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Ring | Orbits the star, carrying the camera | 240 s |
| Satellites | Hold formation with a slight drift | 0.5° |
| Coronal loops | Arc and reconnect | 20 s |
| Star | Rotates under the ring | 120 s |
| Ring shadow | Crosses the star's disc | 60 s |
| Camera | Tracks along the ring | 2 px/s |

**Signature.** A coronal loop reaches from the surface to the ring, passes between two
satellites, and dissolves. The ring's shadow cuts across the star at the same time.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `satellite_count` | 12 | 6–18 |
| `ring_radius` | 0.6 | Relative to the star's disc |
| `orbit_seconds` | 240 | Ring period |
| `loops` | true | Coronal arcs |
| `palette` | amber | `amber`, `ice`, `mono` |
| `detail` | auto | Loop segments and satellite detail |

**Build notes.** The star is a bright disc with a faint grid. The ring is a perspective ellipse
with satellites at intervals; each satellite is a small cross or box with a sunshield. Coronal
loops are beziers that grow from the surface and fade. The camera rides the ring, so the star
drifts slowly across the frame. Keep the loops sparse; they are the signature, not the texture.

**Differentiation.** Space Station V is a station orbiting Earth. This is an instrument ring
orbiting a star, and the star is the subject. The ring is a measurement platform, not a habitat.

---

### II. Orbital infrastructure

#### 4.6 Space Elevator

`spaceelevator` · track / climb · build M · wave 1

**Pitch.** A tether from a planet's surface to a counterweight in orbit. A climber car ascends;
the planet's limb curves below; the tether hums; the station ring at the top grows from a dot to
a structure. The camera tracks the car, so the scale is revealed by what passes.

**Frame.**

```text
+------------------------------------------------------------------+
| SPACE ELEVATOR // CAR 07                       ALT 18,400 KM     |
|   *      .        *        .        *        .        *          |
|                         [counterweight]                          |
|                              ||                                  |
|                         [station ring]                           |
|                              ||                                  |
|        [car 07]==============||==============                    |
|                              ||                                  |
|  ~~~~~~~~~~~~~~~ planet limb / clouds ~~~~~~~~~~~~~~~~~         |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Climber | Ascends the tether | 6–12 px/s |
| Tether | A slight sway and vibration | 0.2°, 12 s |
| Planet | Slow rotation below | 300 s |
| Clouds | Drift across the limb | 2 px/s |
| Station ring | Grows as the car approaches | one pass |
| Camera | Tracks the car, then holds at the station | follows |

**Signature.** The car passes through the station ring; for a moment the ring fills the frame,
then the camera settles above it and the tether's shadow falls across the planet.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `car_speed` | 10 | px/s |
| `altitude` | 18400 | Readout and starting position |
| `show_planet` | true | Limb and clouds |
| `tether_sway` | 0.2 | Degrees |
| `palette` | vector_blue | `vector_blue`, `ice`, `amber` |
| `detail` | auto | Car and station detail |

**Build notes.** The tether is a vertical line with a slight perspective; the car is a small
rectangle with a window and a running light. The planet limb is a cached arc at the bottom; the
station ring is a perspective ellipse that scales with distance. The camera is a vertical
tracking shot. No 3D engine required; a single vanishing point and a few scale cues are enough.

**Differentiation.** The existing `spaceelevatortrafficcontrol` is a console about schedules and
cars. This is the physical climb: a line, a planet, and a very long way up.

---

#### 4.7 Orbital Shipyard

`orbitalshipyard` · track / crane · build M · wave 2

**Pitch.** A skeletal gantry holds a half-built capital ship. Robotic arms weld; construction
drones move along the keel; a crane lifts a hull section; sparks drift. The camera cranes around
the berth, and the ship's silhouette grows across the scene.

**Frame.**

```text
+------------------------------------------------------------------+
| ORBITAL SHIPYARD // BERTH 3                    HULL 62%           |
|        /|                    /|                    /|             |
|       / |       ____        / |      ____         / |             |
|      /  |      /    \      /  |     /    \       /  |             |
|     /   |=====|      |====/   |====|      |=====/   |             |
|    /    |     | hull |   /    |    | hull |    /    |             |
|   /_____|_____|______|__/_____|____|______|___/_____|             |
|        gantry  arms  drones  sparks  gantry                        |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Camera | A slow crane around the berth | 0.5 px/s |
| Hull | Grows in stages as sections lock | one stage / 60 s |
| Gantry arms | Weld and retract | 10–20 s |
| Drones | Move along the keel | 2–5 px/s |
| Crane | Lifts a section into place | 1 event / 45 s |
| Sparks | Drift and fade | 1–3 s |

**Signature.** The keel locks into place. The gantry lights run from red to white along the
spine, and the hull's outline becomes one continuous line for the first time.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `hull_stage` | 0.62 | 0–1; where construction starts |
| `arm_count` | 6 | 2–10 |
| `camera_crane` | 0.5 | px/s |
| `sparks` | true | Weld particles |
| `palette` | amber | `amber`, `vector_blue`, `mono` |
| `detail` | auto | Gantry and drone detail |

**Build notes.** The hull is a box lattice with a keel, ribs and a partial skin; draw only the
edges that exist at the current stage. The gantry is a truss of triangles around it. Arms are
segmented lines with a small bright tip. Drones are dots with a short trail. Sparks are tiny
additive points. Stage changes can be discrete; the camera sells the scale.

**Differentiation.** This is not a finished station. It is a construction site: the subject is
the process, the scaffolding, and the half-built silhouette.

---

#### 4.8 Asteroid Foundry

`asteroidfoundry` · ride · build M · wave 2

**Pitch.** The inside of a hollowed asteroid: a cylindrical cavern, a refinery, crucibles,
conveyors, and a shaft of sunlight from an entry mirror. The camera glides along the cavern,
past the machinery, toward the far end where the ore is flowing.

**Frame.**

```text
+------------------------------------------------------------------+
| ASTEROID FOUNDRY // SHAFT 2                    ORE 18,220 T       |
|  \                                                              / |
|   \    ////////  cavern  ////////    ////////                 /  |
|    \  |  crucible  |  conveyor  |  |  smelter  |             /   |
|     \ |   (o)      |===========|  |   (o)     |            /    |
|      \|____________|___________|__|___________|           /     |
|       \     ore flow  ~~~~~~~~~~~~~~~~~~~~~~~~~~         /       |
|        \________________________________________________/        |
|              a shaft of sunlight from the entry mirror            |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Camera | Glides along the cavern axis | 4 px/s |
| Conveyor | Ore moves toward the smelter | 10–20 px/s |
| Crucibles | Pulse with heat | 4–8 s |
| Mirror shaft | A bright cone from the entry | 0.5 px/s |
| Dust | Motel in the light | 1–3 px/s |
| Cavern rings | Pass the camera | 4 s |

**Signature.** The camera reaches a fresh vein; the cavern lights shift from cold blue to amber,
and the conveyor speeds up as the ore starts to move.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `cavern_length` | 900 | World units; camera loops |
| `ore_rate` | 0.5 | Conveyor density |
| `camera_speed` | 4.0 | px/s |
| `mirror_shaft` | true | Sunlight cone |
| `palette` | amber | `amber`, `phosphor`, `mono` |
| `detail` | auto | Ring spacing and machine detail |

**Build notes.** The cavern is a series of ellipse rings receding to a vanishing point; the
camera moves through them, so the rings scale and pass. Machinery is simple boxes and gantries
placed along the walls. The conveyor is a dashed line with small ore polygons. The mirror shaft
is a translucent cone from the top. This is a ride mode, so the tunnel rhythm matters more than
the individual machines.

**Differentiation.** Trench Run is a surface canyon under open sky. This is an interior
industrial space with a ceiling, a mirror, and a destination.

---

#### 4.9 Accelerator Ring

`acceleratorring` · orbit · build L · wave 3

**Pitch.** A particle accelerator encircles a moon. Detector halls sit at intervals on the ring;
a pulse of light travels around it; the camera holds a slow orbit, so the ring reads as a
clock. The moon hangs inside the ring, lit from one side.

**Frame.**

```text
+------------------------------------------------------------------+
| ACCELERATOR RING // 48 KM                     BEAM 1.2 TEV       |
|          .-~~~~~~~~~~~~~~~~~~~~~~~~-.                             |
|       .-'     o        o        o     '-.                         |
|      /    o       ________       o        \                       |
|     |    o       /  moon  \       o        |                      |
|      \    o       \______/       o        /                       |
|       '-.     o        o        o     .-'                         |
|          '-.______________________.-'                             |
|   pulse ->  o=====o=====o=====o=====o=====o                       |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Pulse | Travels around the ring | 16–24 s |
| Camera | A slow orbit around the ring | 2° / 240 s |
| Detector halls | Light up in sequence as the pulse passes | 0.5 s each |
| Ring | A slow precession | 300 s |
| Moon | Rotates inside the ring | 240 s |
| Stars | Distant and static | — |

**Signature.** The pulse passes a detector hall and the hall's ring lights up from the inside,
one segment at a time, then goes dark as the pulse moves on.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `ring_radius` | 0.7 | Relative to the frame |
| `pulse_speed` | 1.0 | Multiplier on the 18 s lap |
| `detector_count` | 12 | 4–24 |
| `camera_orbit` | 2.0 | Degrees over the full cycle |
| `palette` | vector_blue | `vector_blue`, `phosphor`, `amber` |
| `detail` | auto | Ring segments and hall detail |

**Build notes.** The ring is an ellipse in perspective; the pulse is a short bright segment
that moves along it, leaving a fading trail. Detector halls are small boxes with a ring glyph.
The moon is a wireframe disc or sphere. The camera holds a slow orbit around the ellipse; the
pulse is the only fast element in the frame, and it is small.

**Differentiation.** Penrose Tiling is a geometric pattern. This is a physical instrument with a
traveling event and a clear direction of travel.

---

### III. Ships and voyages

#### 4.10 Generation Ship

`generationship` · track · build L · wave 3

**Pitch.** A generation ship opened in cutaway: decks, a habitat ring, forests, fields, water
tanks, cryo bays, and a drive section. Tiny lights and transport dots move through the section.
The camera tracks along the hull from stern to bow.

**Frame.**

```text
+------------------------------------------------------------------+
| GENERATION SHIP // ARK 9                     POP 12,400          |
|   ____________________________________________________________    |
|  | deck 1 | forest | fields | habitat ring | cryo | engine |   |  |
|  | deck 2 | city   | water  | habitat ring | cargo| fuel   |   |  |
|  | deck 3 | farms  | park   | habitat ring | hang | drive  |   |  |
|  |________|________|________|______________|______|________|   |  |
|      cutaway / decks / tiny lights / camera tracks along           |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Camera | Tracks along the hull, stern to bow | 1 px/s |
| Habitat ring | Rotates inside its bay | 120 s |
| Deck lights | Warm points, a few changing | 3–8 s |
| Transport dots | Move along deck corridors | 2–5 px/s |
| Bay door | Opens as the camera passes | 1 event / 60 s |
| Ship | A very slow pitch | 0.05° |

**Signature.** The camera reaches the bow and the ship's name resolves in hull lights, one
letter at a time, then fades back to structure.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `deck_count` | 3 | 2–5 |
| `camera_speed` | 1.0 | px/s |
| `ring_rotation` | 120 | Seconds per habitat-ring rotation |
| `population_lights` | true | Tiny deck lights and traffic |
| `palette` | ice | `ice`, `amber`, `mono` |
| `detail` | auto | Deck modules and light count |

**Build notes.** The ship is a long hull outline with deck lines and module boxes. The cutaway
is a panel of darker fill behind the deck lines; no texture. The habitat ring is an ellipse
with radial spokes. Transport dots are small points moving along cached polylines. The camera
track is a horizontal scroll; the ship's scale is carried by the repeated modules and the tiny
lights.

**Differentiation.** Cyberspace is a city seen from outside. This is a city seen in section,
inside a ship, with no ground and no sky.

---

#### 4.11 Derelict

`derelict` · orbit · build M · wave 1

**Pitch.** A dead capital ship adrift in the dark. Its spine is broken, one hull section is torn
open, debris turns slowly around it, and a single window flickers. There is no crew, no signal,
and no explanation. The camera drifts around the wreck.

**Frame.**

```text
+------------------------------------------------------------------+
| DERELICT // UNKNOWN                            SIGNAL  NONE       |
|            *          .         *          .                     |
|                ____________________                              |
|        _______/   broken spine     \____________                 |
|       /  hull  \__  //////  //////  \  torn     \                |
|      |   o       \__________________/    o       |               |
|       \       debris   *   *   *   debris       /                |
|        '-.____________________________________.-'                |
|   one window flickers; the rest are dark                          |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Wreck | A slow tumble | 0.05°/s |
| Camera | Drifts around the hull | 0.5 px/s |
| Debris | Turns and drifts | 0.3 px/s |
| Flickering window | A weak, irregular light | 3–7 s |
| Hull gas | A faint vent plume | 1 event / 60 s |
| Stars | Distant and uncaring | — |

**Signature.** The flickering window goes dark just as the camera passes it. A piece of debris
drifts through the gap where the hull is torn, and the ship keeps turning.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `hull_damage` | 0.6 | 0 = intact, 1 = mostly gone |
| `debris` | true | Debris cloud |
| `flicker` | true | The one live window |
| `camera_drift` | 0.5 | px/s |
| `palette` | mono | `mono`, `vector_blue`, `amber` |
| `detail` | auto | Hull and debris detail |

**Build notes.** The hull is a set of box sections with a broken spine; the tear is an open
polygon with jagged edges. Debris is instanced shards on slow orbits. The flicker is a single
small surface with an irregular alpha. This is a quiet mode: resist the urge to add a monster,
a signal, or a flash. The emptiness is the point.

**Differentiation.** Space Station V is pristine, symmetrical and alive. This is asymmetrical,
dead, and drifting. The camera is an observer, not a survivor.

---

#### 4.12 Ramjet

`ramjet` · follow · build M · wave 2

**Pitch.** An interstellar ramjet under power. A magnetic scoop opens in front of the ship like a
wireframe funnel; interstellar gas and dust streak into it; a bright core burns at the throat; a
long wake trails behind. The camera follows from just behind and to one side.

**Frame.**

```text
+------------------------------------------------------------------+
| RAMJET // ISV-4                               V 0.12 C           |
|    dust ->   \                    /                               |
|               \    ~~~~~~~~~~~~  /           wake ->             |
|     *          \  /  magnetic   \/                                |
|                 \/    scoop      /\        ~~~~~~~~~~~~~          |
|                 /\    core      /  \       ~~~~~~~~~~~~~         |
|                /  \____________/    \                             |
|   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~       |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Ship | Holds attitude with a slight yaw | 0.5° |
| Scoop | A magnetic funnel of rings, pulsing | 6 s |
| Dust | Streaks into the scoop | 20–40 px/s |
| Core | Brightens as it ingests | 4–8 s |
| Wake | Long, fading lines behind the ship | 2–5 s |
| Camera | Follows behind and to one side | 5 px/s |

**Signature.** The scoop ingests a dense dust clump; the core brightens, the wake lengthens, and
the ship's outline sharpens for a moment against the glare.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `ship_speed` | 0.12 | Readout only; motion is visual |
| `scoop_size` | 1.0 | Funnel radius |
| `dust_density` | 0.6 | 0 = clean space |
| `camera_offset` | 0.3 | Side offset |
| `palette` | vector_blue | `vector_blue`, `amber`, `phosphor` |
| `detail` | auto | Scoop rings and dust count |

**Build notes.** The scoop is a series of ellipse rings receding into the throat, with a few
radial field lines. The ship is a small hull inside the funnel. Dust is a particle stream that
converges toward the throat; the wake is a set of long lines that fade behind. The camera
follows a smoothed offset, so the ship stays in frame without feeling glued.

**Differentiation.** The Slow Sail is a convoy under light pressure, moving slowly and silently.
This is an active engine with a visible intake, a core, and a wake. It is the only new mode
about velocity.

---

#### 4.13 Von Neumann Swarm

`vonneumannswarm` · survey · build L · wave 3

**Pitch.** A seed probe sits on an asteroid, surrounded by parts. It is building copies of
itself: a lattice of frames unfolds, a new probe lights up, and the swarm grows. Laser links
connect the units. The camera observes from a safe distance as the population count climbs.

**Frame.**

```text
+------------------------------------------------------------------+
| VON NEUMANN SWARM // NODE 7                    UNITS 128          |
|         o        o        o        o        o                    |
|           \      |      /          \      /                       |
|       o----[seed]----o----[copy]----o----o                       |
|           /      |      \          /      \                       |
|         o        o        o        o        o                    |
|   ~~~~ asteroid ~~~~~  parts ~~~~~  assembly ~~~~~               |
|   a new probe unfolds from a lattice of parts                     |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Seed | Holds position on the asteroid | — |
| Copies | Unfold from parts in sequence | 1 / 60 s |
| Swarm | Orbits on a loose lattice | 40–80 s |
| Laser links | Flicker between nearest units | 2–4 s |
| Parts | Drift into the assembly frame | 1–3 px/s |
| Camera | A slow survey drift | 0.5 px/s |

**Signature.** A new probe's frame unfolds; its first light comes on; the unit count increments
and the laser links redraw to include it.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `swarm_count` | 128 | Catalogue count; draw cap by quality |
| `replication_rate` | 0.5 | New units per minute |
| `link_lasers` | true | Nearest-neighbour links |
| `camera_drift` | 0.5 | px/s |
| `palette` | phosphor | `phosphor`, `vector_blue`, `amber` |
| `detail` | auto | Unit detail and link density |

**Build notes.** Each probe is a small glyph: a frame, a sensor head, and a thin solar panel.
Draw only the nearest units at full detail; farther units are simplified. The assembly is a
short scripted unfold: parts move along cached paths and snap into place. Laser links are lines
between nearest neighbours, culled when too long. The asteroid is a wireframe rock.

**Differentiation.** The Slow Sail is a convoy of crewed ships. This is a self-replicating
machine ecology, with no people and no destination.

---

### IV. Worlds and fields

#### 4.14 Aerostat

`aerostat` · survey / drift · build M · wave 2

**Pitch.** A floating city in a gas giant's cloud bands. The city hangs from balloons and a
platform; cloud layers drift past; a storm churns below; lightning flickers deep in the gas.
The camera drifts alongside at the same altitude, so the city seems to hang still while the
atmosphere moves.

**Frame.**

```text
+------------------------------------------------------------------+
| AEROSTAT // CLOUD CITY 4                       ALT 62 KM          |
|   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~     |
|     ~~~~~ cloud band ~~~~~  ~~~~~ cloud band ~~~~~              |
|          ____                                                      |
|         /    \   balloons   /\   /\   /\                          |
|        | city |~~~/  \~~~/  \~~~/  \~~~/  \                       |
|         \____/   platform   |  |   |  |   |  |                    |
|   ~~~~~~~~~~~~~ storm below ~~~~~~~~~~~~~~~~~~~~~~               |
|   lightning flickers deep in the clouds                           |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Camera | Drifts with the city | 0.5 px/s |
| Cloud bands | Two layers, opposite directions | 2 / 4 px/s |
| Balloons | A slow bob and sway | 6 s |
| Storm | Churns below; lightning | 12 s |
| City lights | Warm windows and beacons | 3–7 s |
| Shuttle | Crosses between platforms | 1 event / 45 s |

**Signature.** The city descends a few hundred metres to avoid a storm; the cloud layer rises
past the camera and the horizon disappears for a moment.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `altitude` | 62 | Readout and starting position |
| `city_size` | 1.0 | Scale of the platform |
| `storm` | true | Churning cloud layer and lightning |
| `cloud_speed` | 1.0 | Multiplier |
| `palette` | amber | `amber`, `ice`, `phosphor` |
| `detail` | auto | Balloon and platform detail |

**Build notes.** The clouds are contour bands of lines, not a texture; the storm is a darker,
denser band with a few branching lightning glyphs. The city is a platform with balloons, towers
and a landing pad. The camera drift is horizontal; the cloud layers move at different speeds to
create parallax. This is a rare wireframe mode with a warm palette and a soft horizon.

**Differentiation.** Sunrise is a cartoon forest with a real sun. This is a science-fiction
aerostat in an alien atmosphere, with no ground and no trees.

---

#### 4.15 Magnetosphere

`magnetosphere` · orbit · build M · wave 2

**Pitch.** A planet's magnetic field in the solar wind. Dipole field lines arc from pole to pole;
the solar wind streams in from one side; a bow shock compresses the field; aurora ovals glow at
the poles. A satellite crosses the field lines, measuring.

**Frame.**

```text
+------------------------------------------------------------------+
| MAGNETOSPHERE // SOL 4                         WIND 620 KM/S      |
|   -> -> -> ->     ______________________                          |
|   -> -> ->      .'  field lines        '.        -> -> ->         |
|   -> -> ->     /    .-~~~-.    .-~~~-.   \       -> -> ->         |
|   -> -> ->    |    ( planet )  ( moon )   |      -> -> ->         |
|   -> -> ->     \    `-...-'    `-...-'   /       -> -> ->         |
|   -> -> ->      '.______________________.'        -> -> ->        |
|   bow shock        aurora ovals at poles        wake              |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Solar wind | Streams of short lines from the left | 10–20 px/s |
| Field lines | Pulse and drift with the wind | 8 s |
| Bow shock | A compressed arc; ripples | 12 s |
| Planet | Rotates under the field | 120 s |
| Aurora ovals | Brighten and dim at the poles | 6 s |
| Camera | A 2° orbit around the system | 180 s |
| Satellite | Crosses the field lines | 1 event / 45 s |

**Signature.** A coronal mass ejection hits the bow shock; the field lines compress, the aurora
ovals flare, and the field snaps back over a few seconds.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `wind_speed` | 1.0 | Solar-wind stream speed |
| `field_lines` | 24 | Dipole lines; 8–40 |
| `aurora` | true | Polar ovals |
| `camera_orbit` | 2.0 | Degrees |
| `palette` | phosphor | `phosphor`, `ice`, `mono` |
| `detail` | auto | Line density and wind particles |

**Build notes.** Dipole field lines are parametric curves from pole to pole; draw them with a
distance fade. The solar wind is a set of short horizontal lines with a slight angle; the bow
shock is a bright arc. The planet is a wireframe sphere with a polar grid. The aurora is a pair
of small bright ovals, not a curtain. This is a diagram with a subject, not a simulation.

**Differentiation.** Aurora Relay in `SLOW_WORLDS_DESIGN.md` is a ground station under an
atmospheric aurora. This is a planetary-scale field seen from outside, with a solar wind and a
bow shock.

---

#### 4.16 Cryovolcano

`cryovolcano` · descent · build M · wave 3

**Pitch.** A probe descends into a cryovolcano on an ice moon. The shaft walls are blue-white
ice; a plume of vapor rises past the camera; a shaft of light from the surface fades behind; at
the bottom, a subsurface ocean glows. The camera is the probe's point of view.

**Frame.**

```text
+------------------------------------------------------------------+
| CRYOVOLCANO // PROBE 2                         DEPTH 2,140 M     |
|   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~     |
|      \   ice wall   |   plume   |   ice wall   /                  |
|       \             |           |             /                   |
|        \    [probe] |           |            /                    |
|         \           |           |           /                     |
|          \          |           |          /                      |
|           \_________|___________|_________/                       |
|              subsurface ocean glow below                          |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Probe | Descends the shaft | 2 px/s |
| Ice walls | Pass upward past the camera | 4 px/s |
| Plume | Vapor particles rise | 10–20 px/s |
| Surface light | Fades with depth | continuous |
| Ocean glow | Grows from below | 60 s |
| Camera | A slight sway and roll | 0.3° |

**Signature.** The probe breaks through the ice shelf at the bottom; the ocean's bioluminescence
blooms below, and the shaft above goes dark.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `descent_speed` | 2.0 | px/s |
| `ice_detail` | 0.6 | Wall fracture density |
| `plume` | true | Vapor particles |
| `ocean_glow` | true | The light below |
| `palette` | ice | `ice`, `phosphor`, `mono` |
| `detail` | auto | Ice polygon count and plume density |

**Build notes.** The shaft is a vertical polygon tunnel with fracture lines; the camera moves
down, so the walls scroll upward. The plume is a particle layer moving against the camera. The
surface light is a gradient that fades with depth. The ocean is a soft glow at the bottom with a
few bright motes. Keep the descent slow; the horror is the depth, not a creature.

**Differentiation.** Descent in `SLOW_WORLDS_DESIGN.md` is a bathyscaphe in an ocean trench. This
is a cryovolcanic ice shaft, with a plume, ice walls, and a different palette. The two are
cousins, not duplicates.

---

### V. Instruments and minds

#### 4.17 Gravitational Wave Triangle

`gravwave` · orbit · build S · wave 1

**Pitch.** Three spacecraft in a triangle, linked by laser beams. A gravitational wave passes;
the triangle stretches by a fraction of a pixel and returns. The camera orbits slowly, so the
instrument reads as an object in space, not a diagram on paper.

**Frame.**

```text
+------------------------------------------------------------------+
| GRAVITATIONAL WAVE TRIANGLE // TRIAD            STRAIN 1e-21      |
|              o                                                    |
|             / \                                                   |
|            /   \        laser links                               |
|           /     \                                                 |
|          o-------o                                                |
|         / \     / \        ripple passes                          |
|        /   \   /   \                                              |
|   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~       |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Triangle | Rotates as a rigid instrument | 300 s |
| Laser links | Shimmer with a slight phase | 2 s |
| Wave | A ripple expands through the triangle | 20 s |
| Spacecraft | A tiny station-keeping drift | 0.2 px/s |
| Camera | A 1° orbit | 240 s |
| Stars | Static | — |

**Signature.** A ripple passes; all three laser links stretch by a fraction of a pixel and
return. The change is almost imperceptible, which is the point.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `arm_length` | 0.7 | Relative to the frame |
| `orbit_seconds` | 300 | Triangle rotation |
| `wave_events` | 0.5 | Per minute; 0 disables |
| `show_links` | true | Laser links |
| `palette` | vector_blue | `vector_blue`, `ice`, `mono` |
| `detail` | auto | Spacecraft detail |

**Build notes.** Three spacecraft glyphs at the vertices; the links are thin lines with a
bright core. The wave is a set of concentric rings centered on the triangle, drawn very faintly.
The triangle's rotation is a rigid transform. This is the cheapest mode in the set; its value is
in the restraint and the precision of the motion.

**Differentiation.** Gravity Well in `SLOW_WORLDS_DESIGN.md` is a deformed spacetime sheet.
This is an instrument built to measure a wave, with three spacecraft and laser links.

---

#### 4.18 Neutrino Lattice

`neutrinolattice` · ride · build M · wave 2

**Pitch.** A cubic detector deep under the ice: vertical strings of sensors, horizontal strings,
and a faint track of light from a neutrino interaction. The camera glides through the lattice;
the ice above is a bright ceiling; the deep ice is blue-black. Most of the time nothing happens.

**Frame.**

```text
+------------------------------------------------------------------+
| NEUTRINO LATTICE // DEEP LATTICE                  EVENT 4471         |
|   ~~~~~~~~~~~~~~~~~~~~ ice surface ~~~~~~~~~~~~~~~~~~~~~~~~      |
|     |     |     |     |     |     |     |     |                  |
|     o     o     o     o     o     o     o     o                  |
|     |     |     |     |     |     |     |     |                  |
|     o=====o=====o=====o=====o=====o=====o=====o  <- track       |
|     |     |     |     |     |     |     |     |                  |
|     o     o     o     o     o     o     o     o                  |
|   ~~~~~~~~~~~~~~ deep ice / blue light ~~~~~~~~~~~~~~~~~~       |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Camera | Glides through the lattice | 2 px/s |
| Sensor strings | Pass the camera; dots pulse | 4 s |
| Track | A diagonal line of lit sensors | 1 event / 60–120 s |
| Ice layers | Horizontal bands at different depths | static |
| Deep glow | A faint blue from below | 30 s |
| Counters | Small numeric readout | continuous |

**Signature.** A neutrino track lights a diagonal line of sensors, one by one, then fades. The
lattice returns to waiting. The event is the only bright thing in the frame.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `string_count` | 8 | 4–12 |
| `sensor_spacing` | 1.0 | Vertical spacing |
| `camera_speed` | 2.0 | px/s |
| `event_rate` | 0.5 | Per minute; 0 disables |
| `palette` | ice | `ice`, `phosphor`, `mono` |
| `detail` | auto | Sensor density and track length |

**Build notes.** The lattice is a set of lines and dots; the camera moves through it. The track
is a short diagonal line of brightened sensors, not a particle simulation. The ice surface is a
bright band at the top; the deep ice is a dark gradient. This is a quiet mode: long waits, one
event, then waiting again.

**Differentiation.** `retrocomputermemoryvisualizer` is a diagram of memory. This is a physical
detector in a specific place, with ice above and a track of light.

---

#### 4.19 AI Core

`aicore` · orbit · build M · wave 1

**Pitch.** A suspended neural lattice in a dark chamber: a three-dimensional mesh of nodes and
edges, pulses traveling along the edges, memory fragments orbiting the core, and cooling rings
around it. The camera orbits slowly. The core is thinking, but not for us.

**Frame.**

```text
+------------------------------------------------------------------+
| COGNITION CORE // 9                            LOAD 63%           |
|          .-~~~~~~~~~~~~~~~~~~~~~~~~-.                             |
|       .-'     o----o----o----o        '-.                         |
|      /       / \  / \  / \  / \         \                        |
|     |       o---o----o----o---o          |                       |
|      \       \ /  \ /  \ /  \ /         /                        |
|       '-.     o----o----o----o      .-'                          |
|          '-.______________________.-'                             |
|    cooling rings / memory motes / pulse traveling an edge         |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Camera | A 3° orbit around the core | 180 s |
| Lattice | A slow internal rotation | 120 s |
| Pulses | Travel along edges | 2–4 s |
| Memory motes | Orbit the core | 20–40 s |
| Cooling rings | Expand and contract | 60 s |
| Text fragment | A line resolves and fades | 1 event / 45 s |

**Signature.** A pulse reaches a dead node; the node lights, and a memory fragment resolves into
a line of text before fading back into the lattice.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `node_count` | 128 | 64–256; draw cap by quality |
| `pulse_rate` | 1.0 | Pulses per second |
| `memory_motes` | true | Orbiting fragments |
| `camera_orbit` | 3.0 | Degrees |
| `palette` | phosphor | `phosphor`, `vector_blue`, `magenta` |
| `detail` | auto | Lattice density and text |

**Build notes.** The lattice is a 3D grid or a small random graph projected to 2D. Edges are
lines; nodes are dots. A pulse is a bright segment that travels along an edge. Memory motes are
small glyphs orbiting on ellipses. The text is cached and short. This is a "portrait" mode; the
camera does not travel, so the lattice can be prebuilt and animated by transform.

**Differentiation.** `corememorymatrix` is a retro magnetic-core memory plane. This is an
abstract AI substrate: a thinking object, not a storage diagram.

---

#### 4.20 Artifact Scan

`artifactscan` · scan / orbit · build M · wave 1

**Pitch.** An impossible object on a scanning platform. A plane of light sweeps through it; each
slice draws a contour; brackets measure it; the object rotates slowly. The geometry is not
consistent from one angle to the next. The scan pauses, then continues.

**Frame.**

```text
+------------------------------------------------------------------+
| ARTIFACT SCAN // OBJECT 7                      Slices 128 / 128   |
|        ___________________________                               |
|       /   scan frame   / / / /   \                              |
|      |   .-~~~~~~~-.  / / / /     |                             |
|      |  (  artifact ) / / / /     |     bracket                 |
|      |   `-~~~~~~~-'  / / / /     |                             |
|       \___________________________/                              |
|          platform / rings / glyphs                               |
+------------------------------------------------------------------+
```

**Camera and motion.**

| Element | Motion | Period |
|---|---|---|
| Scan plane | Sweeps through the object | 12 s |
| Slice contour | Redraws at the scan plane | continuous |
| Artifact | Rotates slowly | 120 s |
| Brackets | Tick and adjust | 2 s |
| Platform rings | Rotate in opposite directions | 40 s |
| Camera | A 1° orbit | 240 s |

**Signature.** A slice reveals an interior that is larger than the exterior. The scan pauses for
two seconds, then continues as if nothing happened.

**Parameters.**

| Key | Default | Notes |
|---|---|---|
| `artifact_seed` | unset | Pinned impossible shape |
| `scan_period` | 12 | Seconds per sweep |
| `slice_count` | 128 | Readout and contour density |
| `show_brackets` | true | Measurement annotations |
| `palette` | ice | `ice`, `amber`, `mono` |
| `detail` | auto | Contour resolution and glyphs |

**Build notes.** The artifact is a wireframe mesh with a deliberate topological inconsistency:
a hole that becomes a handle, a corner that connects to a non-adjacent edge. The scan plane is
a translucent line grid; the slice is the intersection contour, precomputed for a set of
heights. The brackets are annotation lines with cached numbers. The pause is a scripted event,
not a glitch. This is the most instrument-like of the set, and the most dependent on a good
silhouette.

**Differentiation.** Penrose Tiling is a flat geometric pattern. This is a single object being
interrogated in three dimensions, with a scan plane and measurements.

---

## 5. Build order and rotation

### 5.1 Recommended waves

**Wave 1 — prove the range (six modes).** Dyson Swarm, Space Elevator, Derelict, Gravitational
Wave Triangle, AI Core, Artifact Scan. These cover swarm, vertical track, wreck, instrument,
lattice and scan, and all are small enough to prototype with the existing projection and line
renderer. They are also the clearest test of whether the collection has a personality distinct
from Trench Run and Cyberspace.

**Wave 2 — the middle scale (seven modes).** Stellar Engine, Orbital Shipyard,
Asteroid Foundry, Ramjet, Aerostat, Magnetosphere, Neutrino Lattice. These add interior rides,
a warm atmosphere, and the first large machinery. They are likely to need an art-direction pass
before code.

**Wave 3 — the largest builds (seven modes).** Orbital Mirror Array, Planet Cracker, Solar
Observatory Ring, Accelerator Ring, Generation Ship, Von Neumann Swarm, Cryovolcano. These are
the most geometric and the most expensive; they benefit from the lessons of the first two waves.

No mode requires another. The waves are a risk order, not a dependency graph.

### 5.2 A rotation recipe

The current narrow profile already mixes wireframe and console modes. The new set should not be
dropped in as a contiguous block. A suggested 30–40 minute sequence:

1. **Opening:** Dyson Swarm → Space Elevator → Derelict
2. **Instruments:** Gravitational Wave Triangle → AI Core → Artifact Scan
3. **Industry:** Orbital Shipyard → Asteroid Foundry → Accelerator Ring
4. **Voyage:** Ramjet → Generation Ship → Von Neumann Swarm
5. **Worlds:** Aerostat → Magnetosphere → Cryovolcano

Rules:

- Alternate camera behaviour: orbit, track, ride, scan. Do not run two rides back to back.
- Alternate scale: a star-scale object, then a human-scale structure, then an instrument.
- Give the scenic modes a dwell of 90–180 seconds. Wireframe detail needs time to read.
- Keep at least one warm-palette mode in every four; the set can otherwise become uniformly
  blue.
- Do not put the two swarm modes (Dyson, Von Neumann) next to each other.

### 5.3 Profile placement

- The 1280×400 profile has limited free slots; existing slots must not be renumbered. Assign
  numbers only after the review chooses which modes to build.
- Accepted modes can be mirrored into the portrait and 16:9 profiles at their next free slots.
- A mode is not "in the collection" until it has a registry entry, at least one instance, and a
  validated profile.

---

## 6. Relationship to existing and proposed modes

The project already has a substantial wireframe and console vocabulary. These are the closest
neighbours and the distinction:

| Existing or proposed | Closest new mode | Why they do not collide |
|---|---|---|
| `cyberspace` | Generation Ship, Aerostat | Cyberspace is a city seen from above the street; these are a cutaway and a floating city |
| `trenchrun` | Asteroid Foundry | Trench Run is an open-sky surface ride; the Foundry is an interior industrial space |
| `spacestation` | Solar Observatory Ring, Derelict | One is a pristine station around Earth; the others are an instrument ring around a star and a dead hull |
| `penrosetiling` | Artifact Scan | A flat geometric pattern versus a single object being interrogated |
| `galacticnavigation`, `alienstarmapcartographer` | Gravitational Wave Triangle, Magnetosphere | Consoles/charts versus physical instruments and fields |
| `spaceelevatortrafficcontrol` | Space Elevator | A scheduling console versus the physical climb |
| `corememorymatrix` | AI Core | A retro magnetic-core memory plane versus an abstract neural substrate |
| `retrocomputermemoryvisualizer` | Neutrino Lattice | A memory diagram versus a physical detector under ice |
| `globalthreatmap`, `rbmkreactorsimulation` | Planet Cracker, Accelerator Ring | Ominous data dashboards versus physical engineering scenes |
| Slow Worlds: Orrery | Dyson Swarm | A brass instrument with a handful of worlds versus a civilization-scale swarm |
| Slow Worlds: Ringworld | Solar Observatory Ring, Accelerator Ring | A habitat ring versus an instrument ring around a star or a moon |
| Slow Worlds: Gravity Well | Gravitational Wave Triangle | A deformed spacetime sheet versus a three-spacecraft instrument |
| Slow Worlds: Slow Sail | Ramjet, Mirror Array | A light-pressure convoy versus an active ramjet and fixed orbital mirrors |
| Slow Worlds: Terraform | Planet Cracker | A world being made versus a world being unmade |
| Slow Worlds: Aurora Relay | Magnetosphere | A ground station under an aurora versus a planetary field in the solar wind |
| Slow Worlds: Descent | Cryovolcano | An ocean trench descent versus an ice-moon vent |
| Slow Worlds: Long Archive | Generation Ship | A monument of slabs versus a living ship in cutaway |

The rule is the same as before: if a concept needs a dashboard to be interesting, it belongs in
the console family, not this one.

---

## 7. Risks and open questions

### 7.1 Risks

| Risk | Mitigation |
|---|---|
| **Twenty modes become twenty tunnels** | The camera taxonomy is the guardrail. At least half the set must be orbit, survey, track or scan; rides are the minority. |
| **Swarm and lattice modes are expensive** | Cap drawn instances, use LOD, prebuild meshes, and let `auto` quality reduce counts. The catalogue number is fiction; the draw count is not. |
| **Wireframe detail turns into noise** | Enforce the line-role hierarchy. A still frame must read with bloom off. |
| **The Pi cannot hold 60 fps** | Budget by tier, cache static layers, accept a 30 fps floor for the largest modes. |
| **Sci-fi becomes generic neon** | Each mode needs a specific subject and a specific camera. The one-line "subject" column is the test. |
| **Scale is not legible** | Put a human-scale cue in every large scene: a car, a drone, a boat, a tiny light, a window. |
| **HUD creep** | Default to minimal; no nested cards, no charts. The existing console modes already own that language. |
| **Text and lore become a writing project** | Keep to one line per mode; built-in fallbacks; no copyrighted quotations. |
| **Too many large builds at once** | Start with the six wave-1 modes. Do not open twenty branches. |

### 7.2 Questions for review

1. **Camera balance.** Is the proposed mix right — most orbit/survey, with tracks, rides and
   scans as the minority? *Recommendation: keep rides in the minority; the wall needs composure
   more than momentum.*
2. **Fill policy.** Should these be line-only, or should cutaways and interiors use the existing
   `xray` / `panel` fill modes? *Recommendation: line-only default, optional x-ray for the
   Generation Ship, Foundry and Aerostat.*
3. **HUD density.** Minimal console, or no HUD at all for the portraits? *Recommendation:
   minimal for instruments and rides, off for the pure portraits (Dyson, Derelict, Artifact).*
4. **Scientific literalism.** How plausible should the labels and geometry be? *Recommendation:
   plausible silhouettes and invented readouts; no claim of simulation.*
5. **Palette range.** Five existing palettes plus mono; is one warm `amber` enough, or should
   there be a second warm family? *Recommendation: keep amber as the single warm exception; the
   blue/ice/phosphor family carries the set.*
6. **First wave.** Are the six wave-1 modes the right first bet? *Recommendation: build Dyson
   Swarm and Space Elevator first; they are the clearest statements of swarm and climb.*
7. **Names.** The titles are placeholders. Settle type keys and titles before registry work, or
   during build?

---

## 8. What this document is not

- Not twenty finished modes. It is a menu for review.
- Not a new renderer. It reuses the existing projection, line, bloom and HUD patterns.
- Not a change to the controller, registry, or profiles.
- Not a commitment to external art, textures, video, audio, network data, or new dependencies.
- Not a simulation. The read is more important than the physics.
- Not a game. No controls, goals, scores, or fail states.
- Not fantasy or horror. The register is science fiction; a wreck can be eerie, but it is not a
  horror scene.

---

## 9. Build tracker

This list is the automated builder's durable queue. The `slow-wireframe` job builds the lowest
unchecked mode, verifies it against Appendix B, and only then ticks the box — so an interrupted
run is retried rather than duplicated. Do not reorder, renumber or delete lines, and do not
reformat them: the job parses lines shaped `- [ ] N · key · ...` and appends `— done YYYY-MM-DD`
when it ticks a line. When all twenty are checked the job holds itself and waits for a new design
document.

- [x] 1 · `dysonswarm` · Dyson Swarm · survey · M · wave 1 · `modes/dyson_swarm_mode.py` · `DysonSwarmMode` — done 2026-11-01
- [x] 2 · `stellarengine` · Stellar Engine · orbit · M · wave 2 · `modes/stellar_engine_mode.py` · `StellarEngineMode` — done 2026-11-01
- [ ] 3 · `orbitalmirrorarray` · Orbital Mirror Array · survey · L · wave 3 · `modes/orbital_mirror_array_mode.py` · `OrbitalMirrorArrayMode`
- [ ] 4 · `planetcracker` · Planet Cracker · orbit · L · wave 3 · `modes/planet_cracker_mode.py` · `PlanetCrackerMode`
- [ ] 5 · `solarobservatory` · Solar Observatory Ring · orbit / track · L · wave 3 · `modes/solar_observatory_mode.py` · `SolarObservatoryMode`
- [ ] 6 · `spaceelevator` · Space Elevator · track / climb · M · wave 1 · `modes/space_elevator_mode.py` · `SpaceElevatorMode`
- [ ] 7 · `orbitalshipyard` · Orbital Shipyard · track / crane · M · wave 2 · `modes/orbital_shipyard_mode.py` · `OrbitalShipyardMode`
- [ ] 8 · `asteroidfoundry` · Asteroid Foundry · ride · M · wave 2 · `modes/asteroid_foundry_mode.py` · `AsteroidFoundryMode`
- [ ] 9 · `acceleratorring` · Accelerator Ring · orbit · L · wave 3 · `modes/accelerator_ring_mode.py` · `AcceleratorRingMode`
- [ ] 10 · `generationship` · Generation Ship · track · L · wave 3 · `modes/generation_ship_mode.py` · `GenerationShipMode`
- [ ] 11 · `derelict` · Derelict · orbit · M · wave 1 · `modes/derelict_mode.py` · `DerelictMode`
- [ ] 12 · `ramjet` · Ramjet · follow · M · wave 2 · `modes/ramjet_mode.py` · `RamjetMode`
- [ ] 13 · `vonneumannswarm` · Von Neumann Swarm · survey · L · wave 3 · `modes/von_neumann_swarm_mode.py` · `VonNeumannSwarmMode`
- [ ] 14 · `aerostat` · Aerostat · survey / drift · M · wave 2 · `modes/aerostat_mode.py` · `AerostatMode`
- [ ] 15 · `magnetosphere` · Magnetosphere · orbit · M · wave 2 · `modes/magnetosphere_mode.py` · `MagnetosphereMode`
- [ ] 16 · `cryovolcano` · Cryovolcano · descent · M · wave 3 · `modes/cryovolcano_mode.py` · `CryovolcanoMode`
- [ ] 17 · `gravwave` · Gravitational Wave Triangle · orbit · S · wave 1 · `modes/grav_wave_mode.py` · `GravWaveMode`
- [ ] 18 · `neutrinolattice` · Neutrino Lattice · ride · M · wave 2 · `modes/neutrino_lattice_mode.py` · `NeutrinoLatticeMode`
- [ ] 19 · `aicore` · AI Core · orbit · M · wave 1 · `modes/ai_core_mode.py` · `AICoreMode`
- [ ] 20 · `artifactscan` · Artifact Scan · scan / orbit · M · wave 1 · `modes/artifact_scan_mode.py` · `ArtifactScanMode`

---

## Appendix A — Common parameters

Every mode should support the same small set of common keys, in addition to its signature
parameters.

| Key | Type | Default | Notes |
|---|---|---|---|
| `seed` | integer or null | null | Unset = new scene on entry; pinned = reproducible |
| `palette` | choice | per mode | Two or three named variants |
| `hud` | choice | `minimal` | `off`, `minimal`, `full` where supported |
| `quality` | choice | `auto` | `auto`, `low`, `medium`, `high` |
| `fill` | choice | `line` | `line`, `xray`, `panel` where the subject benefits |
| `title` | text | mode name | Optional override |
| `subtitle` | text | per mode | Optional secondary line |
| `glow_strength` | number | 0.5 | 0 = no bloom; the scene must still read |
| `scanline_alpha` | number | 0–8 | Optional finish; keep it subtle |

Registry conventions for each accepted mode:

- `required`: normally empty; a mode should start with defaults.
- `optional`: the common keys plus every signature key the mode reads.
- `params`: widgets, ranges, choices and help text for the keys that benefit from tuning.
- The type key is lowercase, with no spaces or underscores.
- All defaults must produce a complete scene without a data file or external asset.

## Appendix B — Acceptance checklist

Before a mode is considered finished:

- [ ] It renders a composed still frame at 1280×400 with the mode-number area clear.
- [ ] It renders natively at 1080×1920 and 1920×1080; the composition is re-anchored, not
      stretched or cropped from the strip.
- [ ] A ten-second glance shows motion; a five-minute capture does not reveal an obvious loop.
- [ ] The camera behaviour matches its card and the taxonomy in §2.3.
- [ ] The line hierarchy is visible in a grayscale screenshot; the hero edge reads first.
- [ ] `seed` reproduces the scene exactly; `seed` unset gives a new one.
- [ ] `palette` variants change the mood without changing the layout.
- [ ] `auto` quality changes detail, not camera path or subject identity.
- [ ] Missing optional data falls back to a complete built-in scene and logs once.
- [ ] No network, no audio, no external texture is required.
- [ ] `exit()` releases surfaces and any threads; no per-frame logging.
- [ ] The registry entry lists `required`/`optional` accurately; `validate_configs.py --all`
      is green.
- [ ] The panel exposes the signature parameters with sensible widgets and ranges.
- [ ] A preview still at 1280×400 and a short motion capture are attached for review.

## Appendix C — Naming and file conventions

| Mode | Type key | Suggested file |
|---|---|---|
| Dyson Swarm | `dysonswarm` | `modes/dyson_swarm_mode.py` |
| Stellar Engine | `stellarengine` | `modes/stellar_engine_mode.py` |
| Orbital Mirror Array | `orbitalmirrorarray` | `modes/orbital_mirror_array_mode.py` |
| Planet Cracker | `planetcracker` | `modes/planet_cracker_mode.py` |
| Solar Observatory Ring | `solarobservatory` | `modes/solar_observatory_mode.py` |
| Space Elevator | `spaceelevator` | `modes/space_elevator_mode.py` |
| Orbital Shipyard | `orbitalshipyard` | `modes/orbital_shipyard_mode.py` |
| Asteroid Foundry | `asteroidfoundry` | `modes/asteroid_foundry_mode.py` |
| Accelerator Ring | `acceleratorring` | `modes/accelerator_ring_mode.py` |
| Generation Ship | `generationship` | `modes/generation_ship_mode.py` |
| Derelict | `derelict` | `modes/derelict_mode.py` |
| Ramjet | `ramjet` | `modes/ramjet_mode.py` |
| Von Neumann Swarm | `vonneumannswarm` | `modes/von_neumann_swarm_mode.py` |
| Aerostat | `aerostat` | `modes/aerostat_mode.py` |
| Magnetosphere | `magnetosphere` | `modes/magnetosphere_mode.py` |
| Cryovolcano | `cryovolcano` | `modes/cryovolcano_mode.py` |
| Gravitational Wave Triangle | `gravwave` | `modes/grav_wave_mode.py` |
| Neutrino Lattice | `neutrinolattice` | `modes/neutrino_lattice_mode.py` |
| AI Core | `aicore` | `modes/ai_core_mode.py` |
| Artifact Scan | `artifactscan` | `modes/artifact_scan_mode.py` |

Modes that grow beyond roughly 600 lines, or need a procedural mesh/scan module, should get a
package directory alongside the wrapper, following `trench_run/`, `cyberspace/` and
`space_station/`. Do not start with a package; start with one file and split when the file tells
you to.

---

*End of design.*
