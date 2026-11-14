#!/usr/bin/env python3
"""
GMR-01 kernel (krnls) — PROPOSED extension.

'krnls os' interpreted as the kernel/core layer of the live feed:
owns feed_state.json — the shared state the feed server reads every
frame, so shell tooling can modify the placer (character positions)
and block space (voxel regions) live.

State schema:
  {
    "source_id": "GMRF",               # output/source id ('by source out id')
    "acronym":  "GMRF",
    "placements": {"a": [x,y,z], ...}, # placer: char -> voxel coord
    "blocks":    [[x0,y0,z0,x1,y1,z1], ...],  # block space regions
    "layout":    "scatter|grid|ring|slide|landing",
    "motion":    "drift|hold"          # drift = movable physics,
                                       # hold = fixed placements
  }
"""

import json
import math
import os

import gmr01_deep

GRID = gmr01_deep.GRID
STATE = "feed_state.json"

LAYOUTS = ["scatter", "grid", "ring", "slide", "landing"]


def default_state(chars):
    place, _ = gmr01_deep.embed_characters(sorted(chars))
    return {
        "source_id": "GMRF",
        "acronym": "GMRF",
        "placements": {ch: [round(v) for v in vox]
                       for vox, ch in place.items()},
        "blocks": [],
        "layout": "scatter",
        "motion": "drift",
        "sync": False,          # inlet/outlet coincidence mode
    }


def load_state():
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return None


def save_state(st):
    with open(STATE, "w") as f:
        json.dump(st, f, indent=2)


# ------------------------------------------------------------- layouts -------

def _chars(st):
    return sorted(st["placements"].keys())


def apply_layout(st, name):
    """Compute placements for a named layout over the current charset."""
    chars = _chars(st)
    n = len(chars)
    p = {}
    if name == "scatter":
        place, _ = gmr01_deep.embed_characters(chars)
        for vox, ch in place.items():
            p[ch] = [round(v) for v in vox]
    elif name == "grid":
        cols = math.ceil(math.sqrt(n))
        for i, ch in enumerate(chars):
            r, c = divmod(i, cols)
            p[ch] = [int((c + 0.5) / cols * GRID),
                     int((r + 0.5) / math.ceil(n / cols) * GRID),
                     GRID // 2]
    elif name == "ring":
        cx = cy = GRID // 2
        for i, ch in enumerate(chars):
            a = 2 * math.pi * i / max(n, 1)
            rad = GRID * 0.35
            p[ch] = [int(cx + rad * math.cos(a)),
                     int(cy + rad * math.sin(a)), GRID // 2]
    elif name == "slide":            # horizontal bands (slide rows)
        bands = 8
        per = math.ceil(n / bands)
        for i, ch in enumerate(chars):
            band = i // per
            idx = i % per
            p[ch] = [int((idx + 0.5) / max(per, 1) * GRID),
                     int((band + 0.5) / bands * GRID),
                     GRID // 2 + (band % 3 - 1) * 80]
    elif name == "landing":          # landing-page blocks: 3 columns
        cols = 3
        per = math.ceil(n / cols)
        for i, ch in enumerate(chars):
            col = i // per
            idx = i % per
            rows = per
            p[ch] = [int((col + 0.5) / cols * GRID),
                     int((idx + 0.5) / rows * GRID),
                     GRID // 3 * (1 + col % 2)]
    else:
        raise ValueError(f"unknown layout '{name}' (have {LAYOUTS})")
    st["placements"] = p
    st["layout"] = name
    return st


def add_block(st, box):
    st["blocks"].append(box)
    return st


def clear_blocks(st):
    st["blocks"] = []
    return st


def set_source(st, source_id, acronym=None):
    st["source_id"] = source_id
    if acronym:
        st["acronym"] = acronym
    return st
