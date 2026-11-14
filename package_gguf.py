#!/usr/bin/env python3
"""
GMR-01 GGUF packager — packages the registry into GGUF format for the
GitHub repo ('package a gguf for githubrepo to keep it alive').

HONEST NOTE: this is a DATA CONTAINER in GGUF format — the GMR-01
symbol registry, token vocabulary, and deterministic hash embeddings
as tensors. It is NOT trained model weights and cannot run inference.
It exists so the registry persists in a standard model-file format.

Produces: gmr01.gguf  (+ gmr01.gguf.json sidecar manifest)
"""

import json

import numpy as np
from gguf import GGUFReader, GGUFWriter

from gmr01 import bithash

OUT = "gmr01.gguf"
MANIFEST = "gmr01.gguf.json"
EMB_DIM = 16


def build_vocab():
    vocab = set()
    try:
        with open("tokens.json") as f:
            vocab.update(json.load(f)["alphabet"].keys())
    except FileNotFoundError:
        pass
    vocab.update("f0123456789-dcslhmwqprGZabcdefghijklmnopqrstuvwxyz")
    return sorted(vocab)


def hash_embedding(token: str, dim: int = EMB_DIM) -> np.ndarray:
    """Deterministic pseudo-embedding from bithash — NOT trained."""
    vals = []
    for i in range(dim):
        h = int(bithash([token, f"emb{i}"]), 16) % 20000
        vals.append((h / 10000.0) - 1.0)
    return np.array(vals, dtype=np.float32)


def main():
    vocab = build_vocab()
    emb = np.stack([hash_embedding(t) for t in vocab])  # [V, D]

    w = GGUFWriter(OUT, arch="gmr01")
    w.add_name("GMR-01 Glyph Mathematical Notation Registry")
    w.add_description(
        "GMR-01 registry bundle: token vocabulary + deterministic "
        "hash embeddings. Data container, not trained weights.")
    w.add_vocab_size(len(vocab))
    w.add_uint32("gmr01.emb_dim", EMB_DIM)
    w.add_token_list(vocab)
    w.add_tensor("token_embedding", emb)
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()

    # verify by reading back
    reader = GGUFReader(OUT)
    n_tensors = len(reader.tensors)
    f = reader.fields.get("general.name")
    fields = {"general.name": bytes(f.parts[-1]).decode()
              if f else ""}

    manifest = {
        "file": OUT, "format": "gguf", "tensors": n_tensors,
        "vocab_size": len(vocab), "emb_dim": EMB_DIM,
        "arch": "gmr01", "weights_trained": False,
        "contents": "GMR-01 registry: alphabet, signal labels, "
                    "content ids; deterministic hash embeddings",
        "verify_name": str(fields.get("general.name", "")),
    }
    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
