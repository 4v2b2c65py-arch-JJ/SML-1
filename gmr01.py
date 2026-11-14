#!/usr/bin/env python3
"""
GMR-01 reference implementation — PROPOSED semantics only.

Implements the conjectural plausibility pipeline from GMR-01.md:
    P_safe(k) = G_T(tau_k) * G_Lambda(s_k) * G_H(seq_k)

Nothing here is established mathematics. It is a scaffold for Stage 3
(computational validation). All registry bindings are PROPOSED.
"""

import hashlib
import json
import random
from dataclasses import asdict, dataclass, field, is_dataclass

# ---------------------------------------------------------------- registry ---

HASH_WIDTH = 256          # PROPOSED: w bits for bithash (SHA-256 native width)
LAMBDA_MIN = 8            # PROPOSED binding for bitlengmin (bits)
LAMBDA_MAX = 64           # PROPOSED binding for bitlenghmax (bits)

HASH_MODE = "net"   # PROPOSED modes for G_H:
                    #   "net"  = original: 1 - |H(seq) - H_ref(net)|
                    #   "seq"  = R1: H(seq) — network-invariant but candidate-blind
                    #   "cand" = R3: H(seq + canon(candidate)) — candidate-weighted

ALPHA, BETA, GAMMA, THETA = 1.0, 1.0, 1.0, 1.5   # PROPOSED logistic weights


def canon(obj) -> str:
    """Canonical serialization of any registry object."""
    def default(o):
        if is_dataclass(o):
            return asdict(o)
        return repr(o)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=default)


