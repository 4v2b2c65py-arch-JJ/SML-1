#!/usr/bin/env python3
"""
GMR-01 consensus decoder — PROPOSED extension (Stage 3 experiment).

Protocol per user directive:
  - move step-by-step without guidance (autonomous walk)
  - at each step, every randomized network variant casts a vote
    ('simple get': each net fetches its argmax-P_safe transition)
  - the consensus winner indexes the next result
  - accumulated validity scores identify the origin and decode
    the entire sequence in one pass

Tests CONJECTURES J2 (ranking stability across network variants)
and J3 (hash/validity convergence) from GMR-01.md.
Nothing here is established mathematics.
"""

import random
from collections import Counter, defaultdict

import gmr01
from gmr01 import State, Transition, canon, p_safe

# Revision R3: candidate-weighted hash gate (see GMR-01.md run log)
gmr01.HASH_MODE = "cand"


# ------------------------------------------------------------- variant nets ---

class VariantNet:
    """A network variant: shared state space, resampled edge wiring.

    This is the concrete meaning of 'network variety' (open question 9):
    identical states/init/sector labels, different admissible edges.
    """

    def __init__(self, states, init_states, edges):
        self.states = states
        self.init = set(init_states)
        self.edges = set(edges)
        self.adj = defaultdict(list)
        for a, b in sorted(self.edges, key=repr):
            self.adj[a].append(b)
        for k in self.adj:
            self.adj[k].sort(key=repr)
        # precompute 2-path reachability for dot-composition
        self._reach2 = set()
        for a in states:
            for m in self.adj.get(a, []):
                for b in self.adj.get(m, []):
                    self._reach2.add((a, b))

    def is_init(self, s):
        return s in self.init

    def points_to(self, a, b):
        return (a, b) in self.edges

    def composable(self, a, b):
        return (a, b) in self._reach2

    def structure(self):
        return {"edges": sorted(repr(e) for e in self.edges)}


def make_state_space(rows, cols, sector_tags):
    """sector_tags: dict {(r,c): tag} marking expansion-zone states."""
    states = []
    for r in range(rows):
        for c in range(cols):
            states.append(State(r, c, tag=sector_tags.get((r, c), "")))
    return states


def sample_edges(states, rng, p=0.3):
    edges = set()
    for a in states:
        for b in states:
            if a != b and rng.random() < p:
                edges.add((a, b))
    return edges


def backbone_variants(states, init_states, backbone, n_nets, rng,
                      keep_p=0.85, add_p=0.08):
    """'Network variety' revision R2: variants are perturbations of a
    shared backbone — backbone edges kept w.p. keep_p, extra edges
    added w.p. add_p. Original test used fully independent graphs
    (no shared structure -> no consensus signal)."""
    all_pairs = [(a, b) for a in states for b in states if a != b]
    nets = []
    for _ in range(n_nets):
        edges = set()
        for e in all_pairs:
            if e in backbone:
                if rng.random() < keep_p:
                    edges.add(e)
            elif rng.random() < add_p:
                edges.add(e)
        nets.append(VariantNet(states, init_states, edges))
    return nets


# ------------------------------------------------------------- consensus ------

def consensus_step(nets, cur, seq, rng):
    """'simple get' per net: each variant fetches its argmax-P_safe
    outgoing transition; consensus winner = highest summed validity.
    Returns (winning_Transition, validity_index) — the transition object
    is returned so the recorded sequence matches what was hashed."""
    wsum = defaultdict(float)
    tally = Counter()
    best_t_of = {}
    for net in nets:
        best_t, best_p = None, -1.0
        for dst in net.adj.get(cur, []):
            for arrow in ("point", "dot"):
                t = Transition(cur, dst, arrow, sector=dst.tag)
                p = p_safe(t, seq, net)
                if p > best_p:
                    best_p, best_t = p, t
        if best_t is None:
            continue
        tally[best_t.dst] += 1
        wsum[best_t.dst] += best_p
        best_t_of[best_t.dst] = best_t
    if not wsum:
        return None, 0.0
    win_dst = max(wsum, key=lambda s: (wsum[s], tally[s]))
    return best_t_of[win_dst], wsum[win_dst] / len(nets)


