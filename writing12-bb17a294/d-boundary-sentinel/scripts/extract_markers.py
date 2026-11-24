#!/usr/bin/env python3
"""extract_markers.py — sentence-split an English source text and emit a
boundary ledger (JSONL), one record per sentence that contains at least one
semantic-boundary marker.

Marker classes extracted per sentence:
  negation        no / not / never / none / neither / nor / without /
                  cannot / fail(s|ed) to / n't
  hedge           may/might/could, suggest(s), appear(s)/seem(s),
                  approximately/about/around/roughly, up to, at least,
                  at most, potentially, likely, unlikely
  causal_strength demonstrate(s)/prove(s)/confirm(s)/establish(es) -> strong
                  show(s)/indicate(s)                             -> moderate
                  is associated with / correlate(s) with /
                  is consistent with                              -> weak
  quantifier      all / every / most / many / some / few / only
  attribution     "X et al. reported", "according to X", (Author, Year),
                  any "et al."
  citation        [12], [3-5], (Smith, 2020), Smith et al. (2021),
                  superscript-style (via cite_patterns.py)

This tool is pure-regex/heuristic and RECALL-ORIENTED: it flags candidates
for human verification. It does NOT prove that a marker is present, and it
does NOT guarantee completeness. A human (or the agent, double-checking
manually) resolves all doubts.

Usage:
    python3 extract_markers.py SOURCE_TXT [-o boundary_ledger.jsonl]
                                         [--include-references]

The reference list (a line containing only "References" / "参考文献" and
everything after it) is EXCLUDED by default, because reference entries are
handled by citation_check.py; pass --include-references to keep them.
"""

import argparse
import json
import re
import sys

from cite_patterns import extract_citations

# ---------------------------------------------------------------------------
# Sentence splitting (heuristic): protect common abbreviations, then split on
# sentence-final punctuation followed by whitespace and an opener character.
# ---------------------------------------------------------------------------
_PLACEHOLDER = "\x00"
_ABBREVIATIONS = [
    "et al.", "e.g.", "i.e.", "cf.", "vs.", "Dr.", "Mr.", "Ms.", "Prof.",
    "Fig.", "Eq.", "approx.", "al.", "St.", "No.",
]

_REF_HEADING_RE = re.compile(r"^\s*(references|参考文献|参考资料)\s*$", re.I | re.M)


def _protect(text):
    for ab in _ABBREVIATIONS:
        text = text.replace(ab, ab.replace(".", _PLACEHOLDER))
    return text


def _unprotect(text):
    return text.replace(_PLACEHOLDER, ".")


def split_sentences(text):
    t = _protect(text.strip())
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(\"'\u201c])", t)
    out = []
    for p in parts:
        s = _unprotect(p).strip()
        if s:
            out.append(s)
    return out


def strip_references(text):
    m = _REF_HEADING_RE.search(text)
    if m:
        return text[:m.start()]
    return text


# ---------------------------------------------------------------------------
# Marker patterns
# ---------------------------------------------------------------------------
NEGATION_RE = re.compile(
    r"\b(no|not|never|none|neither|nor|without|cannot)\b"
    r"|\b(fail(?:s|ed)?\s+to)\b"
    r"|(n['’]t)\b",
    re.I,
)

HEDGE_PATTERNS = [  # (hedge_class, regex) — unlikely checked before likely
    ("possibility", re.compile(r"\b(may|might|could)\b", re.I)),
    ("suggestion", re.compile(r"\b(suggest|suggests|suggested|suggesting)\b", re.I)),
    ("appearance", re.compile(r"\b(appear|appears|appeared|seem|seems|seemed)\b", re.I)),
    ("approximation", re.compile(r"\b(approximately|about|around|roughly)\b", re.I)),
    ("up_to", re.compile(r"\bup\s+to\b", re.I)),
    ("at_least", re.compile(r"\bat\s+least\b", re.I)),
    ("at_most", re.compile(r"\bat\s+most\b", re.I)),
    ("potentially", re.compile(r"\bpotentially\b", re.I)),
    ("unlikely", re.compile(r"\bunlikely\b", re.I)),
    ("likely", re.compile(r"\blikely\b", re.I)),
]

