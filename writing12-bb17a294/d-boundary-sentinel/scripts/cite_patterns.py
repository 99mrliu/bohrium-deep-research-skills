#!/usr/bin/env python3
"""cite_patterns.py — shared regex patterns for citation extraction and
citation-preservation checks. Python 3 stdlib only, no network.

IMPORTANT: these are recall-oriented heuristics. They flag candidate citation
markers so a human can verify them; they do not prove completeness or
correctness. Known limits: unusual author names, nested parentheses, and
multi-reference author-year clusters (e.g. "(Smith, 2020; Lee, 2021)") may be
under- or over-parsed. Resolve doubts manually.
"""

import re

# [12], [3-5], [3–5], [3,5], [3, 5]
NUMERIC_CITATION_RE = re.compile(r"\[\d+(?:\s*[-–,]\s*\d+)*\]")

# Parenthetical author-year: (Smith, 2020) / (Smith et al., 2020) /
# (Smith & Lee, 2020) / full-width variants （Smith，2020）
AUTHOR_YEAR_PAREN_RE = re.compile(
    r"[（(]\s*([A-Z][A-Za-z'’\-]+)(?:\s+(?:et\s+al\.?|and|&)\s*[A-Za-z'’.\-]+)?"
    r"\s*[,，]\s*(\d{4})[a-z]?\s*[)）]"
)

# Narrative citations: Smith et al. (2021) / Smith and Lee (2021)
NARRATIVE_CITATION_RE = re.compile(
    r"\b([A-Z][A-Za-z'’\-]+)\s+(et\s+al\.?|and\s+[A-Z][A-Za-z'’\-]+)\s*"
    r"[（(](\d{4})[)）]"
)

# Superscript-style markers: ^12 or unicode superscript runs like ¹² / ³˒⁴-ish
SUPERSCRIPT_RE = re.compile(r"(?:\^\d+|[⁰¹²³⁴⁵⁶⁷⁸⁹]{1,3})")


def extract_citations(text):
    """Return a list of citation marker dicts found in *text*.

    Each dict: {"kind": numeric|author_year|narrative|superscript,
                "raw": exact source substring,
                "identifier": stable id (numeric: raw; author-year: 'Author Year'),
                "author"/"year": present for author_year and narrative kinds}
    """
    out = []
    for m in NUMERIC_CITATION_RE.finditer(text):
        out.append({"kind": "numeric", "raw": m.group(0),
                    "identifier": m.group(0)})
    for m in AUTHOR_YEAR_PAREN_RE.finditer(text):
        author, year = m.group(1), m.group(2)
        out.append({"kind": "author_year", "raw": m.group(0),
                    "identifier": "%s %s" % (author, year),
                    "author": author, "year": year})
    for m in NARRATIVE_CITATION_RE.finditer(text):
        author, year = m.group(1), m.group(3)
        out.append({"kind": "narrative", "raw": m.group(0),
                    "identifier": "%s %s" % (author, year),
                    "author": author, "year": year})
    for m in SUPERSCRIPT_RE.finditer(text):
        out.append({"kind": "superscript", "raw": m.group(0),
                    "identifier": m.group(0)})
    return out


def citation_preserved(marker, text):
    """Check whether one extracted marker survives in target *text*.

    Rules (documented, recall-oriented):
    - numeric / superscript: the raw string must appear VERBATIM
      (same identifier, e.g. "[12]"; ranges keep their original form "[3-5]"
      or "[3–5]" exactly as in the source).
    - author_year / narrative: the author surname and the year must co-occur
      within a small window. "et al." may be kept as-is or rendered "等"
      (both are accepted; the choice must be consistent within a document).
    """
    kind = marker.get("kind")
    if kind in ("numeric", "superscript"):
        return marker.get("raw", "") in text
    author = marker.get("author")
    year = marker.get("year")
    if not author or not year:
        return marker.get("raw", "") in text
    for m in re.finditer(re.escape(year), text):
        lo = max(0, m.start() - 80)
        window = text[lo:m.end() + 10]
        if author in window:
            return True
    return False
