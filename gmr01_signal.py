#!/usr/bin/env python3
"""
GMR-01 signal-gated decoding — PROPOSED extension (Stage 3 experiment, R4).

Emulates an external signal characterized by:
  - frequency  (normalized 0..1)
  - depth      (normalized 0..1)
  - density    (normalized 0..1)
  - content    (content label derived from hash)

Each candidate transition gets a deterministic Signal signature via
bithash. An observed signal sequence (emulating measurement along a
trajectory) gates plausibility:

    P_sig(k) = P_safe(k) * sim( sig(candidate_k), obs_k )

'sim' = product of Gaussian kernels on freq/depth/density times a
content-match factor. classify() labels a signal by
(freq_band, depth_tier, density_tier, content) — 'to determine what it is'.

This tests whether an external signal resolves the symmetry that made
pure consensus unable to identify a specific path (see GMR-01.md run log).
Emulated signal only — no physical claim.
"""

import math
import random
from collections import defaultdict
from dataclasses import dataclass

import gmr01
from gmr01 import State, Transition, canon, bithash, p_safe
from gmr01_decode import (VariantNet, make_state_space, sample_edges,
                          backbone_variants)

# R3 candidate-weighted hash gate (adopted revision)
gmr01.HASH_MODE = "cand"

SIGMA = 0.08          # kernel width for freq/depth/density similarity
CONTENT_WEIGHT = 1.0  # multiplier when content labels match


# ----------------------------------------------------------------- signal ---

@dataclass(frozen=True)
class Signal:
    freq: float
    depth: float
    density: float
    content: str


def edge_signature(src: State, dst: State) -> Signal:
    """Deterministic content-addressed signature of a transition."""
    h = int(bithash([canon(src.__dict__), canon(dst.__dict__)]), 16)
    return Signal(
        freq=(h & 0xFFFF) / 0xFFFF,
        depth=((h >> 16) & 0xFFFF) / 0xFFFF,
        density=((h >> 32) & 0xFFFF) / 0xFFFF,
        content=f"c{(h >> 48) & 0xFFFF:04x}",
    )


def classify(sig: Signal) -> str:
    """Label a signal by frequency band, depth tier, density tier, content."""
    band = int(sig.freq * 4)
    depth_tier = "shallow" if sig.depth < 1/3 else \
                 "mid" if sig.depth < 2/3 else "deep"
    dens_tier = "low" if sig.density < 1/3 else \
                "mid" if sig.density < 2/3 else "high"
    return f"f{band}-{depth_tier}-{dens_tier}-{sig.content}"


def similarity(a: Signal, b: Signal) -> float:
    """Product of Gaussian kernels on continuous dims x content match."""
    def k(x, y):
        return math.exp(-((x - y) ** 2) / (2 * SIGMA ** 2))
    cont = k(a.freq, b.freq) * k(a.depth, b.depth) * k(a.density, b.density)
    return cont * (CONTENT_WEIGHT if a.content == b.content else 0.0)


def noisy(sig: Signal, rng: random.Random, sigma=SIGMA) -> Signal:
    """Emulated measurement noise on continuous dims; content exact."""
    def n(x):
        return min(1.0, max(0.0, x + rng.gauss(0.0, sigma)))
    return Signal(n(sig.freq), n(sig.depth), n(sig.density), sig.content)


# ------------------------------------------------------- signal decoding -----

def consensus_step_sig(nets, cur, seq, obs_k, rng):
    """Consensus vote where each net's candidate score is gated by
    similarity to the observed external signal at step k."""
    wsum = defaultdict(float)
    tally = defaultdict(int)
    best_of = {}
    for net in nets:
        best_t, best_p = None, -1.0
        for dst in net.adj.get(cur, []):
            for arrow in ("point", "dot"):
                t = Transition(cur, dst, arrow, sector=dst.tag)
                p = p_safe(t, seq, net)
                if obs_k is not None:
                    p *= similarity(edge_signature(cur, dst), obs_k)
                if p > best_p:
                    best_p, best_t = p, t
        if best_t is None:
            continue
        key = (best_t.src, best_t.dst)
        tally[key] += 1
        wsum[key] += best_p
        best_of[key] = best_t
    if not wsum:
        return None, 0.0
    win = max(wsum, key=lambda k: (wsum[k], tally[k]))
    return best_of[win], wsum[win] / len(nets)


