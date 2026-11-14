#!/usr/bin/env python3
"""GML spec — indented pipeline descriptor integrated into GMR-01.

The source block is preserved verbatim (SRC). The parser reads the
indentation tree, extracts stage bindings (``<name1.2`` version pins),
python-operation markers, and compression nodes, then emits a stream
path + return packet in the same style as the GMR registry scaffold.
"""

import hashlib
import json
import re

SRC = """Glutons
C-3dots N loop python
Euler mass \\ python
M sling light drop c Y womepi
V  python ll u b y24R 6py|l
        Compression
            ^ 2 n p ^ 1 6 p^ 11
Maiden
3c LVc1.2
Shortcut
MCI1<C1.2
Compression
V3openloop21<openloop1.2
Math
23010U121<U1.2"""

VERSION_RE = re.compile(r"<([A-Za-z0-9_.\-]*?1\.2)")
TAG_RE = re.compile(r"<([^<>\s]+)")


def parse(src: str = SRC):
    """Indentation parse -> forest of {label, children, depth, line}."""
    roots, stack = [], []
    for raw in src.splitlines():
        if not raw.strip():
            continue
        depth = len(raw) - len(raw.lstrip(" "))
        node = {"label": raw.strip(), "depth": depth, "children": []}
        while stack and stack[-1]["depth"] >= depth:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots


def _analyze(node):
    """Pull structured fields out of one node label."""
    label = node["label"]
    low = label.lower()
    versions = VERSION_RE.findall(label)
    tags = TAG_RE.findall(label)
    return {
        "label": label,
        "depth": node["depth"],
        "python_op": "python" in low,
        "compression": "compression" in low,
        "math": "math" in low,
        "versions": versions,
        "dino_nametag": "dino" if versions else None,
        "tags": tags,
        "children": [],  # flat stage list; nesting kept via depth
    }


def stages(roots=None):
    """Flatten the forest into the ordered pipeline stage list."""
    roots = roots if roots is not None else parse()
    out = []

    def walk(n):
        out.append(_analyze(n))
        for c in n["children"]:
            walk(c)

    for r in roots:
        walk(r)
    return out


def spine():
    """Root->leaf labels in order; nested children inlined after parent."""
    path = []

    def walk(n):
        path.append(n["label"])
        for c in n["children"]:
            walk(c)

    for r in parse():
        walk(r)
    return path


def stream_path():
    return "/".join(spine())


def packet():
    """Return packet: stream + review + stage bindings + compression ops."""
    st = stages()
    comps = [n for n in st if n["compression"]]
    py_ops = [n["label"] for n in st if n["python_op"]]
    bound = {n["label"]: n["versions"] for n in st if n["versions"]}
    dino = {n["label"]: n["versions"] for n in st
            if n.get("dino_nametag") == "dino"}
    stream = stream_path()
    review = {
        "nonempty": bool(stream),
        "has_compression": bool(comps),
        "has_python_ops": bool(py_ops),
        "versioned_bindings": bound,
    }
    return {
        "stream": stream,
        "spine": spine(),
        "stages": st,
        "compression_ops": [c["label"] for c in comps],
        "python_ops": py_ops,
        "version_bindings": bound,
        "dino_nametags": dino,
        "review": review,
        "integrity": {
            "sha256": hashlib.sha256(SRC.encode()).hexdigest()[:16],
            "lines": len([l for l in SRC.splitlines() if l.strip()]),
            "source_preserved": True,
        },
    }


CF_REQ_SRC = """Cloudflare Tunnel
    api_token <secret1.2
    account_id <lookup1.2
    zone_id <lookup1.2
    hostname <chosen1.2
    Shortcut
        MCI1<CF1.2"""


def cf_requirements() -> dict:
    """GML packet for the 4 Cloudflare tunnel requirements.

    Each field is a bound stage: api_token is a Cloudflare-issued
    secret (cannot be model-generated), account_id/zone_id are
    API-discoverable once a token exists, hostname is user-chosen
    (default atlas.<zone>)."""
    roots = parse(CF_REQ_SRC)
    st = stages(roots)
    return {
        "spec": "CF-01",
        "stream": "/".join(_spine(roots)),
        "fields": {
            "api_token": {"kind": "secret",
                          "source": "Cloudflare dashboard -> API Tokens "
                                    "(Account:Cloudflare Tunnel Edit + "
                                    "Zone:DNS Edit)",
                          "model_generatable": False},
            "account_id": {"kind": "lookup",
                           "source": "GET /accounts with api_token"},
            "zone_id": {"kind": "lookup",
                        "source": "GET /zones?account.id=<account_id>"},
            "hostname": {"kind": "chosen",
                         "source": "user pick, default atlas.<zone name>"},
        },
        "stages": st,
        "shortcut": "CF1.2",
        "note": "api_token is a Cloudflare-issued credential — no model "
                "can mint it. The other three are derived via the "
                "Cloudflare API once the token exists.",
    }


def _spine(roots):
    path = []

    def walk(n):
        path.append(n["label"])
        for c in n["children"]:
            walk(c)

    for r in roots:
        walk(r)
    return path


AUTO_SRC = """Automation
    add 1 <rule1.2
    loop python
        counter ^ 1 6py|l
    Shortcut
        MCI1<auto1.2"""


def auto_packet(counter: int = 0) -> dict:
    """AUTO-01 spec packet: the 'add 1' rule applied to a persistent
    counter. Each tick increments and re-binds the auto1.2 pin."""
    roots = parse(AUTO_SRC)
    flat = []

    def walk(n):
        flat.append(_analyze(n))
        for c in n["children"]:
            walk(c)

    for r in roots:
        walk(r)
    nxt = counter + 1
    return {
        "spec": "AUTO-01",
        "rule": "add 1",
        "counter": nxt,
        "stream": "/".join(_spine(roots)),
        "stages": flat,
        "bindings": {"auto1.2": f"tick#{nxt}"},
        "dino_nametags": {"MCI1<auto1.2": ["auto1.2"]},
    }


def registry_entry():
    """GMR-style registry card for this spec."""
    p = packet()
    return {
        "id": "GML-01",
        "kind": "pipeline-spec",
        "stream": p["stream"],
        "stages": len(p["stages"]),
        "compression_ops": p["compression_ops"],
        "python_ops": p["python_ops"],
        "version_bindings": p["version_bindings"],
        "dino_nametags": p["dino_nametags"],
        "sha256_16": p["integrity"]["sha256"],
    }


if __name__ == "__main__":
    print(json.dumps(registry_entry(), indent=1))
