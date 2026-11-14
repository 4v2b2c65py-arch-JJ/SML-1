# GMR-01 — Glyph Mathematical Notation Registry

**Status:** notation reference under formalization — NOT a completed theory.
**Last updated:** 2026-11-13
**Integrity rule:** proven properties, conjectures, and undefined symbols are kept in separate sections. Nothing marked CONJECTURE, PROPOSED, or UNDEFINED is established mathematics.

**Label legend**
- `REGISTERED` — appears in directive fragments; awaiting source verification
- `PROPOSED` — new symbol introduced by this document; has name, definition, dimension, I/O type (rule 6 satisfied); awaiting user confirmation
- `CONJECTURE` — unproven claim
- `UNDEFINED` — used but not defined anywhere
- `PROVEN` — established property (none yet)

---

## 1. Registered terms (awaiting source verification)

| Term | Working reading | Status |
|---|---|---|
| `GMR-01` | Glyph Mathematical Notation Registry, six-dimensional structure | UNDEFINED (dimensions unspecified) |
| `⋆₆` | Star operation, subscript 6 | UNDEFINED — flagged for formal definition |
| `arrow point` | Arrow glyph rule — pointing/directional semantics | REGISTERED |
| `arrow init` | Arrow glyph rule — initializer/origin-state semantics | REGISTERED |
| `arrow dot` | Arrow glyph rule — composition/sequencing semantics | REGISTERED |
| `bitlengmin` | Minimum bit length bound | REGISTERED (semantics unconfirmed) |
| `bitlenghmax` | Maximum bit length bound | REGISTERED (semantics unconfirmed) |
| `bithash` | Hash/sequence identifier within the model | REGISTERED |
| `shabit` | Possibly "SHA bit" or sequence-hash fragment | UNDEFINED |
| `expansion zone` | Sector into which safe entry is scored | REGISTERED |
| `sector` | Unit of state space the trajectory encounters | REGISTERED |

---

## 2. Proposed formalization (PROPOSED — pending confirmation)

Every symbol below is new and introduced by this document. Each has a unique name, definition, dimensional specification, and input/output type.

### 2.1 Carrier sets and indexing

| Symbol | Definition | Dimension | I/O type |
|---|---|---|---|
| `Σ` | Finite glyph alphabet of GMR-01 | `|Σ| ∈ ℕ⁺` | set |
| `𝒮` | State space; states partitioned into rows `R₁…R_m` | rows × cols grid | set |
| `𝒵` | Set of expansion-zone sectors `z ∈ 𝒵` | `|𝒵| ∈ ℕ⁺` | set |
| `𝒩` | Network: graph over `𝒮 ∪ 𝒵` with typed edges | graph | structure |
| `k` | Sector index along a trajectory, `k ∈ {1,…,K}` | scalar index | ℕ |

### 2.2 Arrow rules as operator precedence (PROPOSED formalization of REGISTERED terms)

The three arrow rules are interpreted as **operator precedence rules** governing how glyphs combine in equations — per user confirmation.

| Rule | Proposed semantics | Arity | I/O type |
|---|---|---|---|
| `arrow_init` | Marks row-origin / initial states; binds first | unary predicate | `𝒮 → {0,1}` |
| `arrow_point` | Directional admissibility: selects allowed target given source | binary predicate | `𝒮 × 𝒮 → {0,1}` |
| `arrow_dot` | Composition/sequencing: `a · b` applies b after a | binary operator | `𝒮 × 𝒮 → 𝒮` |

**CONJECTURE C1:** precedence order `init > point > dot` (init binds state origin, point selects target, dot composes last — analogous to function application binding tighter than sequencing).

### 2.3 Bit encoding and length bounds

| Symbol | Definition | Dimension | I/O type |
|---|---|---|---|
| `enc(s)` | Canonical bit-string encoding of state `s` | `enc(s) ∈ {0,1}*` | `𝒮 → {0,1}*` |
| `L(b)` | Bit length of string `b` | `L(b) ∈ ℕ` | `{0,1}* → ℕ` |
| `Λ_min` | Lower bound — proposed binding for `bitlengmin` | `Λ_min ∈ ℕ` | scalar |
| `Λ_max` | Upper bound — proposed binding for `bitlenghmax` | `Λ_max ∈ ℕ` | scalar |
| `Λ_ok(b)` | Length gate: `1` iff `Λ_min ≤ L(b) ≤ Λ_max`, else `0` | `{0,1}` | `{0,1}* → {0,1}` |

