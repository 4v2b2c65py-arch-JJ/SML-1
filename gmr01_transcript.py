#!/usr/bin/env python3
"""
GMR-01 decode transcript — Stage 3 artifact.

Runs one signal-gated decode (R4), writes:
  decode_log.jsonl  — structured per-step log
  transcript.txt    — readable English transcript

Text decoding into readable English uses open-source libraries:
  wordninja  — splits run-together tokens into probable words
  wordfreq   — ranks candidate English words by frequency

Word hints are best-effort decodes of compact tokens (signal labels,
content ids); they are approximate and labeled as such.
"""

import json
import random
import re

import wordninja
from wordfreq import zipf_frequency

import gmr01
from gmr01 import Transition, canon, p_safe
from gmr01_decode import make_state_space, sample_edges, backbone_variants
from gmr01_signal import (edge_signature, classify, similarity, noisy,
                          find_origin_sig, SIGMA)

gmr01.HASH_MODE = "cand"

TRIALS_SEED = 7
N_NETS = 15
STEPS = 10
OUT_LOG = "decode_log.jsonl"
OUT_TXT = "transcript.txt"


def word_hint(token: str) -> str:
    """Best-effort decode of a compact token into probable English.

    Uses wordninja for segmentation and wordfreq to sanity-rank the
    result. Returns '"<decoded>" (~word)' or '(no decode)'."""
    # split into alphabetic runs; digits/hex stay attached to neighbors
    parts = re.findall(r"[a-zA-Z]+|[0-9a-fA-F]+", token)
    words = []
    for p in parts:
        if p.isalpha():
            words.extend(wordninja.split(p.lower()))
        else:
            words.append(p)
    text = " ".join(words)
    # rank by mean wordfreq of alphabetic words
    alpha = [w for w in words if w.isalpha()]
    if not alpha:
        return f"({text})"
    score = sum(zipf_frequency(w, "en") for w in alpha) / len(alpha)
    return f'"{text}" (~{score:.1f})'


def state_name(row, col) -> str:
    return f"row {row} col {col}"


def run_logged_decode():
    rng = random.Random(TRIALS_SEED)
    rows, cols = 4, 4
    sector_tags = {(r, c): f"Z{r}{c}" for r in range(rows)
                   for c in range(cols) if (r + c) % 3 == 0}
    states = make_state_space(rows, cols, sector_tags)
    init_states = [s for s in states if s.row == 0]

    backbone = sample_edges(states, rng, p=0.25)
    nets = backbone_variants(states, init_states, backbone, N_NETS, rng)

    # plant a trajectory and emulate its external signal
    cur = rng.choice(init_states)
    true_edges, obs = [], []
    for _ in range(STEPS):
        outs = sorted([b for (a, b) in backbone if a == cur], key=repr)
        if not outs:
            break
        dst = rng.choice(outs)
        true_edges.append((cur, dst))
        obs.append(noisy(edge_signature(cur, dst), rng, SIGMA))
        cur = dst

    found_init, found_trans, score = find_origin_sig(
        nets, init_states, obs, STEPS)

    # per-step records for the FOUND (decoded) path
    records = []
    for k, t in enumerate(found_trans):
        sig = edge_signature(t.src, t.dst)
        ob = obs[k] if k < len(obs) else None
        sim = similarity(sig, ob) if ob else None
        records.append({
            "step": k + 1,
            "from": {"row": t.src.row, "col": t.src.col},
            "to": {"row": t.dst.row, "col": t.dst.col},
            "sector": t.dst.tag or None,
            "arrow": t.arrow,
            "signal": {
                "freq": round(sig.freq, 4),
                "depth": round(sig.depth, 4),
                "density": round(sig.density, 4),
                "content": sig.content,
                "label": classify(sig),
            },
            "observed": ({
                "freq": round(ob.freq, 4),
                "depth": round(ob.depth, 4),
                "density": round(ob.density, 4),
                "content": ob.content,
                "label": classify(ob),
            } if ob else None),
            "signal_similarity": round(sim, 4) if sim is not None else None,
        })

    meta = {
        "seed": TRIALS_SEED, "n_nets": N_NETS, "steps": STEPS,
        "hash_mode": gmr01.HASH_MODE, "noise_sigma": SIGMA,
        "origin_found": {"row": found_init.row, "col": found_init.col}
        if found_init else None,
        "origin_score": round(score, 4),
        "decoded_steps": len(found_trans),
        "planted_steps": len(true_edges),
        "exact_path_match": len(found_trans) == len(true_edges) and all(
            (t.src, t.dst) == e for t, e in zip(found_trans, true_edges)),
    }
    return meta, records


def render_transcript(meta, records):
    L = []
    L.append("=" * 64)
    L.append("GMR-01 SIGNAL DECODE — READABLE TRANSCRIPT")
    L.append("=" * 64)
    L.append(f"Configuration : {meta['n_nets']} network variants, "
             f"{meta['steps']} steps, hash_mode={meta['hash_mode']}, "
             f"noise sigma={meta['noise_sigma']}")
    of = meta["origin_found"]
    L.append(f"Origin found  : {state_name(of['row'], of['col'])}"
             if of else "Origin found  : none")
    L.append(f"Decode score  : {meta['origin_score']}")
    L.append(f"Path match    : {'YES — decoded path equals planted path' if meta['exact_path_match'] else 'NO — partial match'}")
    L.append(f"Steps decoded : {meta['decoded_steps']} of {meta['planted_steps']} planted")
    L.append("")
    L.append("-" * 64)
    for r in records:
        sig = r["signal"]
        obs = r["observed"]
        L.append(f"Step {r['step']:02d}: {state_name(r['from']['row'], r['from']['col'])}"
                 f" -> {state_name(r['to']['row'], r['to']['col'])}"
                 f"  [{r['arrow']} arrow"
                 + (f", sector {r['sector']}" if r["sector"] else "") + "]")
        L.append(f"         predicted signal: freq={sig['freq']} "
                 f"depth={sig['depth']} density={sig['density']} "
                 f"content={sig['content']}")
        L.append(f"         label            : {sig['label']}")
        if obs:
            L.append(f"         observed signal : freq={obs['freq']} "
                     f"depth={obs['depth']} density={obs['density']} "
                     f"content={obs['content']}  (label: {obs['label']})")
            L.append(f"         similarity       : {r['signal_similarity']}")
        L.append(f"         word hint         : {word_hint(sig['label'])}")
        L.append("")
    L.append("-" * 64)
    L.append("Word hints are approximate decodes via wordninja + wordfreq "
             "(open-source). They are not part of the mathematical record.")
    return "\n".join(L)


def main():
    meta, records = run_logged_decode()
    # JSONL: meta header line, then one record per step
    with open(OUT_LOG, "w") as f:
        f.write(json.dumps({"meta": meta}) + "\n")
        for r in records:
            f.write(json.dumps(r) + "\n")
    with open(OUT_TXT, "w") as f:
        f.write(render_transcript(meta, records))
    print(f"wrote {OUT_LOG} and {OUT_TXT}")
    print(f"exact_path_match={meta['exact_path_match']} "
          f"origin={meta['origin_found']} score={meta['origin_score']}")


if __name__ == "__main__":
    main()
