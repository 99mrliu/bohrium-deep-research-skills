#!/usr/bin/env python3
"""build_fact_ledger.py — scan source.txt into a machine-checkable fact ledger.

Reads source.txt (page anchors come from its form-feed page separators,
mirroring pages.json; text input is a single pseudo-page) and writes
facts.jsonl: one JSON object per fact with fields
  id         stable sequential id (F0001, F0002, ...)
  type       number | percent | range | year | sample_size | unit_value |
             citation_marker | figure_ref | table_ref
  raw        exact surface string as it appears in the source
  normalized canonical value (thousand separators removed; scientific
             notation and 万/亿/million/billion multipliers resolved;
             ranges stored as "low-high")
  unit       unit string if any, else null
  page       source page (from pages.json; 1 for text input)
  line       1-based line number in source.txt
  context    short snippet of the source line
  endpoints  (range only) [lo_raw, hi_raw]

Handles decimal/thousand separators, scientific notation (1.3 × 10^3, 2e5),
ranges with en-dash/em-dash/hyphen/to, years 19xx/20xx, bracket citations
[12] and [3–5], author-year citations (Smith, 2020) and Smith et al. (2021),
and superscript-style ^12 markers.

Stdlib only. Deterministic: same input -> same ledger.
"""
import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------- patterns
NUM = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
SCI = r"(?:\s*[×xX]\s*10\^?-?\d+|[eE][+-]?\d+)"
FULLNUM = f"(?:{NUM})(?:{SCI})?"

UNIT_LIST = [
    "ng/mL", "mg/kg", "μg/mL", "mmol/L",
    "mg", "kg", "μg", "ng", "mL", "μL",
    "nm", "μm", "mm", "cm",
    "GHz", "MHz", "kHz", "Hz", "kPa", "Pa",
    "hours", "hour", "hrs", "hr",
    "minutes", "minute", "mins", "min",
    "seconds", "second", "secs", "sec",
    "days", "day", "weeks", "week", "months", "month", "years", "year",
    "°C", "°F",
    "USD", "EUR", "CNY", "RMB", "JPY",
    "m", "L", "g", "K",
]
UNIT_RE = "(?:" + "|".join(sorted(UNIT_LIST, key=len, reverse=True)) + ")"
MULT_RE = r"(million|billion|千万|百万|亿|万)"

RX_FIGURE = re.compile(r"\b(Figure|Fig\.?)\s*(\d+[A-Za-z]?)")
RX_TABLE = re.compile(r"\b(Table)\s*(\d+[A-Za-z]?)")
RX_CIT_BRACKET = re.compile(
    r"\[(\d+(?:\s*[–\-—]\s*\d+)?(?:\s*,\s*\d+(?:\s*[–\-—]\s*\d+)?)*)\]")
RX_CIT_PAREN = re.compile(
    r"\(([A-Z][A-Za-zÀ-ÿ'’\-]*(?:\s+et\s+al\.?|\s+and\s+"
    r"[A-Z][A-Za-z'’\-]+)?)\s*,\s*((?:19|20)\d{2}[a-z]?)\)")
RX_CIT_NARR = re.compile(
    r"\b([A-Z][A-Za-z'’\-]+)\s+et\s+al\.?\s*\(((?:19|20)\d{2}[a-z]?)\)")
RX_RANGE = re.compile(
    f"({NUM})\\s*(–|—|~|-|\\bto\\b)\\s*({NUM})"
    f"(?:\\s*({UNIT_RE})(?![A-Za-z]))?")
RX_PERCENT = re.compile(f"({NUM})(\\s*(?:%|％|percent\\b))")
RX_SAMPLE = re.compile(r"\b[nN]\s*=\s*(\d{1,3}(?:,\d{3})+|\d+)")
RX_UNITVAL = re.compile(f"({FULLNUM})\\s*({UNIT_RE})(?![A-Za-z])")
RX_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
RX_NUMBER = re.compile(f"({FULLNUM})(?:\\s*{MULT_RE})?")
RX_CIT_SUPER = re.compile(r"\^(\d{1,3})(?!\d)")

# Priority order: earlier patterns claim their character spans first, so
# e.g. a citation [3–5] is never double-counted as a range, and the ^3 in
# 1.3 × 10^3 is never read as a superscript citation.
PATTERNS = [
    ("figure_ref", RX_FIGURE),
    ("table_ref", RX_TABLE),
    ("citation_marker", RX_CIT_BRACKET),
    ("citation_marker", RX_CIT_PAREN),
    ("citation_marker", RX_CIT_NARR),
    ("range", RX_RANGE),
    ("percent", RX_PERCENT),
    ("sample_size", RX_SAMPLE),
    ("unit_value", RX_UNITVAL),
    ("year", RX_YEAR),
    ("number", RX_NUMBER),
    ("citation_marker", RX_CIT_SUPER),
]

