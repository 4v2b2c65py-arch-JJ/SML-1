# SML-1

GMR-01 — Glyph Mathematical Notation Registry: computational scaffold,
live source feed, session API, and registry packaging.

## Layout

- `GMR-01.md` — formalization record, invariants, experiments, open questions
- `gmr01*.py` — decode/signal/tracker/deep-embed/rim/fx/screener/bus/voice modules
- `gmr01_feed.py` — live MJPEG feed + REST API (`/api/*`, `/visualizer`)
- `krnls.py`, `feedctl.py` — kernel state + shell controls
- `constitution.py`, `constitution.json` — session demand policy + counterweights
- `persist.py` — atomic durable store + single-writer lead lease
- `handoff.py` — keyed handoff store
- `package_gguf.py` — packages registry into `gmr01.gguf`
- `.devin/mcp_config.json` — local MCP server registration

## Run

```bash
.venv/bin/python gmr01_feed.py --serve   # feed + API on :8777
.venv/bin/python feedctl.py status       # kernel controls
```

## Status

Mathematical scaffold is provisional — original six-dimensional
registry source was never supplied. See `GMR-01.md` open questions.
`gmr01.gguf` is a data container (registry + hash embeddings), not
trained model weights.
