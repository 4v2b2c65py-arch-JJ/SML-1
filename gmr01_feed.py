#!/usr/bin/env python3
"""
GMR-01 live source feed — PROPOSED extension (Stage 3/4 bridge).

'capture video by converting characters into movables … output that as
live source feed under addition acronym' — interpreted as:

  - every embedded character becomes a MOVABLE: a deterministic
    pseudo-physical particle whose position evolves in the 1000^3
    voxel space each frame (velocity derived from its content hash)
  - frames are rendered by projecting the 3D voxel space to 2D
    (x,y position; z -> shade/size), drawn with Pillow
  - output is a LIVE SOURCE FEED: multipart MJPEG over HTTP
    (http://localhost:PORT/feed.mjpeg) — playable by browsers, VLC,
    ffmpeg, OBS as a capture source
  - the feed is labeled with an additional acronym: GMRF
    (Glyph Mathematical Registry Feed) — configurable via --acronym

Usage:
  .venv/bin/python gmr01_feed.py --frames 30     # offline frame test
  .venv/bin/python gmr01_feed.py --serve         # live MJPEG feed
"""

import argparse
import hashlib
import io
import json
import math
import re
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer

from PIL import Image, ImageDraw

import constitution
import persist
import gmr01_bus
import gmr01_deep
import gmr01_fx
import gmr01_screener
import krnls

import os
import struct
import subprocess
import tempfile

GRID = gmr01_deep.GRID
W, H = 640, 480
FPS = 10
PORT = 8777
ACRONYM = "GMRF"          # 'addition acronym' labeling the live source
SCREEN_TAP = False        # --screen: inlet = user's screen via screencapture
RING_PATH = "frames.ring" # file-backed frame bus (survives shutdown)


