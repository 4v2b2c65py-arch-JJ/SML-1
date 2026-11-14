#!/usr/bin/env python3
"""GML-01 video generation — renders the pipeline spec as a resonant
spatial stream (node glow driven by each stage's own hash), then can
file it straight into the ATLAS sorted store so it appears in the feed.

Usage:
  python3 gml_video.py [--seconds 10] [--scale 1.0] [--store]
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np

import gml_spec

ATLAS = Path("/Users/jjmarte/Documents/ATLAS")
OUT_DIR = Path(__file__).parent / "videos"

W, H = 1280, 720
FPS = 30


def _hash01(label: str, salt: str) -> float:
    h = hashlib.sha256(f"{label}|{salt}".encode()).digest()
    return int.from_bytes(h[:4], "big") / 0xFFFFFFFF


def render(seconds: float = 10.0, scale: float = 1.0,
           store: bool = False) -> dict:
    spine = gml_spec.spine()
    n = len(spine)
    frames = int(seconds * FPS)
    w, h = int(W * scale), int(H * scale)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"gml_resonance_{int(seconds)}s.mp4"
    if out.exists():
        out.unlink()

    # node slots: even horizontal spread, sine-wave vertical drift
    slots = []
    for i, label in enumerate(spine):
        x = int(w * (i + 1) / (n + 1))
        y = int(h * (0.5 + 0.28 * np.sin(i * 0.9)))
        freq = 0.4 + 1.6 * _hash01(label, "freq")
        phase = 2 * np.pi * _hash01(label, "phase")
        glow = 0.45 + 0.55 * _hash01(label, "glow")
        radius = int(min(w, h) * 0.035 * (0.7 + 0.6 * _hash01(label, "r")))
        slots.append({"label": label, "x": x, "y": y, "freq": freq,
                      "phase": phase, "glow": glow, "radius": radius,
                      "depth": i / max(1, n - 1)})

    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"avc1"),
                             FPS, (w, h))
    if not writer.isOpened():
        raise RuntimeError(f"could not open writer for {out}")

    font = cv2.FONT_HERSHEY_SIMPLEX
    for f in range(frames):
        t = f / FPS
        img = np.zeros((h, w, 3), np.uint8)
        img[:] = (8, 6, 14)  # near-black indigo field

        # spine connectors
        pts = [(s["x"], s["y"]) for s in slots]
        for a, b in zip(pts, pts[1:]):
            cv2.line(img, a, b, (30, 24, 48), 1, cv2.LINE_AA)

        for i, s in enumerate(slots):
            pulse = 0.5 + 0.5 * np.sin(2 * np.pi * s["freq"] * t
                                       + s["phase"])
            inten = s["glow"] * pulse
            # depth colour: cyan -> violet -> magenta
            hue = int(160 + 120 * s["depth"])
            col = np.array([max(0, 255 - abs(hue - 60) * 4),
                            60 + int(140 * inten),
                            80 + int(175 * inten)], np.uint8)
            r = int(s["radius"] * (0.75 + 0.5 * pulse))
            cv2.circle(img, (s["x"], s["y"]), r, tuple(int(c) for c in col),
                       -1, cv2.LINE_AA)
            cv2.circle(img, (s["x"], s["y"]), r + 6, (20, 16, 34), 1,
                       cv2.LINE_AA)
            # label (truncated to fit slot spacing)
            short = s["label"] if len(s["label"]) <= 22 else s["label"][:21] + "…"
            fs = 0.42 if scale < 1.5 else 0.5
            (tw, _), _ = cv2.getTextSize(short, font, fs, 1)
            lx = max(4, min(w - tw - 4, s["x"] - tw // 2))
            ly = s["y"] + r + 22
            cv2.putText(img, short, (lx, ly), font, fs,
                        (200, 200, 220), 1, cv2.LINE_AA)

        # header stream path
        cv2.putText(img, "GML-01 :: " + gml_spec.stream_path()[:110],
                    (16, 30), font, 0.55, (120, 200, 255), 1, cv2.LINE_AA)
        writer.write(img)
    writer.release()

    result = {"video": str(out), "frames": frames, "fps": FPS,
              "size": [w, h], "duration": round(frames / FPS, 2),
              "stages": n, "sha256_16": gml_spec.packet()["integrity"]["sha256"]}
    if store:
        if str(ATLAS) not in sys.path:
            sys.path.insert(0, str(ATLAS))
        import identity
        result["stored"] = identity.store_file(str(out),
                                               skip_score_gate=True)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--store", action="store_true")
    a = ap.parse_args()
    print(json.dumps(render(a.seconds, a.scale, a.store), indent=1))
