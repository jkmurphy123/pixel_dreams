"""Cyberspace — a neon wireframe matrix, in the spirit of Gibson's Neuromancer.

The package is split the way the mode thinks:

  * ``palette``  — the neon colour sets and the small RGB helpers.
  * ``camera``   — the route the viewpoint flies (one axis at a time) and the
                   pinhole camera that follows it.
  * ``matrix``   — the deterministic world: street lattice, towers, floating
                   constructs, traffic and landmarks.  Nothing here imports the
                   renderer, so it can be tested without a display.
  * ``render``   — projection, depth-faded line drawing and the additive glow.
  * ``hud``      — the console overlay: coordinates, axis, telemetry, feed.

The mode adapter lives in :mod:`modes.cyberspace_mode`.
"""