def bithash(seq) -> str:
    """PROPOSED binding for `bithash`: SHA-256(canon(seq)) truncated to HASH_WIDTH."""
    return hashlib.sha256(canon(seq).encode()).hexdigest()[: HASH_WIDTH // 4]


def H(seq) -> float:
    """Normalized hash in [0,1] — the 'impedance' normalization constant."""
    return int(bithash(seq), 16) / (1 << HASH_WIDTH)


# ------------------------------------------------------------------ states ---

@dataclass(frozen=True)
class State:
    row: int
    col: int
    tag: str = ""

    def enc(self) -> str:
        """PROPOSED canonical bit encoding of a state."""
        raw = f"{self.row}:{self.col}:{self.tag}"
        return "".join(f"{b:08b}" for b in raw.encode())


@dataclass(frozen=True)
class Transition:
    src: State
    dst: State
    arrow: str          # 'init' | 'point' | 'dot' rule label
    sector: str = ""    # expansion-zone sector entered, if any


# -------------------------------------------------------------------- gates ---

def bit_length_ok(state: State) -> bool:
    """G_Lambda: length gate on enc(state)."""
    n = len(state.enc())
    return LAMBDA_MIN <= n <= LAMBDA_MAX


def transition_ok(t: Transition, net: "Network") -> bool:
    """G_T: arrow-rule admissibility of a transition."""
    if t.arrow == "init":
        return net.is_init(t.src) and t.src == t.dst or net.is_init(t.src)
    if t.arrow == "point":
        return net.points_to(t.src, t.dst)
    if t.arrow == "dot":
        return net.composable(t.src, t.dst)
    return False


def hash_gate(seq, t, net: "Network") -> float:
    """G_H: hash-consistency gate in [0,1].

    "net" mode (original): 1 - |H(seq) - H_ref(net)|, clipped, where
    H_ref is the hash of the network's canonical structure.
    "seq" mode (revision R1): network-invariant gate based only on the
    sequence — measures self-consistency of the hash chain.
    "cand" mode (revision R3): H(seq + canon(t)) — each candidate
    transition gets a fixed network-invariant plausibility weight;
    shared edges correlate votes across network variants.
    """
    if HASH_MODE == "seq":
        return H(seq)
    if HASH_MODE == "cand":
        return H(list(seq) + [canon(t.__dict__)])
    ref = H(canon(net.structure()))
    return max(0.0, 1.0 - abs(H(seq) - ref))


def p_safe(t: Transition, seq, net: "Network") -> float:
    """P_safe(k) = G_T * G_Lambda * G_H  (conjunctive gate form)."""
    g_t = 1.0 if transition_ok(t, net) else 0.0
    g_l = 1.0 if bit_length_ok(t.dst) else 0.0
    g_h = hash_gate(seq, t, net)
    return g_t * g_l * g_h


def score(t: Transition, seq, net: "Network") -> float:
    """Graded variant S(k) = sigmoid(a*G_T + b*G_L + c*G_H - theta)."""
    import math
    g_t = 1.0 if transition_ok(t, net) else 0.0
    g_l = 1.0 if bit_length_ok(t.dst) else 0.0
    g_h = hash_gate(seq, t, net)
    z = ALPHA * g_t + BETA * g_l + GAMMA * g_h - THETA
    return 1.0 / (1.0 + math.exp(-z))


# ------------------------------------------------------------------ network ---

class Network:
    """PROPOSED: row-structured state graph with arrow rules."""

    def __init__(self, rows: int, cols: int, init_states, rng: random.Random):
        self.rows, self.cols = rows, cols
        self.states = [State(r, c) for r in range(rows) for c in range(cols)]
        self.init = set(init_states)
        self.edges = set()
        self._build(rng)

    def _build(self, rng: random.Random):
        for s in self.states:
            for _ in range(rng.randint(1, 3)):
                t = rng.choice(self.states)
                if t != s:
                    self.edges.add((s, t))

    def is_init(self, s: State) -> bool:
        return s in self.init

    def points_to(self, a: State, b: State) -> bool:
        return (a, b) in self.edges

    def composable(self, a: State, b: State) -> bool:
        # dot: b reachable after a via one intermediate (composition)
        return any((a, m) in self.edges and (m, b) in self.edges for m in self.states)

    def structure(self):
        return {
            "rows": self.rows, "cols": self.cols,
            "states": [s.__dict__ for s in self.states],
            "init": [s.__dict__ for s in self.init],
            "edges": [list(e) for e in sorted(self.edges, key=repr)],
        }

    def random_trajectory(self, rng: random.Random, length: int):
        seq, trans = [], []
        cur = rng.choice(self.states)
        for _ in range(length):
            nxt = [b for (a, b) in self.edges if a == cur]
            if not nxt:
                break
            dst = rng.choice(nxt)
            arrow = rng.choice(["point", "dot"])
            t = Transition(cur, dst, arrow)
            trans.append(t)
            seq.append(canon(t.__dict__))
            cur = dst
        return trans, seq


# ------------------------------------------------------------- self-test ----

def self_test():
    rng = random.Random(0)
    fails = []

    for trial in range(200):
        net = Network(rows=rng.randint(2, 5), cols=rng.randint(2, 5),
                      init_states=set(), rng=rng)
        trans, seq = net.random_trajectory(rng, rng.randint(1, 8))

        for i, t in enumerate(trans):
            p = p_safe(t, seq[: i + 1], net)
            s = score(t, seq[: i + 1], net)

            # I1: any zero gate => P = 0
            if not transition_ok(t, net):
                assert p == 0.0, f"I1 violated: p={p}"
            if not bit_length_ok(t.dst):
                assert p == 0.0, f"I1 violated (len): p={p}"

            # I2: bounded
            assert 0.0 <= p <= 1.0, f"I2 violated: p={p}"
            assert 0.0 <= s <= 1.0, f"I2 violated: s={s}"

            # I3: hash determinism
            assert bithash(seq[: i + 1]) == bithash(seq[: i + 1])

        # I5: boundary inclusivity of length gate
        for st in net.states:
            n = len(st.enc())
            assert bit_length_ok(st) == (LAMBDA_MIN <= n <= LAMBDA_MAX)

    print(f"self_test: 200 networks x trajectories — all invariants held")
    return fails


if __name__ == "__main__":
    self_test()