def hash01(s: str, salt: str = "") -> float:
    h = hashlib.sha256((salt + s).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def color_of(ch: str):
    return tuple(int(hash01(ch, "rgb" + c) * 255) for c in "rgb")


class Movable:
    """A character as a moving particle in voxel space."""

    def __init__(self, ch: str, voxel):
        self.ch = ch
        self.pos = [float(v) for v in voxel]
        # deterministic velocity in [-1,1] per axis (voxels/frame)
        self.vel = [hash01(ch, f"v{i}") * 2 - 1 for i in range(3)]
        self.speed = 0.4 + 0.6 * hash01(ch, "speed")

    def step(self):
        for i in range(3):
            self.pos[i] += self.vel[i] * self.speed
            if not 0 <= self.pos[i] < GRID:      # bounce off walls
                self.pos[i] = min(max(self.pos[i], 0.0), GRID - 1.0)
                self.vel[i] *= -1


def load_movables():
    """Movables = unique chars of the signal-label charset plus decode
    content ids — the 'characters' of the registry feed."""
    chars = set("f0123456789-dcslhmwqprGZabcdefghijklmnopqrstuvwxyz")
    try:
        with open("tokens.json") as f:
            chars.update(json.load(f)["alphabet"].keys())
    except FileNotFoundError:
        pass
    place, _ = gmr01_deep.embed_characters(sorted(chars))
    return [Movable(ch, v) for v, ch in place.items()]


def render_frame(movables, frame_idx, state=None, inlet=False):
    """inlet=True renders the canonical source frame (grid + movable
    positions only — no HUD tag, no kernel blocks). The outlet adds
    overlays unless kernel sync mode makes them coincide."""
    img = Image.new("RGB", (W, H), (8, 10, 16))
    d = ImageDraw.Draw(img)
    # faint grid
    for x in range(0, W, 80):
        d.line([(x, 0), (x, H)], fill=(20, 26, 34))
    for y in range(0, H, 80):
        d.line([(0, y), (W, y)], fill=(20, 26, 34))

    # kernel-driven placer: if state has placements, chars sit at their
    # voxels (motion='hold') or drift from them (motion='drift')
    placements = (state or {}).get("placements") or {}
    hold = (state or {}).get("motion") == "hold"
    fx = (state or {}).get("fx") or {}

    # precompute screen positions for every movable (needed by shadow pass)
    movers_px = []
    for m in movables:
        if m.ch in placements:
            vx, vy, vz = placements[m.ch]
            if hold:
                m.pos = [float(vx), float(vy), float(vz)]
            else:
                # drift = deterministic orbit around the placed voxel
                t = frame_idx * 0.05 + hash01(m.ch, "phase") * 6.28
                m.pos = [vx + 12 * math.sin(t),
                         vy + 12 * math.cos(t * 0.8),
                         min(max(vz + 8 * math.sin(t * 0.6), 0), GRID - 1)]
        x, y, z = m.pos
        px = x / GRID * W
        py = y / GRID * H
        depth = z / GRID
        r = 2 + int(depth * 5)
        movers_px.append((px, py, r, m.ch, depth))

    # outlet-only passes: shadow under movables, then movables themselves
    if not inlet:
        sh = fx.get("shadow") or {}
        if sh.get("on", True):
            gmr01_fx.shadow_pass(
                img, [(px, py, r) for px, py, r, _, _ in movers_px],
                dx=sh.get("dx", 6), dy=sh.get("dy", 10),
                alpha=sh.get("alpha", 110))

    for px, py, r, ch, depth in movers_px:
        col = tuple(min(255, int(c * (0.5 + depth * 0.7)))
                    for c in color_of(ch))
        d.ellipse([px - r, py - r, px + r, py + r], fill=col)
        if r >= 4:
            d.text((px + r + 1, py - r), ch, fill=(220, 224, 230))

    # kernel block space via block pass (outlet overlay only)
    if not inlet:
        gmr01_fx.block_pass(d, (state or {}).get("blocks", []),
                            W, H, style=fx.get("block_style", "wire"))

    # shader + illumination passes (outlet only, after geometry)
    if not inlet:
        img = gmr01_fx.shader_pass(img, fx.get("shader", "none"))
        il = fx.get("illum") or {}
        img = gmr01_fx.illum_pass(img, il.get("gain", 1.0),
                                  il.get("gamma", 1.0),
                                  il.get("ambient", 0.0))
        d = ImageDraw.Draw(img)   # HUD draws on post-FX image

    # source tag: additional acronym + frame counter + source id
    # (outlet overlay only — inlet stays clean for face matching)
    if not inlet:
        src_id = (state or {}).get("source_id", ACRONYM)
        acr = (state or {}).get("acronym", ACRONYM)
        tag = (f"{acr}/{src_id} src=live frame={frame_idx} "
               f"movables={len(movables)}")
        d.rectangle([0, 0, W, 18], fill=(8, 10, 16))
        d.text((6, 4), tag, fill=(140, 220, 140))
    return img


def jpeg_bytes(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


# ------------------------------------------------------------- modes ---------

def run_frames(n):
    movables = load_movables()
    for i in range(n):
        for m in movables:
            m.step()
        img = render_frame(movables, i)
        img.save(f"feed/frame_{i:04d}.jpg", quality=85)
    print(f"wrote {n} frames to feed/ ({len(movables)} movables)")


VISUALIZER_HTML = """<!doctype html><html><head><meta charset=utf-8>
<title>GMRF Visualizer</title><style>
body{background:#0b0e14;color:#cfe;font:14px monospace;margin:0}
h1{font-size:16px;padding:8px}img{display:block;max-width:100%}
#st{padding:8px;white-space:pre-wrap}</style></head><body>
<h1>GMRF working-stream visualiser</h1>
<img src="/feed.mjpeg">
<div id=st>connecting…</div>
<script>
async function tick(){
  try{
    const s=await (await fetch('/api/status')).json();
    const q=await (await fetch('/api/quota')).json();
    const d=await (await fetch('/api/demands')).json();
    document.getElementById('st').textContent=
      'source: '+s.acronym+' / '+s.source_id+'\\n'+
      'frame: '+s.frame+'  bus_seq: '+s.bus_seq+'  fps: '+s.fps+'\\n'+
      'layout: '+s.layout+'  motion: '+s.motion+'  sync: '+s.sync+'\\n'+
      'sessions: '+s.sessions_active+'  your_demands: '+d.demands+'\\n'+
      'quota_projects: '+q.projects+'\\n'+
      'accepting_path: '+(s.bus?s.bus.devices.accepting_path:'?')+'\\n'+
      'transport: '+(s.bus?s.bus.devices.transport:'?')+'\\n'+
      'reproducible: bus seq is file-persisted across restarts';
  }catch(e){document.getElementById('st').textContent='api offline'}
}
tick();setInterval(tick,2000);
</script></body></html>"""


def serve():
    import threading
    from collections import deque
    from PIL import ImageChops

    movables = load_movables()

    # ensure kernel state exists (placer seeded from hash embedding)
    if krnls.load_state() is None:
        chars = {m.ch for m in movables}
        krnls.save_state(krnls.default_state(chars))

    # ---- canonical frame clock -------------------------------------
    # ONE producer steps movables and renders BOTH inlet (canonical:
    # grid+positions) and outlet (full overlays, or = inlet when the
    # kernel sync flag is on) per tick. Clients subscribe to either
    # stream; /match compares stored pairs face-to-face.
    clock = {
        "seq": -1,
        "inlet": None,      # jpeg bytes
        "outlet": None,     # jpeg bytes
        "cond": threading.Condition(),
        "history": deque(maxlen=60),   # (seq, inlet_jpg, outlet_jpg)
    }

    # frame screener: stores noise stats + per-frame metrics
    screener = gmr01_screener.Screener(window=60)

    # device bus: file-backed CPU staging ring — persists across
    # shutdown so frame transfers keep seq continuity for consumers
    bus = gmr01_bus.FrameBus(path=RING_PATH, w=W, h=H)

    # ---- multi-browser sessions (cookie cache + attention tensors) --
    # sid -> {"created": ts, "last_seq": int, "attention": list}
    # 'attention tensor' = the seq window this session is watching.
    # Unbounded by design ('no safe tensor limit') — expansion is the
    # session's own; the constitution caps *demands*, not attention.
    # No secrets are ever placed in session state or API responses.
    sessions = {}

    # ---- session demand store + finalized quota projects ----------
    # demands: sid -> [{id, task, modifications, verdict, ts}]
    # quota_projects: [{name, seed, budget, counterweights, ts}]
    # Proprietary content stays keyed to its session; public endpoints
    # expose aggregates/own-records only.
    DEMAND_PATH = "demand_store.json"
    QUOTA_PATH = "quota_projects.json"

    def _load_json(path, default):
        try:
            with open(path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def _save_json(path, obj):
        persist.atomic_write_json(path, obj)

    demands = _load_json(DEMAND_PATH, {})
    quota_projects = _load_json(QUOTA_PATH, [])
    # cookie cache survives restarts: sid -> {created, last_seq}
    # (attention windows are memory-only; they rebuild on activity)
    SESSION_PATH = "session_store.json"
    saved_sessions = _load_json(SESSION_PATH, {})
    for _sid, _s in saved_sessions.items():
        sessions[_sid] = {"created": _s.get("created", time.time()),
                          "last_seq": _s.get("last_seq", -1),
                          "attention": []}

    def _save_sessions():
        _save_json(SESSION_PATH, {
            sid: {"created": s["created"], "last_seq": s["last_seq"]}
            for sid, s in sessions.items()})

    def get_session(handler):
        """Return (sid, is_new). Issues sid via Set-Cookie when absent."""
        cookie = handler.headers.get("Cookie", "")
        m = re.search(r"gmr_sid=([0-9a-f]{16})", cookie)
        if m and m.group(1) in sessions:
            return m.group(1), False
        sid = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
        sessions[sid] = {"created": time.time(), "last_seq": -1,
                         "attention": []}
        _save_sessions()
        return sid, True

    def note_attention(sid):
        if sid in sessions:
            fr = bus.read_latest()
            if fr:
                sessions[sid]["last_seq"] = fr[0]
                sessions[sid]["attention"].append(fr[0])
                _save_sessions()

    def tap_screen():
        """Direct video source tap: macOS screencapture -> RGB frame."""
        fd, tmp = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        try:
            subprocess.run(["screencapture", "-x", "-t", "jpg", tmp],
                           check=True, timeout=10,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            return Image.open(tmp).convert("RGB").resize((W, H))
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def producer():
        seq = 0
        while True:
            t0 = time.time()
            kstate = krnls.load_state() or {}
            if SCREEN_TAP:
                # inlet = user's actual screen; outlet = screen + FX
                inlet_img = tap_screen()
                fx = kstate.get("fx") or gmr01_fx.default_fx()
                outlet_img = gmr01_fx.shader_pass(inlet_img,
                                                  fx.get("shader", "none"))
                il = fx.get("illum") or {}
                outlet_img = gmr01_fx.illum_pass(
                    outlet_img, il.get("gain", 1.0), il.get("gamma", 1.0),
                    il.get("ambient", 0.0))
            else:
                placements = kstate.get("placements") or {}
                for m in movables:
                    if kstate.get("motion") == "hold" or m.ch in placements:
                        pass      # position driven inside render_frame
                    else:
                        m.step()
                inlet_img = render_frame(movables, seq, kstate, inlet=True)
                if kstate.get("sync"):
                    outlet_img = inlet_img          # coincide exactly
                else:
                    outlet_img = render_frame(movables, seq, kstate,
                                              inlet=False)

            # screener: per-frame noise/motion metrics on the outlet
            screener.analyze(outlet_img, seq)

            # device bus publish: CPU staging -> file ring (seq persists)
            bus_seq = bus.publish(outlet_img)
            clock["bus_seq"] = bus_seq

            inlet_jpg = jpeg_bytes(inlet_img)
            outlet_jpg = jpeg_bytes(outlet_img)
            with clock["cond"]:
                clock["seq"] = seq
                clock["inlet"] = inlet_jpg
                clock["outlet"] = outlet_jpg
                clock["history"].append((seq, inlet_jpg, outlet_jpg))
                clock["cond"].notify_all()
            seq += 1
            # screen-tap captures are slow (~0.3s); don't busy-wait
            elapsed = time.time() - t0
            time.sleep(max(0.02, 1.0 / FPS - elapsed))

    threading.Thread(target=producer, daemon=True).start()

    def latest(which, seen):
        """Wait for a frame newer than seen[0]; return (seq, payload)."""
        with clock["cond"]:
            while clock["seq"] == seen[0]:
                clock["cond"].wait(timeout=5)
            seen[0] = clock["seq"]
            return clock["seq"], clock[which]

    def stream_mjpeg(which, wfile):
        seen = [-1]
        while True:
            seq, payload = latest(which, seen)
            try:
                wfile.write(
                    b"--GMRF\r\nContent-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(payload)).encode()
                    + b"\r\n\r\n" + payload + b"\r\n")
                wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/feed.mjpeg") or self.path == "/":
                self.send_response(200)
                self.send_header("Content-Type",
                                 "multipart/x-mixed-replace; boundary=GMRF")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                stream_mjpeg("outlet", self.wfile)
            elif self.path.startswith("/inlet.mjpeg"):
                self.send_response(200)
                self.send_header("Content-Type",
                                 "multipart/x-mixed-replace; boundary=GMRF")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                stream_mjpeg("inlet", self.wfile)
            elif self.path.startswith("/match"):
                # face-to-face: compare last N stored inlet/outlet pairs
                n = 30
                if "?last=" in self.path:
                    try:
                        n = int(self.path.split("last=")[1].split("&")[0])
                    except ValueError:
                        pass
                pairs = list(clock["history"])[-n:]
                results = []
                for seq, ij, oj in pairs:
                    a = Image.open(io.BytesIO(ij)).convert("RGB")
                    b = Image.open(io.BytesIO(oj)).convert("RGB")
                    diff = ImageChops.difference(a, b)
                    bbox = diff.getbbox()
                    # count differing pixels via histogram on extrema
                    extrema = diff.getextrema()
                    changed = any(e[1] > 0 for e in extrema)
                    results.append({"seq": seq,
                                    "identical": not changed,
                                    "diff_bbox": list(bbox) if bbox else None})
                identical = sum(1 for r in results if r["identical"])
                body = json.dumps({
                    "pairs_checked": len(results),
                    "identical_pairs": identical,
                    "all_coincide": identical == len(results) and
                                    len(results) > 0,
                    "sync_flag": bool((krnls.load_state() or {})
                                      .get("sync")),
                    "sample": results[-5:],
                }, indent=2).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path.startswith("/feed.raw"):
                # directed raw output: per frame -> 16B header + RGB
                # (for capture cards / HDMI ingest / GPU consumers)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                seen = [-1]
                last_bus = -1
                try:
                    while True:
                        # wait for a NEW bus frame (seq persists across
                        # restarts — consumers see continuous numbering)
                        while True:
                            fr = bus.read_latest()
                            if fr and fr[0] != last_bus:
                                last_bus = fr[0]
                                break
                            time.sleep(0.02)
                        seq_b, w, h, fmt, arr = fr
                        # emit bus header + raw RGB
                        self.wfile.write(struct.pack(
                            "<QII4sII", seq_b, w, h, fmt.encode().ljust(4),
                            1, w * h * 3))
                        self.wfile.write(arr.tobytes())
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
            elif self.path.startswith("/api/session"):
                sid, is_new = get_session(self)
                note_attention(sid)
                body = json.dumps({
                    "sid": sid, "is_new": is_new,
                    "sessions_active": len(sessions),
                    "last_seq": sessions[sid]["last_seq"],
                    "attention_len": len(sessions[sid]["attention"]),
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                if is_new:
                    self.send_header(
                        "Set-Cookie",
                        f"gmr_sid={sid}; Path=/; HttpOnly; SameSite=Lax")
                self.end_headers()
                self.wfile.write(body)
            elif self.path.startswith("/api/sessions"):
                sid, _ = get_session(self)
                note_attention(sid)
                body = json.dumps({
                    "your_sid": sid,
                    "sessions_active": len(sessions),
                    "your_last_seq": sessions[sid]["last_seq"],
                    # aggregate only — no per-session data exposed
                    "total_attention_events": sum(
                        len(s["attention"]) for s in sessions.values()),
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path.startswith("/api/status"):
                kstate = krnls.load_state() or {}
                body = json.dumps({
                    "acronym": kstate.get("acronym", ACRONYM),
                    "source_id": kstate.get("source_id", ACRONYM),
                    "fps": FPS, "frame": clock["seq"],
                    "layout": kstate.get("layout"),
                    "motion": kstate.get("motion"),
                    "sync": bool(kstate.get("sync")),
                    "bus_seq": clock.get("bus_seq", -1),
                    "sessions_active": len(sessions),
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path.startswith("/api/demands"):
                sid, _ = get_session(self)
                note_attention(sid)
                # own demands only — proprietary content is never
                # exposed to other sessions
                own = demands.get(sid, [])
                body = json.dumps({
                    "demands": len(own),
                    "items": [{k: d[k] for k in
                               ("id", "task", "verdict", "ts")}
                              for d in own],
                    # modifications omitted from list view
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path.startswith("/api/quota"):
                body = json.dumps({
                    "projects": len(quota_projects),
                    # names + seeds are public; proprietary task
                    # content stays session-keyed
                    "items": [{"name": p["name"], "seed": p["seed"],
                               "budget": p["budget"],
                               "counterweights": p["counterweights"],
                               "ts": p["ts"]}
                              for p in quota_projects],
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path.startswith("/visualizer"):
                # working-stream visualiser: live MJPEG + session +
                # quota state. Stream is reproducible via bus seq.
                html = VISUALIZER_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            elif self.path == "/status":
                kstate = krnls.load_state() or {}
                body = json.dumps({
                    "acronym": kstate.get("acronym", ACRONYM),
                    "source_id": kstate.get("source_id", ACRONYM),
                    "fps": FPS,
                    "movables": len(movables),
                    "frame": clock["seq"],
                    "layout": kstate.get("layout"),
                    "motion": kstate.get("motion"),
                    "sync": bool(kstate.get("sync")),
                    "blocks": len(kstate.get("blocks", [])),
                    "screen_tap": SCREEN_TAP,
                    "bus": {"path": RING_PATH,
                            "seq": clock.get("bus_seq", -1),
                            "devices": gmr01_bus.device_caps()},
                    "screener": screener.summary(),
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                payload = {}
            sid, is_new = get_session(self)
            note_attention(sid)
            send_cookie = is_new

            def reply(obj, code=200):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                if send_cookie:
                    self.send_header(
                        "Set-Cookie",
                        f"gmr_sid={sid}; Path=/; HttpOnly; SameSite=Lax")
                self.end_headers()
                self.wfile.write(body)

            if self.path.startswith("/api/demand"):
                # session demand: proprietary task + modifications,
                # constitution-evaluated for counterweights
                own = demands.setdefault(sid, [])
                demand = {
                    "id": hashlib.sha256(
                        f"{sid}:{time.time()}:{len(own)}".encode()
                    ).hexdigest()[:12],
                    "task": str(payload.get("task", ""))[:2000],
                    "modifications": payload.get("modifications", [])[:64],
                    "ts": time.time(),
                }
                verdict = constitution.evaluate(
                    demand, demand_count=len(own))
                demand["verdict"] = verdict
                own.append(demand)
                _save_json(DEMAND_PATH, demands)
                reply({"demand_id": demand["id"], "verdict": verdict,
                       "stored": True})
            elif self.path.startswith("/api/quota"):
                # finalize + store a quota project. Reproducible:
                # name+seed fully determine the project params.
                name = str(payload.get("name", ""))[:80]
                seed = int(payload.get("seed", 0))
                budget = float(payload.get("budget", 50.0))
                # aggregate counterweights across this session's
                # demands — the 'uneven' expansion the network deemed
                cw = {"quota_delta": 0.0, "attention_boost": 0.0}
                for d in demands.get(sid, []):
                    v = d.get("verdict", {})
                    for k in cw:
                        cw[k] += v.get("counterweights", {}).get(k, 0.0)
                cap = constitution.load_constitution()[
                    "tolerances"]["quota_budget_cap"]
                effective = max(0.0, min(budget + cw["quota_delta"], cap))
                project = {
                    "name": name, "seed": seed,
                    "budget": budget, "effective_budget": effective,
                    "counterweights": cw,
                    "attention_boost": cw["attention_boost"],
                    "session_demands": len(demands.get(sid, [])),
                    "ts": time.time(),
                }
                quota_projects.append(project)
                _save_json(QUOTA_PATH, quota_projects)
                reply({"project": project, "stored": True})
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *a):
            pass

    print(f"GMRF live source feed on http://localhost:{PORT} "
          f"(/feed.mjpeg outlet, /inlet.mjpeg inlet, /match face-match, "
          f"/status) — {len(movables)} movables @ {FPS}fps")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=0)
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--acronym", default=ACRONYM)
    ap.add_argument("--screen", action="store_true",
                    help="inlet = user's screen via screencapture")
    args = ap.parse_args()
    ACRONYM = args.acronym
    PORT = args.port
    SCREEN_TAP = args.screen
    if args.serve:
        serve()
    elif args.frames:
        import os
        os.makedirs("feed", exist_ok=True)
        run_frames(args.frames)
    else:
        ap.print_help()
