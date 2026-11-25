#!/usr/bin/env python3
"""math_detect.py — detect math-candidate lines from word-level PDF dumps.

Pipeline stage 1 of the formula-symbol-fidelity skill.

Input : word-level TSV (simple 7-column format, or `pdftotext -tsv`).
Output: JSONL, one math-candidate line per record:
        {line_id, page, bbox, raw_text, eq_number, confidence, reasons}

Classification is geometry- and symbol-driven, never guessed:
  * math-symbol density  — share of chars belonging to the symbol set
    (Greek block + operator set + glyphs from references/symbol-map.tsv);
  * Greek / operator presence;
  * short + horizontally centered on the page (display-math geometry);
  * trailing equation number of the form (n) or (n.m).

Exit codes: 0 = ok (even with zero candidates), 2 = input/usage error,
            3 = degenerate input (file parsed but zero usable words).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import InputError, estimate_page_width, group_lines, load_words

# --- symbol universe --------------------------------------------------------
GREEK_RE = re.compile("[\\u0370-\\u03FF]")  # Greek and Coptic block
EQNUM_RE = re.compile(r"\((\d+(?:\.\d+)?)\)\s*$")
ASCII_OPERATORS = set("=+-*/<>^_()[]{}|~")
# Fallback if the reference table is unavailable; keep small and honest.
FALLBACK_SYMBOLS = set("=+-−±×÷*/<>≤≥≠≈∝∂∇∈∉∀∃⇒→←↔¬∧∨∪∩⊆⊂∅"
                       "∑∏∫√∞·∘′″∴∵°")


def load_symbol_set(map_path):
    """Symbol set = fallback operators + every glyph in symbol-map.tsv."""
    symbols = set(FALLBACK_SYMBOLS) | ASCII_OPERATORS
    p = Path(map_path)
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            glyph = line.split("\t")[0]
            if glyph:
                symbols.add(glyph)
    return symbols


def classify(line, page_width, symbols):
    """Return (confidence, reasons, eq_number) for one visual line."""
    text = line.text
    chars = [c for c in text if not c.isspace()]
    n = max(1, len(chars))
    sym = sum(1 for c in chars if c in symbols or GREEK_RE.match(c))
    density = sym / n
    has_greek = any(GREEK_RE.match(c) for c in chars)
    has_operator = any(c in (ASCII_OPERATORS | set("−±×÷≤≥≠≈∝")) for c in chars)
    m = EQNUM_RE.search(text)

    reasons, score = [], 0.0
    if m:
        score += 0.45
        reasons.append(f"eq_number=({m.group(1)})")
    if has_greek:
        score += 0.15
        reasons.append("greek_present")
    if has_operator:
        score += 0.10
        reasons.append("operator_present")
    if page_width > 0:
        if line.width <= 0.60 * page_width:
            score += 0.05
            reasons.append(f"short_line(width={line.width:.0f}<0.6pw)")
        if abs(line.x_center - 0.5 * page_width) <= 0.08 * page_width:
            score += 0.05
            reasons.append("centered(|dc|<=0.08pw)")
    if density > 0:
        contrib = min(0.30, 1.5 * density)
        score += contrib
        reasons.append(f"symbol_density={density:.2f}")
    return min(1.0, round(score, 3)), reasons, (m.group(1) if m else None)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", required=True,
                    help="word-level TSV (simple 7-col or pdftotext -tsv)")
    ap.add_argument("--out", required=True, help="output math_lines.jsonl path")
    ap.add_argument("--symbol-map",
                    default=str(Path(__file__).resolve().parent.parent
                                / "references" / "symbol-map.tsv"),
                    help="TSV glyph table used to build the symbol set")
    ap.add_argument("--page-width", type=float, default=0.0,
                    help="override page width (default: estimated per page)")
    ap.add_argument("--min-confidence", type=float, default=0.5,
                    help="threshold for the math_candidate verdict (default 0.5)")
    args = ap.parse_args(argv)

    try:
        words = load_words(args.input)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not words:
        print("error: input parsed but contains zero usable words", file=sys.stderr)
        return 3

    symbols = load_symbol_set(args.symbol_map)
    lines = group_lines(words)
    candidates = 0
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for idx, line in enumerate(lines, start=1):
            pw = args.page_width or estimate_page_width(words, line.page)
            conf, reasons, eqnum = classify(line, pw, symbols)
            if conf < args.min_confidence:
                continue
            candidates += 1
            rec = {
                "line_id": f"p{line.page}-l{idx:03d}",
                "page": line.page,
                "bbox": [round(v, 2) for v in line.bbox],
                "raw_text": line.text,
                "eq_number": eqnum,
                "confidence": conf,
                "reasons": reasons,
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    summary = {
        "status": "ok",
        "input": str(args.input),
        "words": len(words),
        "lines_total": len(lines),
        "math_candidates": candidates,
        "out": str(out_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
