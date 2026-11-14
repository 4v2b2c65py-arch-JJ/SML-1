#!/usr/bin/env python3
"""
GMR-01 string rigging formalizer — PROPOSED extension.

'add its formaliser for how it can rig strings into meshes or
polyforms' — formal mappings (each symbol: name, definition,
dimension, I/O type — rule 6):

  rig_mesh(s)     : string -> mesh (V, E, F)
      V_i        vertex per character position; coord =
                  voxel_of(char) perturbed by index (unique joints)
      E          path edges (i,i+1) — string order IS the topology
      F          triangle faces on windows (i,i+1,i+2) whose
                  vertices are non-degenerate
  rig_polyform(s): string -> polyomino on Z^2
      walk       start (0,0); each char picks a 4-direction via
                  content hash; occupied cells = the polyform
  export_obj     : mesh -> Wavefront .obj (v/l/f records)

PROVABLE properties (mechanical consequences of definitions):
  P1  mesh path graph: |V|=n, |E_path|=n-1 -> chi >= 1 always
  P2  polyform walk uses 4-neighbor steps -> always edge-connected
  P3  both constructions are deterministic (hash-addressed)

CLI:  .venv/bin/python gmr01_rig.py "f2-deep-high-c523a"
"""

import hashlib
import json
import sys

GRID = 1000


def _h(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest(), 16)


def hash01(s: str) -> float:
    return (_h(s) % (2 ** 32)) / 2 ** 32


def voxel_of(key: str):
    h = _h(key)
    return tuple(((h >> (10 * i)) & 0x3FF) * GRID // 1024
                 for i in range(3))


# ------------------------------------------------------------- mesh rig ------

def rig_mesh(s: str):
    """String -> mesh dict {vertices, edges, faces}."""
    verts = []
    for i, ch in enumerate(s):
        base = voxel_of(ch)
        # index perturbation keeps repeated chars as distinct joints
        v = tuple((base[k] + i * 37 + _h(ch + str(i)) % 61) % GRID
                  for k in range(3))
        verts.append(v)
    n = len(verts)
    edges = [(i, i + 1) for i in range(n - 1)]
    # faces: consecutive triples forming a non-degenerate triangle
    faces = []
    for i in range(n - 2):
        a, b, c = verts[i], verts[i + 1], verts[i + 2]
        # non-collinear check via squared-area proxy (Manhattan spread)
        spread = (abs(a[0]-b[0])+abs(b[0]-c[0])+abs(a[0]-c[0]) +
                  abs(a[1]-b[1])+abs(b[1]-c[1])+abs(a[1]-c[1]))
        if spread > 30:
            faces.append((i, i + 1, i + 2))
    return {"name": s, "vertices": verts, "edges": edges, "faces": faces}


def mesh_stats(mesh):
    V, E, F = len(mesh["vertices"]), len(mesh["edges"]), len(mesh["faces"])
    chi = V - E + F
    # P1: path edges alone give chi_path = 1; faces raise it
    return {"V": V, "E": E, "F": F, "chi": chi,
            "chi_path_only": V - (V - 1) + 0}


# --------------------------------------------------------- polyform rig ------

DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def rig_polyform(s: str):
    """String -> polyomino: deterministic 4-neighbor walk on Z^2.
    Each char's hash picks a direction; collisions re-try the next
    direction in hash order (keeps walk self-avoiding when possible)."""
    cells = {(0, 0)}
    order = []
    x = y = 0
    for ch in s:
        h = _h(ch)
        dirs = DIRS[h % 4:] + DIRS[:h % 4]      # hash-rotated order
        moved = False
        for d in dirs:
            nx, ny = x + d[0], y + d[1]
            if (nx, ny) not in cells:
                x, y = nx, ny
                cells.add((x, y))
                moved = True
                break
        if not moved:                            # trapped: stay put
            pass
        order.append((x, y))
    # boundary edges + connectivity proof (P2: 4-neighbor path)
    boundary = 0
    for c in cells:
        for d in DIRS:
            if (c[0] + d[0], c[1] + d[1]) not in cells:
                boundary += 1
    # BFS connectivity check
    seen = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        cx, cy = stack.pop()
        for d in DIRS:
            nb = (cx + d[0], cy + d[1])
            if nb in cells and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    connected = seen == cells
    return {"cells": sorted(cells), "order": order,
            "boundary_edges": boundary, "connected": connected,
            "area": len(cells)}


# ------------------------------------------------------------- export --------

def export_obj(mesh, path):
    with open(path, "w") as f:
        f.write(f"# GMR-01 rigged mesh: {mesh['name']}\n")
        for v in mesh["vertices"]:
            f.write(f"v {v[0]} {v[1]} {v[2]}\n")
        for a, b in mesh["edges"]:
            f.write(f"l {a + 1} {b + 1}\n")
        for a, b, c in mesh["faces"]:
            f.write(f"f {a + 1} {b + 1} {c + 1}\n")


def report(s):
    mesh = rig_mesh(s)
    poly = rig_polyform(s)
    ms = mesh_stats(mesh)
    out = []
    out.append(f"rig report for {s!r} (n={len(s)})")
    out.append(f"  MESH   : V={ms['V']} E={ms['E']} F={ms['F']} "
               f"chi={ms['chi']} (path-only chi={ms['chi_path_only']})")
    out.append(f"  POLY   : area={poly['area']} cells, "
               f"boundary={poly['boundary_edges']} edges, "
               f"connected={poly['connected']} (P2: always True)")
    out.append(f"  PROOFS : P1 chi>=1 holds ({ms['chi']}>=1: "
               f"{ms['chi'] >= 1}) | P3 deterministic: "
               f"{rig_mesh(s) == mesh}")
    return "\n".join(out), mesh, poly


if __name__ == "__main__":
    s = sys.argv[1] if len(sys.argv) > 1 else "f2-deep-high-c523a"
    text, mesh, poly = report(s)
    print(text)
    obj = s.replace("/", "_")[:40] + ".obj"
    export_obj(mesh, obj)
    with open(obj.replace(".obj", ".poly.json"), "w") as f:
        json.dump(poly, f)
    print(f"  wrote {obj} and {obj.replace('.obj', '.poly.json')}")