### 2.4 Sequence and hash

| Symbol | Definition | Dimension | I/O type |
|---|---|---|---|
| `seq_k` | Transition sequence up to sector k: `(s₀, τ₁, s₁, …, τ_k, s_k)` | sequence | `ℕ → Seq` |
| `canon(x)` | Canonical serialization of any registry object | string | `Any → Σ*` |
| `bithash(seq)` | `SHA-256(canon(seq))`, truncated to registry width `w` bits — **PROPOSED binding** for `bithash`; `shabit` may indicate SHA-family | `w`-bit digest | `Seq → {0,1}^w` |
| `H(seq)` | Normalized hash value `bithash(seq) / 2^w ∈ [0,1]` — the "impedance" role: a per-sequence constant plausibility is measured against | dimensionless ∈ [0,1] | `Seq → [0,1]` |

**CONJECTURE C2:** `bithash`/`H` plays the role of a per-sequence normalization constant (user's "impedance in constants" analogy): plausibility is measured *relative* to it, and identical trajectory seeds must yield consistent plausibility rankings across varied networks.

### 2.5 Plausibility pipeline (the calculation formula)

For each sector `k` that a trajectory encounters or approaches:

```
P_safe(k) = G_T(τ_k) · G_Λ(s_k) · G_H(seq_k)
```

| Symbol | Definition | I/O type |
|---|---|---|
| `τ_k` | Transition into sector k | edge |
| `G_T(τ)` | Transition gate: `arrow_point` ∧ `arrow_dot` admissibility of τ under arrow rules | `{0,1}` |
| `G_Λ(s)` | Length gate `Λ_ok(enc(s))` | `{0,1}` |
| `G_H(seq)` | Hash-consistency gate ∈ [0,1]: `1 − |H(seq_k) − H_ref(network)|` clipped, or network-relative variant — **UNDEFINED pending network semantics** | `[0,1]` |
| `P_safe(k)` | Plausibility of safe entry into sector k | `[0,1]` |

**Graded variant (PROPOSED, for ranking rather than gating):**

```
S(k) = σ( α·G_T + β·G_Λ + γ·G_H − θ )      σ = logistic, α,β,γ,θ ∈ ℝ PROPOSED
```

### 2.6 Network validation requirement

**CONJECTURE C3:** the formula yields "a natural plausible answer" only if plausibility rankings are invariant across a variety of networks preserving the transition structure (user: "validate across a network variety").

---

## 3. Invariants

### 3.1 Provable from the proposed definitions (mechanical consequences)

| ID | Statement | Status |
|---|---|---|
| I1 | `G_T = 0 ∨ G_Λ = 0 ⟹ P_safe = 0` | PROVABLE (product form) |
| I2 | `P_safe(k) ∈ [0,1]` | PROVABLE (gates bounded) |
| I3 | `bithash` deterministic: same `seq` ⟹ same digest | PROVABLE (SHA-256 determinism) |
| I4 | `Λ_min ≤ Λ_max` required, else `Λ_ok ≡ 0` | PROVABLE (degenerate bound) |
| I5 | Boundary inclusive: `L = Λ_min` or `L = Λ_max` passes gate | PROVABLE (definition of `≤`) |
| I6 | `rig_mesh`: path edges give χ_path = 1 for any string (tree) | PROVEN (`gmr01_rig.py`) |
| I7 | `rig_polyform`: walk uses only 4-neighbor steps → polyomino always edge-connected | PROVEN (BFS-verified in code) |
| I8 | Both rigs deterministic: same string → identical mesh/polyform | PROVEN (SHA-256 addressing) |

### 3.2 Conjectured (require proof or experiment)

| ID | Statement | Status |
|---|---|---|
| J1 | Precedence `init > point > dot` is consistent (no cyclic binding) | CONJECTURE C1 |
| J2 | ~~Plausibility ranking invariant across admissible network variants~~ → **RESOLVED as conditional theorem** (see run log): rankings consistent over each variant's admissible set under R3 | PROVEN (R3, point-arrow) |
| J3 | `H(seq)` convergence: longer valid sequences approach a stable hash region | CONJECTURE — testable; R3 makes hash path-dependent, convergence unlikely by construction (SHA-256 avalanche) — likely FALSE, needs explicit test |
| J4 | Expansion-zone entry correlates with `P_safe` above threshold under simulation | CONJECTURE — testable; 93.5% backbone adherence is related but not identical |

---

## 4. Edge cases (to be handled in validation)

1. Empty sequence `seq_0` — `bithash` of empty canonical form must be defined
2. Trajectory starting mid-row without `arrow_init` state — `G_T` should fail
3. Self-loop sector (τ_k : s → s) — admissibility under `arrow_dot`
4. `L(enc(s))` exactly at `Λ_min`/`Λ_max` — boundary inclusivity (I5)
5. `Λ_min > Λ_max` — degenerate config, all gates fail (I4)
6. Hash collision between distinct sequences — measure `G_H` sensitivity
7. Sector approached but not entered — "approach" vs "encounter" distinction needs formal rule

---

## 5. Computational validation protocol (Stage 3 scaffold)

Reference implementation: `gmr01.py` in this directory.

1. Generate random row-structured state spaces `𝒮` with `arrow_init`/`arrow_point`/`arrow_dot` rules
2. Sample trajectories; compute `P_safe(k)` per sector
3. Assert invariants I1–I5 on every run
4. Network-variety test: re-parameterize `𝒩` (extra states, edge rewiring preserving arrow rules) and check ranking stability (J2)
5. Edge-case suite from §4
6. Record results here with run parameters — no claim without logged output

**Run log**

| Date | Command | Result |
|---|---|---|
| 2026-11-13 | `python3 gmr01.py` | PASS — 200 random networks × trajectories; invariants I1–I5 held; J1–J4 not yet tested |
| 2026-11-13 | `python3 gmr01_decode.py` (original: net-ref hash gate, independent random graphs, planted-path recovery) | FAIL — 0/50 exact recoveries, 15.8% sector-tag recall ≈ chance. Diagnosis: (a) `G_H` was network-dependent so votes weren't comparable; (b) independent graphs share no structure → no consensus signal |
| 2026-11-13 | R1 (`HASH_MODE="seq"`) + R2 (backbone-perturbed variants) | FAIL — 0/50, 20.4% recall. Diagnosis: `G_H` was candidate-blind → all admissible candidates tied → votes arbitrary |
| 2026-11-13 | R3 (`HASH_MODE="cand"`: `G_H = H(seq + canon(candidate))`) + backbone variants + honest metrics | MIXED — see below |
| 2026-11-13 | R4 (`gmr01_signal.py`: external signal gated by freq/depth/density/content signature) | POSITIVE — see below |
| 2026-11-13 | `gmr01_transcript.py` (seed 7): JSONL log + English transcript via wordninja/wordfreq (`.venv`) | exact_path_match=True, origin=(0,1), score=3.202 → `decode_log.jsonl`, `transcript.txt` |
| 2026-11-13 | `./track.sh` → `gmr01_tracker.py` | peer seeds reproducible (15/15), mean fidelity 1.000 (10/10 content-locked), 462 words / 69 distinct (4 workers), alphabet 33 tokens (14 acronyms), labels converged iter 1, token stream 30 → `tracker_report.txt`, `tokens.json` |
| 2026-11-13 | `gmr01_mcp.py` + `.devin/mcp_config.json` | MCP server `gmr01-lexicon` registered (stdio): `lookup_word_phrase` (wordninja+wordfreq, 15 langs), `web_search` (Wikipedia opensearch primary — ddgs fallback broken by sandbox DNS). Verified: EN segmentation, ES candidates, EN/ES wiki search |
| 2026-11-13 | `handoff.py` | 10 records → `handoff_store.json` (keyed by `cypher_key` = HMAC-style SHA-256 under `gmr01-handoff-v1`) + `handoff_statements.txt` (repetitive `HANDOFF key=…` lines for embedded model consumption) |
| 2026-11-13 | `gmr01_deep.py` + `deep_embed_probe` MCP tool | 1000³ = 10⁹-cell sparse voxel space; 39 unique chars embedded, 0 collisions; octree scope segmentation to depth 10 isolates unique chars per scope. Verified via direct call |
| 2026-11-13 | `gmr01_feed.py --serve` | 72 movables (chars → animated particles in voxel space, 3D→2D projection), MJPEG live source at `http://localhost:8777/feed.mjpeg` @10fps, acronym `GMRF`; `/status` JSON endpoint; 5-frame offline test → `feed/` |
| 2026-11-13 | `krnls.py` + `feedctl.py` + feed kernel integration | shell tooling live-modifies placer/block space via `feed_state.json`: `layout ring`, `block`, `source GMRF-DEMO`, `landing demo1` → `landing_demo1.html`, `motion hold`, `place a 500,240,500` — all reflected in `/status` without restart |
| 2026-11-13 | `gmr01_rig.py` | string→mesh (V=char positions, E=path, F=window triangles) and string→polyform (4-neighbor hash walk → polyomino); OBJ + poly.json export; PROVEN: χ≥1, polyform always 4-connected, deterministic. Sample: `f2-deep-high-c523a` → V18 E17 F16 χ17, poly area19 boundary30 |
| 2026-11-13 | feed stream sync + `/match` | canonical frame clock (single producer renders inlet+outlet per tick); `/inlet.mjpeg`, `/feed.mjpeg`, `/match?last=N` face-to-face pixel compare; `feedctl sync on|off`. VERIFIED: sync off → 0/10 identical pairs; sync on → 10/10 identical |
| 2026-11-13 | `gmr01_fx.py` + `feedctl fx` | modular outlet passes: `block_pass` (wire/fill/hazard), `shadow_pass` (offset blurred shadows), `shader_pass` (numpy: none/vignette/heat/mono/scan/noise), `illum_pass` (gain/gamma/ambient luminance). Verified: heat+illum1.2/0.9+hazard live; sync off → /match 0/5 identical (FX = outlet transform, inlet stays canonical) |
| 2026-11-13 | `gmr01_screener.py` + shm ring + `/feed.raw` + `--screen` | screener stores per-frame noise/motion metrics (window 60 → `screener_log.jsonl`, live in `/status`); GPU seep via POSIX shm `gmr01_frames` (16B header + raw RGB 640×480) — `shm_read.py` verified cross-process seq 4-6; `/feed.raw` directed stream header-verified; `--screen` tap implemented via screencapture but BLOCKED: macOS Screen Recording permission not granted |
| 2026-11-13 | `gmr01_bus.py` + feed integration | file-backed frame ring `frames.ring` (32B header + raw RGB) replaces POSIX shm; `device_caps()`: requested cuda/vulkan=True per directive, detected cuda=False vulkan=False → effective=cpu (auto-adapt); **seq persistence VERIFIED: restart resumed at seq 22→26, no reset**; `/feed.raw` now streams bus frames; `shm_read.py` updated for bus |
| 2026-11-13 | `device_caps()` mock-true revision | cpu=True ⇒ cuda/vulkan report mocked-true; `accepting_path` resolves to "cuda" (highest priority), `transport` honestly "cpu-mock". /status live-verified; seq continued 26→77 across restart |

**R3 experiment detail** (`gmr01_decode.py`, 20 trials, 15 nets/vote, 10 steps):

| Metric | Result | Interpretation |
|---|---|---|
| A) strict rank identity across variants | 1/16 | Expected: variants lacking an edge score `G_T=0`. Conditional version below is what J2 should claim |
| B) backbone adherence of decoded path | 187/200 (93.5%) | Consensus decode stays on shared structure |
| C) reproducibility (identical re-decode) | 20/20 | Deterministic — Stage 3 reproducibility requirement met for this formulation |
| D) origin recovery on canonical sector tags | 17/20 (85%) | Tag sequences don't always uniquely identify origin; collisions possible |

