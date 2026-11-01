"""The Long Archive scene kit.

``modes.long_archive_mode`` is the mode adapter; this package owns the wall
geometry, the invented script, the cached renderer and the console.  Keeping
them separate lets the renderer be measured and the layout be tested without
starting a mode.
"""
