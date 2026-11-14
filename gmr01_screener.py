#!/usr/bin/env python3
"""
GMR-01 frame screener — PROPOSED extension.

'store nose lengh for its built screener' — interpreted as: a built-in
frame screener that stores noise statistics and per-frame metrics over
a rolling window ('noise length' = analysis window length; assumption
flagged in GMR-01.md Q16).

Per frame it records:
  seq, mean_luma, luma_std (noise proxy), delta_mean (motion vs prev),
  unique_colors (quantized), ts

Stores: in-memory ring (window) + append-only screener_log.jsonl.
"""

import json
import time
from collections import deque

import numpy as np
from PIL import Image


class Screener:
    def __init__(self, window=60, log_path="screener_log.jsonl"):
        self.window = window
        self.log_path = log_path
        self.ring = deque(maxlen=window)
        self.prev = None
        self._log = open(log_path, "a")

    def analyze(self, img: Image, seq: int):
        a = np.asarray(img.convert("RGB")).astype(np.float32)
        luma = a.mean(axis=-1)
        # noise proxy: std of luma high-frequency residual
        # (cheap approx: std of frame minus 3x3 box mean via shifts)
        blur = (np.roll(luma, 1, 0) + np.roll(luma, -1, 0) +
                np.roll(luma, 1, 1) + np.roll(luma, -1, 1)) / 4.0
        resid = luma - blur
        noise_std = float(resid.std())
        mean_luma = float(luma.mean())
        luma_std = float(luma.std())
        delta = (float(np.abs(luma - self.prev).mean())
                 if self.prev is not None else 0.0)
        self.prev = luma
        # quantized unique colors (upper 4 bits per channel)
        q = (a // 16).astype(np.uint8)
        colors = len(np.unique(q.reshape(-1, 3), axis=0))
        rec = {"seq": seq, "ts": round(time.time(), 3),
               "mean_luma": round(mean_luma, 2),
               "luma_std": round(luma_std, 2),
               "noise_std": round(noise_std, 2),
               "delta_mean": round(delta, 3),
               "unique_colors": int(colors)}
        self.ring.append(rec)
        self._log.write(json.dumps(rec) + "\n")
        self._log.flush()
        return rec

    def summary(self):
        if not self.ring:
            return {}
        noise = [r["noise_std"] for r in self.ring]
        delta = [r["delta_mean"] for r in self.ring]
        return {
            "window": self.window,
            "frames": len(self.ring),
            "noise_mean": round(sum(noise) / len(noise), 3),
            "noise_max": round(max(noise), 3),
            "motion_mean": round(sum(delta) / len(delta), 3),
            "last": self.ring[-1],
        }
