#!/usr/bin/env python3
"""
GMR-01 feed shell tooling — PROPOSED extension.

CLI over the krnls kernel state (feed_state.json) so the LIVE feed
updates without restart:

  feedctl.py place <char> <x,y,z>        move one character (placer)
  feedctl.py block <x0:y0:z0:x1:y1:z1>   add a block-space region
  feedctl.py unblock                     clear all blocks
  feedctl.py layout <name>               scatter|grid|ring|slide|landing
  feedctl.py motion <drift|hold>         free physics vs fixed placer
  feedctl.py source <id> [acronym]       set source/output id
  feedctl.py status                      show kernel state summary
  feedctl.py landing <id>                write landing_<id>.html

Everything is keyed by source id — pass --source to target a specific
feed instance's state file (default feed_state.json).
"""

import argparse
import json
import sys

import krnls


def parse_voxel(s):
    parts = s.replace(":", ",").split(",")
    if len(parts) != 3:
        raise ValueError("expected x,y,z or x:y:z")
    return [int(p) for p in parts]


def parse_box(s):
    parts = s.split(":")
    if len(parts) != 6:
        raise ValueError("expected x0:y0:z0:x1:y1:z1")
    return [int(p) for p in parts]


def ensure_state():
    st = krnls.load_state()
    if st is None:
        # seed charset from a default run if feed never started
        import gmr01_deep, gmr01_feed
        chars = {m.ch for m in gmr01_feed.load_movables()}
        st = krnls.default_state(chars)
        krnls.save_state(st)
    return st


def write_landing(source_id, st):
    fn = f"landing_{source_id}.html"
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{source_id} — GMRF landing</title>
<style>body{{background:#0a0c10;color:#cfe3f5;font-family:monospace;
margin:2em}}img{{border:1px solid #285;border-radius:6px}}
code{{color:#8fd}}</style></head><body>
<h1>{st.get('acronym','GMRF')}/{source_id}</h1>
<p>layout={st.get('layout')} motion={st.get('motion')} \
blocks={len(st.get('blocks',[]))} movables={len(st.get('placements',{}))}</p>
<img src="/feed.mjpeg" width="640" height="480">
<p><small>live source feed — GMR-01 kernel state</small></p>
</body></html>"""
    with open(fn, "w") as f:
        f.write(html)
    print(f"wrote {fn}")


def main():
    ap = argparse.ArgumentParser(prog="feedctl")
    ap.add_argument("--state", default=krnls.STATE)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("place"); p.add_argument("char"); p.add_argument("voxel")
    p = sub.add_parser("block"); p.add_argument("box")
    sub.add_parser("unblock")
    p = sub.add_parser("layout"); p.add_argument("name")
    p = sub.add_parser("motion"); p.add_argument("mode", choices=["drift", "hold"])
    p = sub.add_parser("sync"); p.add_argument("mode", choices=["on", "off"])
    p = sub.add_parser("fx")
    p.add_argument("module", choices=["shader", "shadow", "illum",
                                      "blockstyle", "reset"])
    p.add_argument("args", nargs="*")
    p = sub.add_parser("speak")
    p.add_argument("what", choices=["transcript", "handoff", "status"])
    p.add_argument("--lines", type=int, default=3)
    p.add_argument("--voice")
    p.add_argument("--rate", type=int, default=200)
    p = sub.add_parser("source"); p.add_argument("id"); p.add_argument("acronym", nargs="?")
    sub.add_parser("status")
    p = sub.add_parser("landing"); p.add_argument("id")

    args = ap.parse_args()
    krnls.STATE = args.state
    st = ensure_state()

    if args.cmd == "place":
        st["placements"][args.char] = parse_voxel(args.voxel)
    elif args.cmd == "block":
        krnls.add_block(st, parse_box(args.box))
    elif args.cmd == "unblock":
        krnls.clear_blocks(st)
    elif args.cmd == "layout":
        st = krnls.apply_layout(st, args.name)
    elif args.cmd == "motion":
        st["motion"] = args.mode
    elif args.cmd == "sync":
        st["sync"] = args.mode == "on"
    elif args.cmd == "fx":
        import gmr01_fx
        fx = st.setdefault("fx", gmr01_fx.default_fx())
        a = args.args
        if args.module == "reset":
            st["fx"] = gmr01_fx.default_fx()
        elif args.module == "shader":
            if a and a[0] in ("none", "vignette", "heat", "mono",
                              "scan", "noise"):
                fx["shader"] = a[0]
            else:
                sys.exit("shader must be none|vignette|heat|mono|scan|noise")
        elif args.module == "shadow":
            if a and a[0] in ("on", "off"):
                fx["shadow"]["on"] = a[0] == "on"
            else:
                sys.exit("shadow must be on|off")
        elif args.module == "blockstyle":
            if a and a[0] in ("wire", "fill", "hazard"):
                fx["block_style"] = a[0]
            else:
                sys.exit("blockstyle must be wire|fill|hazard")
        elif args.module == "illum":
            if len(a) >= 2:
                fx["illum"] = {"gain": float(a[0]), "gamma": float(a[1]),
                               "ambient": float(a[2]) if len(a) > 2 else 0.0}
            else:
                sys.exit("illum needs <gain> <gamma> [ambient]")
    elif args.cmd == "source":
        st = krnls.set_source(st, args.id, args.acronym)
    elif args.cmd == "landing":
        krnls.save_state(st)
        write_landing(args.id, st)
        return
    elif args.cmd == "speak":
        import gmr01_voice
        if args.what == "transcript":
            ok = gmr01_voice.speak_lines("transcript.txt",
                                         n=args.lines, voice=args.voice,
                                         rate=args.rate)
        elif args.what == "handoff":
            ok = gmr01_voice.speak_handoffs(n=args.lines,
                                            voice=args.voice,
                                            rate=args.rate)
        else:
            ok = gmr01_voice.speak(
                f"source {st['source_id']} layout {st['layout']} "
                f"motion {st['motion']} blocks {len(st['blocks'])}",
                voice=args.voice, rate=args.rate)
        if not ok:
            sys.exit("speech failed (say not available?)")
        return
    elif args.cmd == "status":
        print(json.dumps({k: (len(v) if isinstance(v, (dict, list)) else v)
                          for k, v in st.items()}, indent=2))
        return

    krnls.save_state(st)
    print(f"[{st['source_id']}] {args.cmd} applied — "
          f"layout={st['layout']} motion={st['motion']} "
          f"blocks={len(st['blocks'])} placements={len(st['placements'])}")


if __name__ == "__main__":
    main()
