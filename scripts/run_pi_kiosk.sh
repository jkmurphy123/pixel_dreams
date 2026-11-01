#!/usr/bin/env bash
# Start the Raspberry Pi kiosk: its own 1280x400 profile plus the GPIO rotary encoder.
#
# The --config pin is the isolation story. The portrait kiosk keeps using
# configs/modes_config_vert.json; this process loads configs/modes_config_narrow_horz.json,
# the narrow-horizontal wall at 1280x400. The two profiles are separate files, and the
# command-line pin means this wall cannot follow a profile switch recorded for the
# portrait one. The panel will not offer a profile switch here (a command-line pin would
# win again at the next restart), which is the right trade for a kiosk.
#
# Trench Run is slot 17 and Cyberspace Matrix is slot 18 in that profile. Start on one
# of them with, for example, --start 17.
#
# Default encoder wiring (BCM GPIO numbers, not header pin numbers):
#   A=17  B=27  button=23  LEDs=5,6,13,19,26,21,20,16
# Override any of them:
#   ./scripts/run_pi_kiosk.sh --rotary-pins 5,6 --rotary-button-pin 12
#   ./scripts/run_pi_kiosk.sh --rotary-led-pins ""     # no LED ring
#   ./scripts/run_pi_kiosk.sh --rotary-hold none       # no hold-to-reboot
#
# The panel is opt-in, exactly as on the other kiosk:
#   ./scripts/run_pi_kiosk.sh --panel-port 8090          # loopback only
#   ./scripts/run_pi_kiosk.sh --panel-port 8090 --panel-bind 0.0.0.0 --panel-open
# (the second form is readable AND writable by anyone on the LAN).
set -euo pipefail

cd "$(dirname "$0")/.."

export PYTHONUNBUFFERED=1
# No sound card on most kiosk Pis; SDL's audio probing is just noise there.
export SDL_AUDIODRIVER="${SDL_AUDIODRIVER:-dummy}"

# A desktop session exports these. If you start this from a bare console or a
# cage/labwc session, set the ones your SDL build needs before running it.
# export DISPLAY="${DISPLAY:-:0}"
# export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

exec .venv/bin/python pixel_dreams.py \
    --config configs/modes_config_narrow_horz.json \
    --input rotary \
    --start 0 \
    "$@"