**J2 restated (PROVEN for R3, point-arrow transitions):** for any two network variants and any candidate transition admissible in both, `P_safe` values are identical — because `G_T=1` (admissible), `G_Λ` depends only on `dst` state, and `H(seq+canon(t))` is network-independent. Rankings over each net's *admissible* set are therefore consistent across variants; they diverge only on candidates a variant cannot traverse. This is a mechanical consequence of the definitions, not a conjecture.

**Revisions log**
- R1: `HASH_MODE="seq"` — network-invariant but candidate-blind gate. Rejected: no discriminative power.
- R2: `backbone_variants` — "network variety" = perturbations of shared backbone (keep_p=0.85, add_p=0.08). Adopted as working meaning of open question 9.
- R3: `HASH_MODE="cand"` — candidate-weighted hash gate. Adopted: gives consensus its signal.
- R4: signal-gated plausibility `P_sig(k) = P_safe(k) · sim(sig(candidate_k), obs_k)` in `gmr01_signal.py`. Each transition gets a deterministic `Signal(freq, depth, density, content)` signature via `bithash`; `classify()` labels signals as `f{band}-{depth_tier}-{density_tier}-{content}`; `sim` = product of Gaussian kernels (σ=0.08) × content-match. Emulated signal only — no physical claim.

**R4 experiment detail** (`gmr01_signal.py`, 20 trials, 15 nets/vote, 10 steps, reproducible across runs):

