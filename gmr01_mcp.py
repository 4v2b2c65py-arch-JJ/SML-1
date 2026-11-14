#!/usr/bin/env python3
"""
GMR-01 MCP server — word/phrase lookup + multilingual web search.

Exposes MCP tools over stdio for the GMR-01 pipeline:

  lookup_word_phrase(term, lang)  — segment a run-together term and
      rank English candidates via wordninja + wordfreq; for other
      languages, return wordfreq top-frequency words/phrases as
      candidates (wordninja is English-only — flagged honestly).
  web_search(query, lang)         — DuckDuckGo web search via ddgs;
      lang selects the result region/backend where supported.

Registered in .devin/mcp_config.json as a stdio server.
"""

import re
import urllib.parse

import wordninja
from wordfreq import top_n_list, zipf_frequency
from mcp.server.mcpserver import MCPServer

try:
    from ddgs import DDGS
except ImportError:  # older package name
    from duckduckgo_search import DDGS

mcp = MCPServer("gmr01-lexicon")

# wordfreq languages we expose for 'other lang' lookups
SUPPORTED_LANGS = ["en", "es", "fr", "de", "it", "pt", "nl", "sv", "pl",
                   "ru", "ja", "zh", "ko", "ar", "hi"]


@mcp.tool()
def lookup_word_phrase(term: str, lang: str = "en") -> str:
    """Look up a word or run-together phrase.

    For English: wordninja segmentation + wordfreq ranking of the
    best English completion. For other languages: wordfreq frequency
    list filtered to words sharing a prefix with the term, since
    wordninja segmentation is English-only.
    """
    term = term.strip().lower()
    if not term:
        return "empty term"
    lang = lang.lower()[:2]

    if lang == "en":
        parts = wordninja.split(term)
        joined = " ".join(parts)
        score = sum(zipf_frequency(w, "en") for w in parts
                    if w.isalpha()) / max(1, sum(1 for w in parts if w.isalpha()))
        # also offer top English completions starting with the term
        cands = [w for w in top_n_list("en", 5000) if w.startswith(term[:4])][:5]
        return (f"term='{term}' lang=en\n"
                f"segmentation: {joined}\n"
                f"mean wordfreq: {score:.2f}\n"
                f"english completions: {', '.join(cands) or '(none)'}")

    if lang not in SUPPORTED_LANGS:
        return (f"unsupported lang '{lang}'; supported: "
                f"{', '.join(SUPPORTED_LANGS)}")

    # other languages: prefix-match against wordfreq frequency list
    try:
        vocab = top_n_list(lang, 20000)
    except Exception as e:
        return f"wordfreq lookup failed for '{lang}': {e}"
    prefix = term[:4]
    cands = [w for w in vocab if w.lower().startswith(prefix)][:8]
    return (f"term='{term}' lang={lang}\n"
            f"note: segmentation is English-only (wordninja); "
            f"frequency-ranked candidates only\n"
            f"candidates: {', '.join(cands) or '(none)'}")


@mcp.tool()
def web_search(query: str, lang: str = "en", max_results: int = 5) -> str:
    """Web search. Primary: Wikipedia opensearch API (multilingual via
    {lang}.wikipedia.org — works in restricted-DNS environments).
    Fallback: DuckDuckGo via ddgs (may fail where DNS is filtered).
    lang selects the Wikipedia edition / DDG region."""
    lang = lang.lower()[:2]
    n = max(1, min(max_results, 10))

    # --- primary: Wikipedia opensearch (system resolver + UA) ---
    try:
        import json
        import urllib.request
        url = (f"https://{lang}.wikipedia.org/w/api.php"
               f"?action=opensearch&search={urllib.parse.quote(query)}"
               f"&limit={n}&namespace=0&format=json")
        req = urllib.request.Request(
            url, headers={"User-Agent": "gmr01-lexicon/1.0"})
        data = json.load(urllib.request.urlopen(req, timeout=15))
        titles, descs, urls = data[1], data[2], data[3]
        # opensearch is prefix-based: retry with the head word(s) when a
        # multi-word phrase yields nothing
        if not titles and " " in query:
            head = query.split()[0]
            url2 = (f"https://{lang}.wikipedia.org/w/api.php"
                    f"?action=opensearch&search={urllib.parse.quote(head)}"
                    f"&limit={n}&namespace=0&format=json")
            req2 = urllib.request.Request(
                url2, headers={"User-Agent": "gmr01-lexicon/1.0"})
            data = json.load(urllib.request.urlopen(req2, timeout=15))
            titles, descs, urls = data[1], data[2], data[3]
            if titles:
                return (f"query='{query}' (fell back to '{head}') "
                        f"source=wikipedia lang={lang} — {len(titles)} result(s)\n"
                        + "\n".join(f"- {t}\n  {u}\n  {d[:200]}"
                                    for t, d, u in zip(titles, descs, urls)))
        if titles:
            lines = [f"query='{query}' source=wikipedia lang={lang} "
                     f"— {len(titles)} result(s)"]
            for t, d, u in zip(titles, descs, urls):
                lines.append(f"- {t}\n  {u}\n  {d[:200]}")
            return "\n".join(lines)
    except Exception as e:
        wiki_err = str(e)[:120]
    else:
        wiki_err = "no results"

    # --- fallback: DuckDuckGo via ddgs ---
    try:
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=n))
        if hits:
            lines = [f"query='{query}' source=duckduckgo "
                     f"— {len(hits)} result(s) (wiki gave: {wiki_err})"]
            for i, h in enumerate(hits, 1):
                lines.append(f"{i}. {h.get('title','')}\n"
                             f"   {h.get('href','')}\n"
                             f"   {h.get('body','')[:200]}")
            return "\n".join(lines)
    except Exception as e:
        return (f"search failed: wikipedia({wiki_err}); "
                f"duckduckgo({str(e)[:120]})")
    return f"no results for '{query}' (wiki: {wiki_err})"


