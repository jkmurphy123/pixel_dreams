#!/usr/bin/env bash
# Start the kiosk on the attached display, with the LAN control panel open (no token gate).
#
# This is the one place the --panel-open decision is recorded, so restarting the kiosk from this
# script can never silently re-arm the token gate the way a hand-typed command line does.
#
#   ./scripts/run_kiosk.sh                 # LAN panel on http://jetsons:8090, ungated, manual
#   ./scripts/run_kiosk.sh --auto 60       # extra flags are appended: this one cycles on a timer
#   ./scripts/run_kiosk.sh --play 12       # single mode
#
# No --auto by default: it starts on the profile's first enabled mode and stays there until someone
# presses LEFT/RIGHT or uses the panel's transport / mode list.
#
# To put the token gate back, run pixel_dreams.py yourself WITHOUT --panel-open:
#   .venv/bin/python pixel_dreams.py --panel-port 8090 --panel-bind 0.0.0.0
# A gated panel needs panel_token in secrets.json and serves 403 until you visit
# /_panel/auth?token=<panel_token> once. See deploy/README.md, "The panel over the LAN".
#
# Why a script: the gate is armed whenever the process starts without the flag, so any launch path
# that does not carry it will ask for the token again after the next restart. The token is ignored
# while --panel-open is in effect — anyone who can reach the address can also WRITE profiles.
set -euo pipefail

cd "$(dirname "$0")/.."

RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
# A graphical session's display; override by exporting DISPLAY before calling this script.
export DISPLAY="${DISPLAY:-:0}"
# This host keeps XAUTHORITY in the session's runtime dir, not ~/.Xauthority.
export XAUTHORITY="${XAUTHORITY:-$RUNTIME_DIR/gdm/Xauthority}"
# SDL keeps its audio/display sane on a Jetson with no sound card attached.
export SDL_AUDIODRIVER="${SDL_AUDIODRIVER:-dummy}"
export PYTHONUNBUFFERED=1

exec .venv/bin/python pixel_dreams.py \
    --panel-port 8090 \
    --panel-bind 0.0.0.0 \
    --start 0 \
    --panel-open \
    "$@"