def decode_sig(nets, origin, steps, obs):
    """Autonomous decode gated by observed signal sequence obs.
    Returns (transitions, validity_per_step)."""
    cur, seq, trans, vals = origin, [], [], []
    for k in range(steps):
        obs_k = obs[k] if k < len(obs) else None
        t, v = consensus_step_sig(nets, cur, seq, obs_k, None)
        if t is None:
            break
        seq.append(canon(t.__dict__))
        trans.append(t)
        vals.append(v)
        cur = t.dst
    return trans, vals


def find_origin_sig(nets, init_states, obs, steps):
    """For each candidate origin, decode and score total signal
    agreement; return best (origin, transitions, score)."""
    best = (None, None, -1.0)
    for init in init_states:
        trans, vals = decode_sig(nets, init, steps, obs)
        agree = 0.0
        for k, t in enumerate(trans):
            if k < len(obs):
                agree += similarity(edge_signature(t.src, t.dst), obs[k])
        score = agree + 0.1 * sum(vals)
        if score > best[2]:
            best = (init, trans, score)
    return best


# ------------------------------------------------------------- experiment ----

def run_experiment(trials=20, n_nets=15, steps=10, seed=1, noise=SIGMA):
    rng = random.Random(seed)
    rows, cols = 4, 4
    sector_tags = {(r, c): f"Z{r}{c}" for r in range(rows)
                   for c in range(cols) if (r + c) % 3 == 0}
    states = make_state_space(rows, cols, sector_tags)
    init_states = [s for s in states if s.row == 0]

    path_hits, origin_hits, label_hits, label_total = 0, 0, 0, 0
    for _ in range(trials):
        backbone = sample_edges(states, rng, p=0.25)
        nets = backbone_variants(states, init_states, backbone,
                                 n_nets, rng)

        # plant a trajectory on the backbone and emulate its signal
        cur = rng.choice(init_states)
        true_trans = []
        for _ in range(steps):
            outs = sorted([b for (a, b) in backbone if a == cur],
                          key=repr)
            if not outs:
                break
            dst = rng.choice(outs)
            true_trans.append((cur, dst))
            cur = dst
        obs = [noisy(edge_signature(a, b), rng, noise)
               for a, b in true_trans]

        # decode with signal gating
        found_init, found_trans, score = find_origin_sig(
            nets, init_states, obs, steps)
        hit = len(found_trans) == len(true_trans) and all(
            (t.src, t.dst) == e for t, e in zip(found_trans, true_trans))
        path_hits += hit
        # origin = the init the planted walk started from
        # (we recover it by re-deriving: first true_trans src)
        true_origin = true_trans[0][0] if true_trans else None
        origin_hits += (found_init == true_origin)

        # labeling: full classify() label of noisy obs vs clean truth
        for o, (a, b) in zip(obs, true_trans):
            label_total += 1
            if classify(o) == classify(edge_signature(a, b)):
                label_hits += 1

    print(f"signal-gated decode (R4): {trials} trials, {n_nets} nets/vote, "
          f"{steps} steps, noise sigma={noise}")
    print(f"  exact planted-path recovery: {path_hits}/{trials}")
    print(f"  origin recovery: {origin_hits}/{trials}")
    print(f"  signal labeling content-match: {label_hits}/{label_total}")


if __name__ == "__main__":
    for sigma in (0.0, SIGMA, 0.20):
        run_experiment(noise=sigma)
        print()