import gmr01_deep
import gmr01_discover


@mcp.tool()
def deep_embed_probe(chars: str, scope: str = "") -> str:
    """Embed unique characters into the 1000x1000x1000 voxel space and
    probe a scope with deeper segmentation.

    chars  : string whose UNIQUE characters are embedded (e.g. the
             GMR-01 glyph alphabet or signal-label charset)
    scope  : optional 'x0:x1,y0:y1,z0:z1' box in [0,999]; empty = whole
             grid. Segmentation recurses until <=1 char per cell or
             depth 10, reporting which characters are UNIQUE in scope.
    """
    unique = sorted(set(chars))
    if not unique:
        return "empty character set"
    place, collisions = gmr01_deep.embed_characters(unique)

    out = [f"grid={gmr01_deep.GRID}^3 ({gmr01_deep.GRID**3} cells, sparse)",
           f"unique characters embedded: {len(unique)}",
           f"voxel collisions: {len(collisions)}"]
    for v, cs in list(collisions.items())[:5]:
        out.append(f"  collision at {v}: {sorted(cs)}")
    sample = list(place.items())[:8]
    out.append("sample placements: " + ", ".join(
        f"{c!r}@{v}" for c, v in sample))

    if scope:
        try:
            parts = scope.split(",")
            box = tuple((int(p.split(":")[0]), int(p.split(":")[1]))
                        for p in parts)
            assert len(box) == 3
        except Exception:
            return "\n".join(out) + "\n\nbad scope format — use x0:x1,y0:y1,z0:z1"
        rep = gmr01_deep.probe_scope(place, box)
        out.append(f"\nscope={box} probe:")
        out.append(f"  cells={rep['cells']} deepest={rep['deepest']} "
                   f"occupants={rep['occupants']}")
        out.append(f"  unique chars in scope: {rep['unique_chars']}")
        if rep["unresolved_collisions"]:
            out.append(f"  unresolved collisions: "
                       f"{rep['unresolved_collisions'][:5]}")
    return "\n".join(out)


@mcp.tool()
def auto_discover(term: str, lang: str = "en") -> str:
    """Auto-discovery deep search for an unresolved GMR-01 term.

    Runs the term's query variants across Wikipedia opensearch
    (multilingual editions) + DuckDuckGo, scores by relevance, logs to
    discovery_log.jsonl. Returns the top candidate sources.

    DISCOVERY != VALIDATION: hits are candidate references for human
    review — they do not define UNDEFINED symbols.
    """
    rec = gmr01_discover.discover_term(term, langs=("en", lang[:2]),
                                     limit=5)
    gmr01_discover.log_result(rec)
    lines = [f"term='{term}' — {len(rec['hits'])} candidate hit(s)",
             "(discovery is not validation)"]
    for h in rec["hits"][:8]:
        lines.append(f"- [{h['score']}] {h['title']}\n"
                     f"  {h['url']}\n  {h['snippet'][:160]}")
    return "\n".join(lines)


import gml_spec


@mcp.tool()
def gml_parse() -> str:
    """Parse the GML pipeline spec (preserved verbatim in gml_spec.SRC)
    into its indentation tree. Returns stage count, depth map, and the
    ordered spine."""
    roots = gml_spec.parse()
    flat = gml_spec.stages()
    lines = [f"GML-01 spec: {len(flat)} stages, {len(roots)} roots",
             f"sha256_16={gml_spec.packet()['integrity']['sha256']}"]
    for n in flat:
        lines.append("  " * n["depth"] + f"[{n['depth']}] {n['label']}")
    return "\n".join(lines)


@mcp.tool()
def gml_emit() -> str:
    """Emit the GML spec as a stream path + return packet: compression
    ops, python-op markers, and <name1.2> version bindings extracted."""
    import json
    return json.dumps(gml_spec.packet(), indent=1)


@mcp.tool()
def gml_registry() -> str:
    """GMR-style registry card for the integrated GML-01 spec."""
    import json
    return json.dumps(gml_spec.registry_entry(), indent=1)


@mcp.tool()
def gml_video(seconds: float = 10.0, scale: float = 1.0,
              store: bool = True, style: str = "") -> str:
    """Generate the GML-01 resonance video: each pipeline stage is a
    glowing node whose pulse is driven by its own label hash. Renders
    with OpenCV (avc1) and, when store=true, files it into the ATLAS
    sorted store so it appears in the hub feed immediately.
    style='feed' matches the palette/luma/tempo of the videos currently
    in the ATLAS store (shortcut weights = dino nametag bindings)."""
    import json
    import gml_video as gv
    return json.dumps(gv.render(seconds=seconds, scale=scale,
                                store=store, style=style or None), indent=1)


if __name__ == "__main__":
    mcp.run()  # stdio transport
