#!/usr/bin/env python3
"""Encode a folder of PNG frames to MP4 with system OpenCV (not in the venv)."""
import glob
import os
import shutil
import sys

import cv2

frames_dir, out, fps = sys.argv[1], sys.argv[2], int(sys.argv[3])
files = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
if not files:
    raise SystemExit("no frames")
first = cv2.imread(files[0])
h, w = first.shape[:2]
writer = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
if not writer.isOpened():
    raise SystemExit("could not open video writer")
for f in files:
    writer.write(cv2.imread(f))
writer.release()
shutil.rmtree(frames_dir, ignore_errors=True)
print(f"encoded {len(files)} frames -> {out} ({os.path.getsize(out)} bytes)")
