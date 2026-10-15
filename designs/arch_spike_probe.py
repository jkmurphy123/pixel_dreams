#!/usr/bin/env python3
"""pixel_dreams architecture spike (throwaway).

Proves / disproves the in-process architecture assumption:
  A) NiceGUI's server (uvicorn) can run in a BACKGROUND THREAD while a pygame
     60fps loop owns the MAIN thread, in one process.
  B) An HTTP request to the panel can hand a command to the render loop, which
     drains it at a frame boundary (the "refresh mode / reload config" path).
  C) The render loop's frame rate is not destroyed by the panel thread.
  D) A crash-safe config write (temp sibling + fsync + os.replace) round-trips.

Prints RESULT lines for each claim.
"""
import hashlib
import json
import os
import queue
import sys
import threading
import time
import urllib.request

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")   # no display needed for the probe
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from nicegui import app, ui

PORT = 8099
RESULTS = []


def result(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"RESULT {name}: {'PASS' if ok else 'FAIL'} {detail}", flush=True)


# ---------------------------------------------------------------- control bus
class ControlBus:
    """Thread-safe handoff: panel thread (or an HTTP route) -> render loop."""

    def __init__(self):
        self._q = queue.Queue()
        self._lock = threading.Lock()
        self._state = {"config_file": "configs/modes_config_portrait.json",
                       "refresh_count": 0, "mode_index": 2,
                       "params": {"font_size": 192}}

    def post(self, cmd):
        self._q.put(cmd)

    def drain(self, limit=8):
        out = []
        while len(out) < limit:
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                break
        return out

    def snapshot(self):
        with self._lock:
            return json.loads(json.dumps(self._state))

    def apply(self, cmd):
        """Called from the MAIN (render) thread only."""
        with self._lock:
            if cmd.get("cmd") == "refresh":
                # emulate: re-read config from disk, rebuild the mode instance
                self._state["refresh_count"] += 1
                self._state["params"] = cmd.get("params", self._state["params"])
                return f"mode {self._state['mode_index']} rebuilt with {self._state['params']}"
            if cmd.get("cmd") == "set_config":
                self._state["config_file"] = cmd["file"]
                return f"active config -> {cmd['file']}"
        return "noop"


BUS = ControlBus()
PANEL_READY = threading.Event()
PAGE_BUILDS = []


# ------------------------------------------------------------- panel (thread)
@ui.page("/")
def panel_page():
    PAGE_BUILDS.append(time.time())
    ui.label("pixel_dreams spike panel").classes("text-lg")
    snap = BUS.snapshot()
    ui.label(f"active config: {snap['config_file']}")
    ui.label(f"refresh_count: {snap['refresh_count']}")


@app.get("/api/refresh")
def api_refresh():
    """Stand-in for the panel's Save+Refresh button path."""
    BUS.post({"cmd": "refresh", "params": {"font_size": 96}})
    return {"queued": "refresh"}


@app.get("/api/config")
def api_config():
    return BUS.snapshot()


@app.get("/api/health")
def api_health():
    return {"ok": True, "main_thread": threading.current_thread() is threading.main_thread()}


def run_panel():
    ui.run(host="127.0.0.1", port=PORT, reload=False, show=False,
           title="pixel_dreams spike", uvicorn_logging_level="warning")


# ------------------------------------------------------------- render loop
def render_loop(seconds=14.0):
    pygame.init()
    screen = pygame.display.set_mode((320, 200))
    clock = pygame.time.Clock()
    frames = 0
    applied = []
    t_end = time.time() + seconds
    while time.time() < t_end:
        clock.tick(60)                      # same pacing as pixel_drift's loop
        for cmd in BUS.drain():             # <- the whole integration surface
            applied.append(BUS.apply(cmd))
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pass
        screen.fill((10, 10, 20))
        pygame.draw.rect(screen, (80, 255, 120), (10, 10, 40, frames % 60))
        pygame.display.flip()
        frames += 1
        FRAMES[0] = frames          # live counter so the probe can sample mid-run
    pygame.quit()
    return frames, applied


# ------------------------------------------------------------- probe driver
def probe():
    # wait for the panel's HTTP server to answer
    ready = False
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=1) as r:
                health = json.loads(r.read())
                ready = True
                break
        except Exception:
            time.sleep(0.25)
    result("A_panel_reachable", ready, f"health={health if ready else 'no answer'}")
    if ready:
        result("A_health_served_off_main_thread", health.get("main_thread") is False,
               f"served from main thread? {health.get('main_thread')}")
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=5) as r:
            body = r.read()
        result("A_page_served", r.status == 200 and len(PAGE_BUILDS) >= 1,
               f"HTTP {r.status}, {len(body)}B, page builder ran {len(PAGE_BUILDS)}x, "
               f"label text in HTML: {b'pixel_dreams spike panel' in body}")

    # B: HTTP -> command -> main loop
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/refresh", timeout=5) as r:
        queued = json.loads(r.read())
    time.sleep(1.0)
    snap = BUS.snapshot()
    result("B_http_command_reached_render_loop", snap["refresh_count"] >= 1,
           f"queued={queued} refresh_count={snap['refresh_count']} params={snap['params']}")

    # C: frame rate while the panel thread is live (sampled DURING the run)
    while FRAMES[0] == 0 and time.time() < time.time() + 3:
        time.sleep(0.05)
    t0, f0 = time.time(), FRAMES[0]
    time.sleep(3.0)
    fps = (FRAMES[0] - f0) / (time.time() - t0)
    result("C_framerate_maintained", fps > 45.0, f"{FRAMES[0]} frames total, live sample {fps:.1f} fps")

    # D: crash-safe config write
    target = "/tmp/pd_spike_cfg_test.json"
    payload = {"modes": {"2": {"type": "slideshow", "font_size": 96}}}
    tmp = target + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)
    with open(target) as f:
        back = json.load(f)
    h = hashlib.sha256(open(target, "rb").read()).hexdigest()[:12]
    result("D_atomic_config_write_roundtrip", back == payload and not os.path.exists(tmp),
           f"sha256={h} tmp_leftover={os.path.exists(tmp)}")

    print("--- applied in render loop:", APPLIED[0], flush=True)
    print(f"SUMMARY {sum(1 for _, ok, _ in RESULTS if ok)}/{len(RESULTS)} passed", flush=True)
    for name, ok, detail in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)
    os._exit(0)   # uvicorn is in a daemon thread; hard-exit the probe


FRAMES = [0]
APPLIED = [[]]
PROBE_SECONDS = 14.0

if __name__ == "__main__":
    panel_thread = threading.Thread(target=run_panel, daemon=True, name="panel")
    panel_thread.start()
    threading.Thread(target=probe, daemon=True, name="probe").start()
    frames, applied = render_loop(PROBE_SECONDS)     # MAIN thread = pygame, like pixel_drift
    FRAMES[0], APPLIED[0] = frames, applied
    time.sleep(2.5)
    print("MAIN LOOP RETURNED; probe did not finish in time", flush=True)
    sys.exit(1)
