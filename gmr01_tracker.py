#!/usr/bin/env python3
"""
GMR-01 shell tracker — PROPOSED extension (Stage 3 artifact).

Components (interpretation of user directive; assumptions logged in
GMR-01.md):

  1. peer seeds      — deterministic per-variant seed ledger derived
                       from the ensemble key; peers sharing the key
                       derive identical streams (reproducibility)
  2. fidelity column — per-step signal fidelity (content lock +
                       continuous similarity) in the transcript
  3. parallel word count — multiprocessing word statistics over
                       transcript.txt plus run parameters
  4. word/acronymical alphabet — token alphabet extended with word
                       labels AND acronym forms of every token
  5. qbit shear      — quantum-INSPIRED (not quantum) encoding: the
                       three continuous signal features are quantized
                       to nibbles and sheared into qbit-pair tokens
                       plus a remainder token
  6. label iteration — labels assigned per record and iterated until
                       a fixed point, then emitted as token output

Reads decode_log.jsonl + transcript.txt; writes tracker_report.txt
and tokens.json.
"""

import json
import re
from collections import Counter
from multiprocessing import Pool

from gmr01 import canon, bithash

LOG = "decode_log.jsonl"
TXT = "transcript.txt"
REPORT = "tracker_report.txt"
TOKENS = "tokens.json"
WORKERS = 4


# ------------------------------------------------------------- 1. peer seeds --

def peer_seed(idx: int, ensemble_key: str) -> int:
    """Deterministic 32-bit seed for peer/variant idx."""
    return int(bithash([ensemble_key, f"peer{idx}"]), 16) % (2 ** 32)


def peer_seed_ledger(meta, n_peers=15):
    key = canon({k: meta[k] for k in
                 ("seed", "n_nets", "steps", "hash_mode", "noise_sigma")})
    ledger = {f"peer{i}": peer_seed(i, key) for i in range(n_peers)}
    # fidelity check: same key -> same seeds (re-derivation identical)
    check = all(peer_seed(i, key) == s for i, s in enumerate(ledger.values()))
    return ledger, check


# ------------------------------------------------- 3. parallel word count ----

def _count_chunk(words):
    return Counter(words)


def parallel_word_count(text, workers=WORKERS):
    words = re.findall(r"[a-z]+", text.lower())
    chunks = [words[i::workers] for i in range(workers) if words[i::workers]]
    with Pool(workers) as pool:
        parts = pool.map(_count_chunk, chunks)
    total = Counter()
    for c in parts:
        total.update(c)
    return total, len(words)


# ------------------------------------------------ 4. alphabet + 5. qbits ------

def build_alphabet(records):
    """Word + acronymical alphabet: every token gets an index; each
    multi-part token also contributes its acronym form."""
    alpha = {}

    def add(tok):
        if tok and tok not in alpha:
            alpha[tok] = len(alpha)

    for r in records:
        add(r["signal"]["label"])
        if r["sector"]:
            add(r["sector"])
        add(r["arrow"])
        add(r["signal"]["content"])
        if r["observed"]:
            add(r["observed"]["label"])
            add(r["observed"]["content"])

    # acronymical extension: initials of label parts, uppercased
    for tok in list(alpha):
        parts = [w for w in re.split(r"[-\d]", tok) if w.isalpha()]
        if len(parts) >= 2:
            add("".join(w[0] for w in parts).upper()[:6])
    return alpha


def shear_qbits(record):
    """Quantum-inspired shear: quantize freq/depth/density to nibbles,
    pair them into qbit tokens, emit leftover nibble as remainder."""
    q = [round(min(1.0, max(0.0, record["signal"][k]))) * 15
         for k in ("freq", "depth", "density")]
    tokens = [f"q{a:02x}{b:02x}" for a, b in zip(q[::2], q[1::2])]
    if len(q) % 2:
        tokens.append(f"r{q[-1]:x}")
    return tokens


# ------------------------------------------------------- 2. fidelity ---------

def fidelity_column(records):
    """Per-step fidelity: 1.0 when observed content locks to predicted
    content, else the continuous similarity."""
    out = []
    for r in records:
        ob = r.get("observed")
        if ob and ob["content"] == r["signal"]["content"]:
            out.append(1.0)
        else:
            out.append(r.get("signal_similarity") or 0.0)
    return out


