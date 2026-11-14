#!/usr/bin/env python3
"""
GMR-01 FX passes — PROPOSED extension.

Modular render passes for the feed OUTLET (inlet stays canonical so
/match keeps verifying coincidence):

  block_pass    — kernel block regions, styles: wire|fill|hazard
  shadow_pass   — drop shadows under movables (offset + alpha)
  shader_pass   — per-pixel shader, numpy-backed:
                  none|vignette|heat|mono|scan|noise
  illum_pass    — luminance/illumination control:
                  out = clamp(ambient + gain * in^gamma)

State lives in feed_state.json under "fx"; feedctl sets it.
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

GRID = 1000


# ------------------------------------------------------------- block pass ----

def block_pass(d: ImageDraw.ImageDraw, blocks, w, h, style="wire"):
    for b in blocks or []:
        x0, y0, z0, x1, y1, z1 = b
        px0, py0 = x0 / GRID * w, y0 / GRID * h
        px1, py1 = x1 / GRID * w, y1 / GRID * h
        if style == "fill":
            d.rectangle([px0, py0, px1, py1], fill=(30, 45, 70))
        elif style == "hazard":
            for x in range(int(px0), int(px1), 16):
                d.line([(x, py0), (x + 8, py1)], fill=(120, 90, 40))
        else:  # wire
            d.rectangle([px0, py0, px1, py1],
                        outline=(90, 140, 200), width=1)
        d.text((px0 + 2, py0 + 2), f"blk z{z0}-{z1}",
               fill=(90, 140, 200))


# ------------------------------------------------------------- shadow pass ---

def shadow_pass(img: Image, movers_px, dx=6, dy=10, alpha=110):
    """movers_px: list of (px, py, r). Draws blurred dark ellipses
    offset by (dx,dy) underneath."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for px, py, r in movers_px:
        d.ellipse([px + dx - r, py + dy - r, px + dx + r, py + dy + r],
                  fill=(0, 0, 0, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(4))
    img.paste(layer, (0, 0), layer)


# ------------------------------------------------------------- shader pass ---

def _arr(img):
    return np.asarray(img).astype(np.float32)


def _img(a):
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


def shader_pass(img: Image, name="none", params=None):
    if name in (None, "none"):
        return img
    a = _arr(img)
    h, w, _ = a.shape
    yy, xx = np.mgrid[0:h, 0:w]
    if name == "vignette":
        cx, cy = w / 2, h / 2
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (w * 0.7)
        a *= np.clip(1.15 - dist, 0.35, 1.0)[..., None]
    elif name == "heat":
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        a = np.stack([r * 1.15, g * 0.75, b * 0.55], axis=-1)
    elif name == "mono":
        lum = a.mean(axis=-1, keepdims=True)
        a = np.repeat(lum, 3, axis=-1) * 1.05
    elif name == "scan":
        mask = (yy % 4 < 2)[..., None]
        a = a * (0.75 + 0.25 * mask)
    elif name == "noise":
        rng = np.random.default_rng(1234)   # deterministic grain
        a = a + rng.normal(0, 8, a.shape)
    else:
        return img
    return _img(a)


# ------------------------------------------------------ illumination pass ----

def illum_pass(img: Image, gain=1.0, gamma=1.0, ambient=0.0):
    """Luminance control: out = clamp(ambient*255 + gain*(in/255)^gamma*255)."""
    if gain == 1.0 and gamma == 1.0 and ambient == 0.0:
        return img
    a = _arr(img) / 255.0
    a = np.clip(a, 0, 1) ** gamma * gain + ambient
    return _img(a * 255.0)


def default_fx():
    return {
        "shader": "none",
        "shadow": {"on": True, "dx": 6, "dy": 10, "alpha": 110},
        "illum": {"gain": 1.0, "gamma": 1.0, "ambient": 0.0},
        "block_style": "wire",
    }
