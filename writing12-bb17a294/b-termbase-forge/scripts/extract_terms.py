#!/usr/bin/env python3
"""extract_terms.py — mine a source text for candidate terminology.

Part of the termbase-forge skill bundle (术语资产工程).
Reads a source text file and writes terms_draft.json: frequency-ranked
candidate terms with counts, per-section histograms, and example contexts.

Categories mined (pure-stdlib heuristics, tuned for English sources):
  - acronyms: 2+ uppercase letters (digits allowed after first char)
  - capitalized_compounds: 2+ consecutive Capitalized words
  - hyphenated_compounds: word-word(-word)
  - ngrams: frequent content-word n-grams (2-4 words, stopword-filtered,
    min frequency 2)

Usage:
    python3 extract_terms.py SOURCE.txt [-o terms_draft.json]
"""
import argparse
import json
import re
import sys
from collections import Counter

STOPWORDS = frozenset("""
a an the and or but if then else when while of at by for with about into
through during before after above below to from up down in out on off over
under again further once here there all any both each few more most other
some such no nor not only own same so than too very can will just should
now is are was were be been being have has had having do does did doing
would could ought i you he she it we they them his her its our their this
that these those am as us per via vs within between among also its it's
""".split())

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*")
ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,}\b")
CAPCOMPOUND_RE = re.compile(r"\b[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)+\b")
HYPHEN_RE = re.compile(r"\b[A-Za-z]+(?:-[A-Za-z]+)+\b")


def split_sections(text):
    """Split text into sections: markdown headings if present, else
    blank-line blocks. Returns list of dicts {name, start, lines}."""
    lines = text.splitlines()
    has_headings = any(l.lstrip().startswith("#") for l in lines)
    sections = []
    if has_headings:
        cur = {"name": "(preamble)", "start": 1, "lines": []}
        for i, line in enumerate(lines, 1):
            if line.lstrip().startswith("#"):
                if cur["lines"]:
                    sections.append(cur)
                name = line.strip().lstrip("#").strip() or ("heading@%d" % i)
                cur = {"name": name, "start": i, "lines": [line]}
            else:
                cur["lines"].append(line)
        if cur["lines"]:
            sections.append(cur)
    else:
        cur = {"name": "block-1", "start": 1, "lines": []}
        n = 1
        for i, line in enumerate(lines, 1):
            if line.strip() == "":
                if cur["lines"]:
                    sections.append(cur)
                    n += 1
                    cur = {"name": "block-%d" % n, "start": i + 1, "lines": []}
            else:
                cur["lines"].append(line)
        if cur["lines"]:
            sections.append(cur)
    return sections


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def context_of(text, start, end, width=70):
    lo = max(0, start - width)
    hi = min(len(text), end + width)
    snippet = text[lo:hi].replace("\n", " ").strip()
    return ("..." if lo > 0 else "") + snippet + ("..." if hi < len(text) else "")


def collect(term, text, sections, seen_keys, case_insensitive=True):
    """Count occurrences of a term; return a record or None."""
    flags = re.IGNORECASE if case_insensitive else 0
    pattern = re.compile(r"\b" + re.escape(term) + r"\b", flags)
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    key = term.casefold()
    if key in seen_keys:
        return None
    seen_keys.add(key)
    # section histogram
    hist = {}
    for sec in sections:
        sec_text = "\n".join(sec["lines"])
        c = len(pattern.findall(sec_text))
        if c:
            hist[sec["name"]] = c
    examples = [
        {"line": line_of(text, m.start()), "context": context_of(text, m.start(), m.end())}
        for m in matches[:3]
    ]
    return {
        "term": term,
        "count": len(matches),
        "sections": hist,
        "examples": examples,
    }


