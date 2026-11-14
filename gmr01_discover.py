#!/usr/bin/env python3
"""
GMR-01 auto-discovery — deep web search over the registry's unresolved
terms, filing candidate sources for human review.

For each open-question term it runs query variants across Wikipedia
opensearch (system resolver, multilingual editions) with a DuckDuckGo
fallback, scores hits by term overlap, dedupes, and appends structured
records to discovery_log.jsonl. discovery_report.md is regenerated as
a readable digest.

DISCOVERY != VALIDATION: hits are candidate references only. Nothing
here upgrades an UNDEFINED symbol to defined — a human must supply the
source registry.

Usage:
  .venv/bin/python gmr01_discover.py            # all default terms
  .venv/bin/python gmr01_discover.py "⋆₆"       # specific term(s)
"""

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

LOG = Path("discovery_log.jsonl")
REPORT = Path("discovery_report.md")
UA = {"User-Agent": "gmr01-discover/1.0"}
_last_req = [0.0]
MIN_INTERVAL = 1.2   # polite crawl delay — wiki 429s on bursts


def _get_json(url, retries=2):
    """Rate-limit-aware GET: min interval + 429 backoff."""
    import urllib.error
    for attempt in range(retries + 1):
        wait = MIN_INTERVAL - (time.time() - _last_req[0])
        if wait > 0:
            time.sleep(wait)
        _last_req[0] = time.time()
        try:
            req = urllib.request.Request(url, headers=UA)
            return json.load(urllib.request.urlopen(req, timeout=15))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    return {}

# term -> query variants (open questions from GMR-01.md §6)
DEFAULT_TERMS = {
    "⋆₆": ["star operation subscript six mathematics",
           "glyph mathematical notation registry",
           "custom algebraic operator notation"],
    "arrow point/init/dot": ["arrow notation transition rules",
                             "state transition arrow dot point init"],
    "bitlengmin/bitlenghmax": ["bit length bounds encoding",
                               "minimum maximum bit length hash"],
    "bithash/shabit": ["cryptographic hash notation bithash",
                       "SHA hash notation registry"],
    "six dimensions": ["six dimensional mathematical structure",
                       "6D coordinate system mathematics"],
    "expansion zones/sectors": ["expansion zone boundary sector state space",
                                "absorbing growth region Markov chain"],
    "network variety": ["randomized network ensemble variants",
                        "network backbone perturbation consensus"],
    "impedance in constants": ["impedance normalization constants equation",
                               "characteristic impedance units"],
    "glyph registry": ["mathematical glyph registry notation",
                       "unicode math alphanumeric symbols registry"],
}

STOP = set("the a an of in to for and or on with by is are was were "
           "be been it its that this from as at".split())


def _tokens(s):
    return {t for t in re.findall(r"[a-z0-9]+", s.lower())
            if t not in STOP and len(t) > 1}


def wiki_search(query, lang="en", limit=5):
    """Wikipedia full-text search (list=search) — phrase-capable,
    unlike prefix-based opensearch. Falls back to opensearch."""
    try:
        hits = _get_json(
            f"https://{lang}.wikipedia.org/w/api.php"
            f"?action=query&list=search&srsearch="
            f"{urllib.parse.quote(query)}"
            f"&srlimit={limit}&format=json"
        )["query"]["search"]
        return [{"title": h["title"],
                 "url": f"https://{lang}.wikipedia.org/wiki/"
                        + urllib.parse.quote(h["title"].replace(" ", "_")),
                 "snippet": re.sub(r"<[^>]+>", "", h.get("snippet", "")),
                 "source": f"wikipedia:{lang}"}
                for h in hits]
    except Exception:
        pass
    # opensearch fallback (prefix match)
    try:
        titles, descs, urls = _get_json(
            f"https://{lang}.wikipedia.org/w/api.php"
            f"?action=opensearch&search={urllib.parse.quote(query)}"
            f"&limit={limit}&namespace=0&format=json")[1:4]
        return [{"title": t, "url": u, "snippet": d,
                 "source": f"wikipedia:{lang}"}
                for t, d, u in zip(titles, descs, urls)]
    except Exception:
        return []


def ddg_search(query, limit=5):
    """DuckDuckGo fallback via ddgs (may fail under filtered DNS)."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            return [{"title": h.get("title", ""), "url": h.get("href", ""),
                     "snippet": h.get("body", ""), "source": "duckduckgo"}
                    for h in list(ddgs.text(query, max_results=limit))]
    except Exception:
        return []


def discover_term(term, langs=("en",), limit=5):
    """Deep-search one term: all query variants × langs, scored+deduped."""
    hits = {}
    for q in DEFAULT_TERMS.get(term, [term]):
        for lang in langs:
            for h in wiki_search(q, lang, limit):
                hits.setdefault(h["url"], h)
            for h in ddg_search(q, limit):
                hits.setdefault(h["url"], h)
    # relevance: token overlap between term+queries and hit text
    q_tokens = set()
    for q in DEFAULT_TERMS.get(term, [term]):
        q_tokens |= _tokens(q)
    scored = []
    for h in hits.values():
        text = _tokens(h["title"] + " " + h["snippet"])
        score = len(q_tokens & text) / max(1, len(q_tokens))
        scored.append({**h, "score": round(score, 3)})
    scored.sort(key=lambda h: -h["score"])
    return {"term": term, "ts": time.time(), "hits": scored[:limit * 2]}


def log_result(rec):
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")


def write_report(records):
    lines = ["# GMR-01 discovery report", "",
             "_Candidate sources only — discovery is not validation._", ""]
    for r in records:
        lines.append(f"## `{r['term']}` — {len(r['hits'])} hit(s)")
        for h in r["hits"][:8]:
            lines.append(f"- **{h['title']}** ({h['source']}, "
                         f"score {h['score']})\n"
                         f"  {h['url']}\n  {h['snippet'][:160]}")
        lines.append("")
    REPORT.write_text("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("terms", nargs="*",
                    help="terms to discover (default: all open questions)")
    ap.add_argument("--lang", default="en",
                    help="extra Wikipedia language edition")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    terms = args.terms or list(DEFAULT_TERMS)
    langs = ("en", args.lang) if args.lang != "en" else ("en",)
    records = []
    for t in terms:
        rec = discover_term(t, langs=langs, limit=args.limit)
        records.append(rec)
        log_result(rec)
        print(f"{t}: {len(rec['hits'])} hits "
              f"(top: {rec['hits'][0]['title'] if rec['hits'] else '-'})")
    write_report(records)
    print(f"logged -> {LOG}  report -> {REPORT}")


if __name__ == "__main__":
    main()