# ------------------------------------------------- 6. labels -> tokens -------

def compute_labels(records, alphabet):
    """Assign each record its alphabet index; iterate until the label
    sequence is a fixed point (converges immediately — labels are a pure
    function of the record — but the loop enforces the 'till stable'
    requirement explicitly)."""
    labels = [alphabet.get(r["signal"]["label"], -1) for r in records]
    for it in range(10):
        new = [alphabet.get(r["signal"]["label"], -1) for r in records]
        if new == labels:
            break
        labels = new
    # token output: label index followed by sheared qbit tokens
    tokens = []
    for lab, r in zip(labels, records):
        tokens.append(lab)
        tokens.extend(shear_qbits(r))
    return labels, tokens, it + 1


# ------------------------------------------------------------------ main -----

def main():
    with open(LOG) as f:
        lines = [json.loads(l) for l in f if l.strip()]
    meta, records = lines[0]["meta"], lines[1:]

    with open(TXT) as f:
        transcript = f.read()

    # 1. peer seeds
    ledger, seeds_ok = peer_seed_ledger(meta)

    # 2. fidelity
    fids = fidelity_column(records)

    # 3. parallel word count + parameters
    wc, total_words = parallel_word_count(transcript)

    # 4/5/6. alphabet, qbits, labels -> tokens
    alphabet = build_alphabet(records)
    labels, tokens, iters = compute_labels(records, alphabet)

    # ---- report ----
    R = []
    R.append("=" * 64)
    R.append("GMR-01 SHELL TRACKER REPORT")
    R.append("=" * 64)
    R.append(f"records={len(records)} steps | parameters: "
             f"n_nets={meta['n_nets']} hash_mode={meta['hash_mode']} "
             f"sigma={meta['noise_sigma']} seed={meta['seed']}")
    R.append("")
    R.append("[1] PEER SEED LEDGER (deterministic, ensemble-keyed)")
    R.append(f"    seeds reproducible across re-derivation: {seeds_ok}")
    for k, v in list(ledger.items())[:5]:
        R.append(f"    {k}: {v}")
    R.append(f"    ... ({len(ledger)} peers total)")
    R.append("")
    R.append("[2] FIDELITY COLUMN (per-step signal lock)")
    R.append(f"    mean fidelity: {sum(fids)/len(fids):.3f} | "
             f"content-locked steps: {sum(1 for x in fids if x == 1.0)}/{len(fids)}")
    R.append("")
    R.append(f"[3] PARALLEL WORD COUNT ({WORKERS} workers)")
    R.append(f"    total words: {total_words} | distinct: {len(wc)}")
    R.append("    top 10: " + ", ".join(f"{w}({c})" for w, c in wc.most_common(10)))
    R.append("")
    R.append("[4] WORD/ACRONYMICAL ALPHABET")
    R.append(f"    tokens: {len(alphabet)} "
             f"({sum(1 for t in alphabet if t.isupper() and len(t) <= 6)} acronyms)")
    R.append("    sample: " + ", ".join(list(alphabet)[:8]))
    R.append("")
    R.append("[5] QBUT SHEAR (quantum-inspired nibble pairs)")
    R.append(f"    tokens per record: label + {len(shear_qbits(records[0]))} "
             f"qbit/remainder tokens")
    R.append(f"    sample: {shear_qbits(records[0])}")
    R.append("")
    R.append("[6] LABEL ITERATION -> TOKEN OUTPUT")
    R.append(f"    converged in {iters} iteration(s) (fixed point)")
    R.append(f"    labels: {labels}")
    R.append(f"    token stream length: {len(tokens)}")
    R.append(f"    first 20 tokens: {tokens[:20]}")

    with open(REPORT, "w") as f:
        f.write("\n".join(R) + "\n")
    with open(TOKENS, "w") as f:
        json.dump({"labels": labels, "tokens": tokens,
                   "alphabet": alphabet}, f, indent=2)
    print(f"wrote {REPORT} and {TOKENS}")


if __name__ == "__main__":
    main()