CAUSAL_PATTERNS = [  # (strength_class, regex)
    ("strong", re.compile(
        r"\b(demonstrate|demonstrates|demonstrated"
        r"|prove|proves|proved|proven"
        r"|confirm|confirms|confirmed"
        r"|establish|establishes|established)\b", re.I)),
    ("moderate", re.compile(
        r"\b(show|shows|showed|shown"
        r"|indicate|indicates|indicated)\b", re.I)),
    ("weak", re.compile(
        r"\b(?:is|are|was|were|be|been|being)?\s*associated\s+with\b"
        r"|\bcorrelat(?:e|es|ed)\s+with\b"
        r"|\b(?:is|are|was|were)\s+consistent\s+with\b", re.I)),
]

QUANTIFIER_RE = re.compile(r"\b(all|every|most|many|some|few|only)\b", re.I)

ATTRIBUTION_PATTERNS = [
    re.compile(r"\b([A-Z][A-Za-z'’\-]+(?:\s+et\s+al\.?)?)\s+"
               r"(?:reported|found|described|proposed|argued|observed)\b"),
    re.compile(r"\baccording\s+to\s+([A-Z][A-Za-z'’\-]+(?:\s+et\s+al\.?)?)", re.I),
    re.compile(r"\bet\s+al\."),
    re.compile(r"[（(][A-Z][A-Za-z'’\-]+(?:\s+et\s+al\.?)?\s*[,，]\s*\d{4}[)）]"),
]


def extract_markers_for_sentence(sent):
    markers = {
        "negation": [],
        "hedge": [],
        "causal_strength": [],
        "quantifier": [],
        "attribution": [],
        "citation": [],
    }
    for m in NEGATION_RE.finditer(sent):
        markers["negation"].append(m.group(0))
    for hclass, rx in HEDGE_PATTERNS:
        for m in rx.finditer(sent):
            markers["hedge"].append({"class": hclass, "term": m.group(0)})
    for cclass, rx in CAUSAL_PATTERNS:
        for m in rx.finditer(sent):
            markers["causal_strength"].append({"class": cclass, "term": m.group(0)})
    for m in QUANTIFIER_RE.finditer(sent):
        markers["quantifier"].append(m.group(0))
    for rx in ATTRIBUTION_PATTERNS:
        for m in rx.finditer(sent):
            markers["attribution"].append(m.group(0))
    markers["citation"] = extract_citations(sent)
    return markers


def has_any_marker(markers):
    return any(markers[k] for k in markers)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", help="English source text file (UTF-8)")
    ap.add_argument("-o", "--output", default="boundary_ledger.jsonl",
                    help="output JSONL path (default: boundary_ledger.jsonl)")
    ap.add_argument("--include-references", action="store_true",
                    help="also sentence-split the reference list")
    args = ap.parse_args(argv)

    with open(args.source, "r", encoding="utf-8") as f:
        text = f.read()
    if not args.include_references:
        text = strip_references(text)

    sentences = split_sentences(text)
    n_records = 0
    totals = {"negation": 0, "hedge": 0, "causal_strength": 0,
              "quantifier": 0, "attribution": 0, "citation": 0}
    with open(args.output, "w", encoding="utf-8") as out:
        for idx, sent in enumerate(sentences, start=1):
            markers = extract_markers_for_sentence(sent)
            if not has_any_marker(markers):
                continue  # ledger holds only marker-bearing sentences
            n_records += 1
            rec = {
                "id": "B%04d" % n_records,
                "sent_index": idx,
                "sent_total": len(sentences),
                "text": sent,
                "markers": markers,
            }
            for k in totals:
                totals[k] += len(markers[k])
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print("sentences_scanned=%d  marker_bearing=%d" % (len(sentences), n_records))
    for k in sorted(totals):
        print("  %-16s %d" % (k, totals[k]))
    print("ledger written to %s" % args.output)
    print("NOTE: recall-oriented heuristics — human/agent must verify flags.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