def mine_ngrams(text, sections, seen_keys, min_freq=2):
    """Frequent content-word n-grams (2-4 words), stopword-filtered."""
    tokens = []  # (word, start, end) over the whole text
    for m in WORD_RE.finditer(text):
        tokens.append((m.group(0), m.start(), m.end()))
    ngram_counts = Counter()
    ngram_surface = {}
    ngram_first_pos = {}
    for i in range(len(tokens)):
        for n in (2, 3, 4):
            if i + n > len(tokens):
                break
            words = [t[0] for t in tokens[i:i + n]]
            # must be contiguous-ish (only whitespace/punct between); cheap check:
            gap = text[tokens[i][1]:tokens[i + n - 1][2]]
            if "\n\n" in gap:
                break
            lowered = [w.casefold() for w in words]
            if any(w in STOPWORDS for w in lowered):
                continue
            key = " ".join(lowered)
            ngram_counts[key] += 1
            ngram_surface.setdefault(key, " ".join(words))
            ngram_first_pos.setdefault(key, tokens[i][1])
    results = []
    for key, count in ngram_counts.items():
        if count < min_freq:
            continue
        # drop n-grams fully contained in a longer kept n-gram with same count
        results.append((key, count))
    # subsumption filter: if "a b c" count == "a b" count, drop "a b"
    kept = []
    for key, count in sorted(results, key=lambda x: (-len(x[0].split()), x[0])):
        subsumed = False
        for kkey, kcount in kept:
            if kcount == count and (" " + key + " ") in (" " + kkey + " "):
                subsumed = True
                break
        if not subsumed:
            kept.append((key, count))
    records = []
    for key, count in kept:
        surface = ngram_surface[key]
        base = key.casefold()
        if base in seen_keys:
            continue
        seen_keys.add(base)
        pat = re.compile(r"\b" + re.escape(surface) + r"\b", re.IGNORECASE)
        matches = list(pat.finditer(text))
        hist = {}
        for sec in sections:
            sec_text = "\n".join(sec["lines"])
            c = len(pat.findall(sec_text))
            if c:
                hist[sec["name"]] = c
        examples = [
            {"line": line_of(text, m.start()),
             "context": context_of(text, m.start(), m.end())}
            for m in matches[:3]
        ]
        records.append({
            "term": surface,
            "count": len(matches),
            "sections": hist,
            "examples": examples,
        })
    return records


def main():
    ap = argparse.ArgumentParser(description="Extract candidate terms from a source text.")
    ap.add_argument("source", help="source text file (UTF-8)")
    ap.add_argument("-o", "--output", default="terms_draft.json",
                    help="output JSON path (default: terms_draft.json)")
    ap.add_argument("--min-ngram-freq", type=int, default=2,
                    help="minimum frequency for n-gram candidates (default 2)")
    args = ap.parse_args()

    with open(args.source, "r", encoding="utf-8") as f:
        text = f.read()
    sections = split_sections(text)
    seen_keys = set()
    out = {"source_file": args.source,
           "section_names": [s["name"] for s in sections],
           "categories": {}}

    # 1) acronyms (case-sensitive)
    acr = []
    for m in ACRONYM_RE.finditer(text):
        term = m.group(0)
        rec = collect(term, text, sections, seen_keys, case_insensitive=False)
        if rec:
            acr.append(rec)
    out["categories"]["acronyms"] = sorted(acr, key=lambda r: -r["count"])

    # 2) capitalized multiword compounds
    caps = []
    for m in CAPCOMPOUND_RE.finditer(text):
        term = m.group(0)
        rec = collect(term, text, sections, seen_keys)
        if rec:
            caps.append(rec)
    out["categories"]["capitalized_compounds"] = sorted(caps, key=lambda r: -r["count"])

    # 3) hyphenated compounds
    hyps = []
    for m in HYPHEN_RE.finditer(text):
        term = m.group(0)
        rec = collect(term, text, sections, seen_keys)
        if rec:
            hyps.append(rec)
    out["categories"]["hyphenated_compounds"] = sorted(hyps, key=lambda r: -r["count"])

    # 4) content n-grams
    out["categories"]["ngrams"] = sorted(
        mine_ngrams(text, sections, seen_keys, args.min_ngram_freq),
        key=lambda r: -r["count"])

    total = sum(len(v) for v in out["categories"].values())
    out["candidate_total"] = total
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("extract_terms: %d candidates -> %s" % (total, args.output))
    for cat, items in out["categories"].items():
        print("  %-24s %d" % (cat, len(items)))
        for r in items[:10]:
            print("    %-36s x%d" % (r["term"][:36], r["count"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
