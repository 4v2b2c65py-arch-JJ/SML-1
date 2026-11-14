#!/usr/bin/env python3
"""
GMR-01 bus consumer example — attach to the file-backed frame ring.

The feed publishes each outlet frame to frames.ring via gmr01_bus:
32-byte header (seq u64, w u32, h u32, fmt 'RGB ', flags u32,
payload_bytes u32) then raw RGB. Seq PERSISTS across feed restarts —
a consumer reconnecting sees continuous numbering (gap = missed frames).

CUDA path (PyTorch):
    fr = bus.read_latest()          # seq,w,h,fmt,np_array
    cpu = torch.from_numpy(fr[4])   # uint8 HxWx3
    gpu = cpu.cuda()                # cross-device transfer point

Vulkan path: memcpy ring payload into a host-visible VkBuffer, or
wrap the file pages directly.

Run:  .venv/bin/python shm_read.py   (prints latest frame stats)
"""

import time

import gmr01_bus


def main():
    bus = gmr01_bus.FrameBus(path="frames.ring", w=640, h=480)
    last = -1
    for _ in range(5):
        fr = bus.read_latest()
        if fr and fr[0] != last:
            last = fr[0]
            seq, w, h, fmt, img = fr
            print(f"seq={seq} {w}x{h} {fmt} mean={img.mean():.1f} "
                  f"shape={img.shape}")
        time.sleep(0.4)
    bus.close()


if __name__ == "__main__":
    main()