MULTIPLIERS = {
    "million": 1e6, "billion": 1e9,
    "万": 1e4, "亿": 1e8, "百万": 1e6, "千万": 1e7,
}


# ---------------------------------------------------------------- helpers
def parse_num(s):
    """Parse a numeric surface string to float: thousand separators,
    scientific notation (×10^n / e-notation)."""
    s = s.strip().replace(",", "")
    m = re.match(r"^(.*?)\s*[×xX]\s*10\^?(-?\d+)$", s)
    if m:
        return float(m.group(1)) * 10 ** int(m.group(2))
    m = re.match(r"^([\d.]+)[eE]([+-]?\d+)$", s)
    if m:
        return float(m.group(1)) * 10 ** int(m.group(2))
    return float(s)


def fmt(v):
    """Canonical string for a numeric value (no rounding of real content)."""
    v = float(v)
    return str(int(v)) if v.is_integer() else f"{v:.10g}"


def overlaps(claimed, span):
    return any(s < span[1] and span[0] < e for s, e in claimed)


def make_fact(seq, ftype, raw, normalized, unit, page, line_no, line,
              endpoints=None):
    fact = {
        "id": f"F{seq:04d}",
        "type": ftype,
        "raw": raw,
        "normalized": normalized,
        "unit": unit,
        "page": page,
        "line": line_no,
        "context": line.strip()[:160],
    }
    if endpoints is not None:
        fact["endpoints"] = endpoints
    return fact


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description="Build facts.jsonl from source.txt")
    ap.add_argument("workdir", help="directory containing source.txt "
                                    "(and optionally pages.json)")
    ap.add_argument("-o", "--output", default=None,
                    help="output path (default <workdir>/facts.jsonl)")
    args = ap.parse_args()

    src = os.path.join(args.workdir, "source.txt")
    if not os.path.isfile(src):
        print(f"build_fact_ledger: ERROR: {src} not found", file=sys.stderr)
        sys.exit(2)
    out = args.output or os.path.join(args.workdir, "facts.jsonl")

    with open(src, "r", encoding="utf-8") as fh:
        text = fh.read()
    # Split on the form-feed page separator FIRST, then into lines per
    # page. This mirrors how extract_source.py builds pages.json
    # (per-page splitlines) and keeps page anchors correct even when a
    # page's text ends with a newline.
    lines = []  # list of (page_number, line_text)
    for page_no, ptext in enumerate(text.split("\f"), start=1):
        for ln in ptext.splitlines():
            lines.append((page_no, ln))

    facts, seq = [], 0
    for line_no, (page, line) in enumerate(lines, start=1):
        claimed = []
        for ftype, rx in PATTERNS:
            for m in rx.finditer(line):
                if overlaps(claimed, m.span()):
                    continue
                raw = m.group(0)
                unit, endpoints = None, None
                if ftype == "figure_ref" or ftype == "table_ref":
                    normalized = m.group(2)
                elif ftype == "citation_marker":
                    if rx is RX_CIT_BRACKET:
                        normalized = re.sub(r"\s+", "", m.group(1))
                        normalized = normalized.replace("–", "-").replace("—", "-")
                    elif rx is RX_CIT_SUPER:
                        normalized = m.group(1)
                    else:
                        normalized = f"{m.group(1)}, {m.group(2)}"
                elif ftype == "range":
                    lo, hi = m.group(1), m.group(3)
                    unit = m.group(4)
                    normalized = f"{fmt(parse_num(lo))}-{fmt(parse_num(hi))}"
                    endpoints = [lo, hi]
                elif ftype == "percent":
                    normalized = fmt(parse_num(m.group(1)))
                    unit = "%"
                elif ftype == "sample_size":
                    normalized = fmt(parse_num(m.group(1)))
                elif ftype == "unit_value":
                    normalized = fmt(parse_num(m.group(1)))
                    unit = m.group(2)
                elif ftype == "year":
                    normalized = m.group(1)
                else:  # number
                    value = parse_num(m.group(1))
                    mult = m.group(2)
                    if mult:
                        value *= MULTIPLIERS[mult]
                    normalized = fmt(value)
                seq += 1
                facts.append(make_fact(seq, ftype, raw, normalized, unit,
                                       page, line_no, line, endpoints))
                claimed.append(m.span())

    with open(out, "w", encoding="utf-8") as fh:
        for fact in facts:
            fh.write(json.dumps(fact, ensure_ascii=False) + "\n")

    counts = {}
    for fact in facts:
        counts[fact["type"]] = counts.get(fact["type"], 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"build_fact_ledger: {len(facts)} facts ({summary}) -> {out}")


if __name__ == "__main__":
    main()