def decode(nets, origin, steps):
    """Autonomous consensus walk from origin. Returns
    (path, seq, validity_per_step)."""
    cur, seq, path, vals = origin, [], [], []
    for _ in range(steps):
        t, v = consensus_step(nets, cur, seq, None)
        if t is None:
            break
        seq.append(canon(t.__dict__))
        path.append(t.dst)
        vals.append(v)
        cur = t.dst
    return path, seq, vals


def find_origin(nets, init_states, observed_tags, steps):
    """Try each init state as candidate origin; consensus-decode and
    score against observed sector tags. Returns best origin, its decoded
    path, and its score — 'find the origin and decode the entire
    sequence in one' evaluation pass per candidate."""
    best = (None, None, -1.0)
    for init in init_states:
        path, seq, vals = decode(nets, init, steps)
        pred = [s.tag for s in path]
        match = sum(1 for a, b in zip(pred, observed_tags)
                    if a and a == b)
        score = sum(vals) + 0.5 * match
        if score > best[2]:
            best = (init, (path, seq, vals), score)
    return best


# ------------------------------------------------------------- experiment -----

def run_experiment(trials=20, n_nets=15, steps=10, seed=1):
    """Honest probe of J2/J3 under revision R3 (candidate-weighted hash).

    Measures:
      A) rank stability: for candidates shared across variants, is the
         P_safe ordering identical? (J2)
      B) backbone adherence: fraction of consensus-decoded transitions
         that are backbone edges (validity of decoded path)
      C) reproducibility: decode twice -> identical path?
      D) origin finding: feed a canonical decode's sector tags back as
         'observed'; does find_origin return the same origin?
    """
    rng = random.Random(seed)
    rows, cols = 4, 4
    sector_tags = {(r, c): f"Z{r}{c}" for r in range(rows)
                   for c in range(cols) if (r + c) % 3 == 0}
    states = make_state_space(rows, cols, sector_tags)
    init_states = [s for s in states if s.row == 0]

    rank_stable, rank_total = 0, 0
    adhere_num, adhere_den = 0, 0
    repro_ok, origin_ok = 0, 0

    for _ in range(trials):
        backbone = sample_edges(states, rng, p=0.25)
        nets = backbone_variants(states, init_states, backbone,
                                 n_nets, rng)

        # ---- A: rank stability on shared candidates ----
        cur = rng.choice(states)
        shared = [d for d in states
                  if sum((cur, d) in n.edges for n in nets) >= n_nets // 2]
        if len(shared) >= 3:
            rankings = []
            for net in nets[:5]:
                scored = []
                for d in shared:
                    t = Transition(cur, d, "point", sector=d.tag)
                    scored.append((d, p_safe(t, [], net)))
                rankings.append([d for d, _ in
                                 sorted(scored, key=lambda x: -x[1])])
            rank_total += 1
            if all(r == rankings[0] for r in rankings):
                rank_stable += 1

        # ---- B/C: decode twice from a random init ----
        origin = rng.choice(init_states)
        path1, seq1, vals1 = decode(nets, origin, steps)
        path2, seq2, vals2 = decode(nets, origin, steps)
        if [s.row for s in path1] == [s.row for s in path2] and \
           [(s.row, s.col) for s in path1] == \
           [(s.row, s.col) for s in path2]:
            repro_ok += 1
        for i, dst in enumerate(path1):
            src = origin if i == 0 else path1[i - 1]
            adhere_den += 1
            if (src, dst) in backbone:
                adhere_num += 1

        # ---- D: origin finding on canonical decode's tags ----
        observed = [s.tag for s in path1]
        found, _, _ = find_origin(nets, init_states, observed, steps)
        if found == origin:
            origin_ok += 1

    print(f"consensus decode experiment (R3): {trials} trials, "
          f"{n_nets} nets/vote, {steps} steps")
    print(f"  A) rank stability across variants: "
          f"{rank_stable}/{rank_total}")
    print(f"  B) backbone adherence of decoded path: "
          f"{adhere_num}/{adhere_den} ({adhere_num/max(adhere_den,1):.1%})")
    print(f"  C) reproducibility (identical re-decode): {repro_ok}/{trials}")
    print(f"  D) origin recovery on canonical tags: {origin_ok}/{trials}")
    print("  -> probes J2 (cross-network ranking stability), "
          "J3 (validity convergence)")


if __name__ == "__main__":
    run_experiment()
