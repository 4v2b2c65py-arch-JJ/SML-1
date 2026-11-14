#!/usr/bin/env python3
"""
GMR-01 handoff store — PROPOSED extension.

'use store like cypher key to pass on handoff to the model embedded
calls via repetitive statements' — interpreted as:

  - a keyed JSON store (handoff_store.json) where each handoff record
    is filed under a 'cypher key': a keyed SHA-256 digest of the
    ensemble identity + record index (cipher-key interpretation;
    NOT Neo4j Cypher — flagged as assumption)
  - repetitive handoff statements (handoff_statements.txt): one
    fixed-format HANDOFF line per decode record, readable by an
    embedded model call without additional parsing context

Reads decode_log.jsonl; writes handoff_store.json and
handoff_statements.txt.
"""

import hashlib
import json

from gmr01 import canon

LOG = "decode_log.jsonl"
STORE = "handoff_store.json"
STMTS = "handoff_statements.txt"

CIPHER_KEY = "gmr01-handoff-v1"   # PROPOSED store key ('cypher key')


def cypher_key(material: str) -> str:
    """Keyed digest: HMAC-style sha256(CIPHER_KEY || material)."""
    return hashlib.sha256(
        (CIPHER_KEY + "|" + material).encode()).hexdigest()


def handoff_key(meta, idx: int) -> str:
    base = canon({k: meta[k] for k in
                  ("seed", "n_nets", "steps", "hash_mode", "noise_sigma")})
    return cypher_key(f"{base}|{idx}")[:16]


def record_fields(r, fids):
    sig = r["signal"]
    return {
        "step": r["step"],
        "from": f"{r['from']['row']},{r['from']['col']}",
        "to": f"{r['to']['row']},{r['to']['col']}",
        "sector": r["sector"],
        "arrow": r["arrow"],
        "label": sig["label"],
        "content": sig["content"],
        "fidelity": round(fids[r["step"] - 1], 4),
        "sim": r.get("signal_similarity"),
    }


def main():
    with open(LOG) as f:
        lines = [json.loads(l) for l in f if l.strip()]
    meta, records = lines[0]["meta"], lines[1:]

    # fidelity column (same rule as tracker)
    fids = []
    for r in records:
        ob = r.get("observed")
        fids.append(1.0 if (ob and ob["content"] == r["signal"]["content"])
                    else (r.get("signal_similarity") or 0.0))

    store = {}
    stmts = []
    for r in records:
        key = handoff_key(meta, r["step"])
        fields = record_fields(r, fids)
        store[key] = fields
        # repetitive fixed-format statement for embedded model calls
        stmts.append(
            f"HANDOFF key={key} step={fields['step']} "
            f"edge={fields['from']}>{fields['to']} "
            f"sector={fields['sector'] or '-'} arrow={fields['arrow']} "
            f"label={fields['label']} content={fields['content']} "
            f"fidelity={fields['fidelity']}")

    envelope = {
        "cipher_key_id": CIPHER_KEY,
        "ensemble": {k: meta[k] for k in
                     ("seed", "n_nets", "steps", "hash_mode", "noise_sigma")},
        "origin": meta["origin_found"],
        "origin_score": meta["origin_score"],
        "exact_path_match": meta["exact_path_match"],
        "records": store,
    }
    with open(STORE, "w") as f:
        json.dump(envelope, f, indent=2)
    with open(STMTS, "w") as f:
        f.write("\n".join(stmts) + "\n")

    print(f"wrote {STORE} ({len(store)} keyed records) and {STMTS}")
    print(f"sample statement:\n  {stmts[0] if stmts else '(none)'}")


if __name__ == "__main__":
    main()