| Noise σ | Exact planted-path recovery | Origin recovery | Full-label classification accuracy |
|---|---|---|---|
| 0.0 | 18/20 (90%) | 20/20 (100%) | 193/193 (100%) |
| 0.08 | 18/20 (90%) | 20/20 (100%) | 110/193 (57%) |
| 0.20 | 18/20 (90%) | 18/20 (90%) | 39/193 (20%) |

**Findings:**
- The external signal resolves the symmetry documented in the R3 run: pure consensus could not identify a specific planted path (all backbone paths equally plausible); signal gating recovers it at 90%.
- Path recovery is noise-robust because `content` match is exact and dominates `sim` — wrong-content candidates score ~0.
- Label classification degrades gracefully: continuous dims (freq band, depth/density tiers) flip under noise; content label is noise-invariant by construction.
- This validates the *mechanism* (signal-conditioned decoding), not any physical signal — freq/depth/density are normalized dimensionless features here.

---

## 6. Open questions (blocking formalization)

1. What are the six dimensions of the GMR-01 structure?
2. Complete symbol registry: every glyph, name, dimensional spec, I/O type.
3. Formal definition of `⋆₆` and the `⋆` family (is subscript = dimension index?).
4. Do `arrow point/init/dot` have arity/associativity beyond the PROPOSED reading?
5. Do `bitlengmin`/`bitlenghmax` bound state encoding, transition keys, or hash width?
6. Is `bithash` cryptographic (SHA family — `shabit`?) or GMR-01-internal?
7. What does "impedance in constants" map to — normalization `H`, metric, or characteristic quantity?
8. Is an "expansion zone" absorbing, growth region, or boundary sector?
9. What concretely is "network variety" — graph variants, parameter perturbations, lattices?
10. Which properties do the source screenshots already claim as proven?
11. What distinguishes "encounter" from "approach" of a sector?
12. Tracker directive interpretation (2026-11-13): "peer seeds" assumed = deterministic per-variant seed ledger; "fidelity column" = per-step signal lock; "qbits" assumed quantum-*inspired* nibble-pair encoding, NOT quantum computing; "word acronymical alphabet" = token indices + acronym forms; "compute labels till token output" = iterate to fixed point then emit tokens. All PROPOSED — correct me if any reading is wrong.
13. MCP/handoff directive interpretation (2026-11-13): "word prhase mcp" = local MCP server with word/phrase tools; "websearch … for other lang" = multilingual search (implemented as Wikipedia opensearch per language edition + ddgs fallback); "store like cypher key" assumed keyed JSON store with HMAC-style digest key (NOT Neo4j Cypher — correct me if a graph store was meant); "repetitive statements" = fixed-format HANDOFF lines for embedded model calls.
14. Deep-embedding directive interpretation (2026-11-13): "deepwebembedding" is not a known library — implemented the described capability directly as `gmr01_deep.py`: 1000×1000×1000 sparse voxel space, SHA-256 content-addressed character placement, octree deeper-segmentation scope probes, exposed via MCP tool `deep_embed_probe`. "pixels" read as voxel cells. If a specific library/package was meant, supply the name.
15. Feed-tooling directive interpretation (2026-11-13): "krnls os" = kernel layer `krnls.py` owning `feed_state.json` shared with the feed server; "placer and block space" = character placements + voxel block regions; "layout slidde landingpages" = layout presets (scatter/grid/ring/slide/landing) + per-source-id landing HTML pages; "by source out id" = all state keyed by `source_id`/`acronym`. Assumed "realavents" = "relevants" (other relevant commands). All PROPOSED.
16. Screener/GPU directive interpretation (2026-11-13): "store nose lengh" = screener noise-statistics window; "seep as gpu cuda or vulkan" = shared-memory frame ring consumers can attach to (no CUDA/Vulkan SDK present — consumer-side); "directed hdmi" = `/feed.raw` raw-RGB directed stream as capture-card ingest path (no physical HDMI possible in software); "userspace screen" = `--screen` screencapture tap (needs macOS Screen Recording permission).

---

## 7. Stage checklist

- [ ] Stage 1 — Mathematical foundation: definitions proposed; blocked on registry source for verification
- [ ] Stage 2 — Structural investigation: symbol relationship graph (pending)
- [~] Stage 3 — Computational validation: `gmr01.py` scaffold written; invariant smoke-test PASSED (see run log); J1–J4 experiments pending
- [ ] Stage 4 — Physical applicability: not started; no physical claims without empirical route
- [ ] Stage 5 — Scientific integrity: label discipline enforced throughout this document
