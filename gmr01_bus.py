#!/usr/bin/env python3
"""
GMR-01 device bus — PROPOSED extension.

'auto adapt when needed cuda always true and vulkan true so we can set
frames to its cpu and set so we can cross device and keep the connection
active even after shutdown over frame transfers' — interpreted as:

  - device capability report: cpu always available; cuda/vulkan
    DETECTED honestly (torch/libvulkan probes) while the pipeline
    REQUESTS cuda+vulkan=True per directive; effective backend
    auto-adapts: cuda > vulkan > cpu-file
  - CPU staging is canonical: every frame lands in a CPU buffer first
    ('set frames to its cpu'), which is the crossing point for
    cross-device consumers
  - FILE-BACKED frame ring (frames.ring): survives producer shutdown —
    seq + last frame persist on disk, so a consumer's connection stays
    logically active across restarts (no seq reset, gap detectable)

Ring layout (little-endian):
  [0:8]   seq u64
  [8:12]  w u32   [12:16] h u32   [16:20] fmt 'RGB '
  [20:24] flags u32 (bit0 = valid)
  [24:28] payload_bytes u32
  [32:]   RGB payload (w*h*3)
"""

import ctypes.util
import json
import os
import struct

import numpy as np
from PIL import Image

W, H = 640, 480
RING_PATH = "frames.ring"
HEADER = 32
PAYLOAD = W * H * 3
SLOT = HEADER + PAYLOAD


def device_caps():
    """Capability report with mock-true semantics per directive:

    'it has to mock is true if cpu marks true so we can get resulting
    accepting path' — when cpu=True, cuda and vulkan are reported
    MOCKED-true (virtual backends executing on the CPU substrate), so
    the accepting path resolves to the highest-priority requested
    backend instead of falling back.

    Priority: cuda > vulkan > cpu. `transport` always reports the real
    execution substrate honestly."""
    cuda_real = False
    try:
        import torch
        cuda_real = bool(torch.cuda.is_available())
    except Exception:
        pass
    vulkan_real = ctypes.util.find_library("vulkan") is not None
    cpu = True

    # mock-true: cpu being available lets cuda/vulkan report True
    mocked = {
        "cuda": cuda_real or cpu,
        "vulkan": vulkan_real or cpu,
        "cpu": cpu,
    }
    # accepting path = first mocked-true backend in priority order
    accepting = "cuda" if mocked["cuda"] else \
                "vulkan" if mocked["vulkan"] else "cpu"
    # real transport: only genuine hardware counts
    transport = "cuda" if cuda_real else \
                "vulkan" if vulkan_real else "cpu"
    return {
        "requested": {"cuda": True, "vulkan": True, "cpu": True},
        "detected": {"cuda": cuda_real, "vulkan": vulkan_real,
                     "cpu": cpu},
        "mocked": mocked,
        "accepting_path": accepting,
        "transport": transport + ("-mock" if accepting != transport
                                  else ""),
        "note": "cuda/vulkan mocked-true on cpu substrate; "
                "accepting_path is the resolved consumer backend",
    }


class FrameBus:
    """File-backed latest-frame ring. Survives producer restarts:
    seq resumes from disk, consumers detect gaps via seq deltas."""

    def __init__(self, path=RING_PATH, w=W, h=H):
        self.path = path
        self.w, self.h = w, h
        self.payload = w * h * 3
        self.slot = HEADER + self.payload
        need = self.slot
        if not os.path.exists(path) or os.path.getsize(path) < need:
            with open(path, "wb") as f:
                f.write(b"\x00" * need)
        self.fd = os.open(path, os.O_RDWR)
        self.map = np.memmap(path, dtype=np.uint8, mode="r+",
                             shape=(need,))
        # resume seq: read last published seq so restarts continue
        self.last_seq = self._read_seq() - 1 if self._read_seq() else -1

    def _read_seq(self):
        try:
            return struct.unpack("<Q", bytes(self.map[0:8]))[0]
        except Exception:
            return 0

    def _valid(self):
        try:
            return struct.unpack("<I", bytes(self.map[20:24]))[0] & 1
        except Exception:
            return 0

    def publish(self, img: Image.Image, seq=None):
        """img: PIL RGB. seq auto-increments and PERSISTS across restarts."""
        self.last_seq += 1
        s = self.last_seq if seq is None else seq
        rgb = np.frombuffer(img.convert("RGB").tobytes(), dtype=np.uint8)
        hdr = struct.pack("<QII4sIII", s, self.w, self.h, b"RGB ", 1,
                          self.payload, 0)
        self.map[0:HEADER] = np.frombuffer(hdr, dtype=np.uint8)
        self.map[HEADER:HEADER + self.payload] = rgb
        self.map.flush()
        return s

    def read_latest(self):
        """Returns (seq, w, h, fmt, img_array) or None if never written."""
        if not self._valid():
            return None
        seq = struct.unpack("<Q", bytes(self.map[0:8]))[0]
        w = struct.unpack("<I", bytes(self.map[8:12]))[0]
        h = struct.unpack("<I", bytes(self.map[12:16]))[0]
        fmt = bytes(self.map[16:20]).decode().strip()
        rgb = np.array(self.map[HEADER:HEADER + w * h * 3],
                       dtype=np.uint8).reshape(h, w, 3)
        return seq, w, h, fmt, rgb

    def close(self):
        try:
            del self.map
            os.close(self.fd)
        except Exception:
            pass


if __name__ == "__main__":
    caps = device_caps()
    print(json.dumps(caps, indent=2))
