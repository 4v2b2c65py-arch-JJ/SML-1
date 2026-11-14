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


def feed_style(max_videos: int = 12) -> dict:
    """Extract a style signature from the ATLAS store: dominant palette,
    mean luma, and motion tempo of the videos currently shown in the
    feed. Used as the 'shortcut' weight set — heuristic stand-in for
    neural weights (llama3.2 is text-only, no vision tower)."""
    store = ATLAS / "videos" / "store"
    vids = [p for p in store.rglob("*")
            if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")]
    vids = [v for v in vids if "rejected" not in v.parts][:max_videos]
    palette, lumas, motions = [], [], []
    for v in vids:
        cap = cv2.VideoCapture(str(v))
        if not cap.isOpened():
            continue
        total, nfr, prev = 0.0, 0, None
        while nfr < 60:
            ok, fr = cap.read()
            if not ok:
                break
            if nfr % 10 == 0:
                small = cv2.resize(fr, (64, 36))
                palette.append(cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
                               .reshape(-1, 3).mean(axis=0))
                lumas.append(float(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                                   .mean()))
                if prev is not None:
                    motions.append(float(cv2.absdiff(small, prev).mean()))
                prev = small
            nfr += 1
        cap.release()
    if not palette:
        return {"palette": [], "luma": 15.0, "motion": 5.0, "videos": 0}
    pal = np.mean(np.array(palette), axis=0)  # mean HSV
    return {"palette_hsv": pal.tolist(),
            "luma": float(np.mean(lumas)),
            "motion": float(np.mean(motions)) if motions else 5.0,
            "videos": len(vids)}


def _hsv_to_bgr(h, s, v):
    return tuple(int(c) for c in cv2.cvtColor(
        np.uint8([[[h, s, v]]]), cv2.COLOR_HSV2BGR)[0, 0])


def render(seconds: float = 10.0, scale: float = 1.0,
           store: bool = False, style: str | None = None) -> dict:
    spine = gml_spec.spine()
    n = len(spine)
    frames = int(seconds * FPS)
    w, h = int(W * scale), int(H * scale)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{style}" if style else ""
    out = OUT_DIR / f"gml_resonance_{int(seconds)}s{suffix}.mp4"
    if out.exists():
        out.unlink()

    # style hook: 'feed' matches the palette/luma/tempo of the videos
    # currently shown in the ATLAS store; version bindings act as the
    # shortcut weight set (openloop1.2 et al.)
    sty = feed_style() if style == "feed" else None
    pkt = gml_spec.packet()
    shortcut_w = len(pkt.get("dino_nametags") or {})
    tempo = 1.0
    base_hue = 160.0
    bg = (8, 6, 14)
    if sty:
        base_hue = float(sty["palette_hsv"][0])
        tempo = float(np.clip(sty["motion"] / 8.0, 0.5, 2.5))
        lv = int(np.clip(sty["luma"] * 0.45, 4, 60))
        bg = (lv // 3, lv // 4, lv // 2 + 4)

    # node slots: even horizontal spread, sine-wave vertical drift
    slots = []
    for i, label in enumerate(spine):
        x = int(w * (i + 1) / (n + 1))
        y = int(h * (0.5 + 0.28 * np.sin(i * 0.9)))
        freq = (0.4 + 1.6 * _hash01(label, "freq")) * tempo
        phase = 2 * np.pi * _hash01(label, "phase")
        glow = 0.45 + 0.55 * _hash01(label, "glow")
        # shortcut weight: dino-nametag bindings amplify node glow
        glow = min(1.0, glow * (1.0 + 0.15 * shortcut_w))
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
        img[:] = bg

        # spine connectors
        pts = [(s["x"], s["y"]) for s in slots]
        for a, b in zip(pts, pts[1:]):
            cv2.line(img, a, b, (30, 24, 48), 1, cv2.LINE_AA)

        for i, s in enumerate(slots):
            pulse = 0.5 + 0.5 * np.sin(2 * np.pi * s["freq"] * t
                                       + s["phase"])
            inten = s["glow"] * pulse
            # depth colour: feed palette hue when styled, else
            # cyan -> violet -> magenta ramp
            if sty:
                hue = int((base_hue + 40 * s["depth"]) % 180)
                sat = int(140 + 80 * inten)
                val = int(120 + 135 * inten)
                col = np.array(_hsv_to_bgr(hue, sat, val), np.uint8)
            else:
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
              "stages": n, "style": style, "feed_style": sty,
              "shortcut_weight": shortcut_w,
              "sha256_16": gml_spec.packet()["integrity"]["sha256"]}
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
    ap.add_argument("--style", default=None,
                    help="'feed' = match ATLAS store palette/luma/tempo")
    a = ap.parse_args()
    print(json.dumps(render(a.seconds, a.scale, a.store, a.style), indent=1))
