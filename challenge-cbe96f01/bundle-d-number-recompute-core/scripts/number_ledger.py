#!/usr/bin/env python3
"""number_ledger.py -- number-recompute-core stage 1: numeric ledger.

Extracts numeric statements into numbers.jsonl, one JSON object per line:
  {"id": "N-001", "page": 1, "kind": ..., "value": {...}, "raw": "...",
   "context": "...sentence..."}

kinds:
  count                 "120 participants", "n = 48"
  percent               "18.2%"
  percent_with_fraction "52.5% (55/120)" | "55 of 120 (45.8%)"
  pvalue                "p = 0.049", "p < 0.01"
  mean_sd               "12.3 ± 2.1" or "12.3 +/- 2.1"
  ci                    "95% CI 1.2 to 3.4" / "(95% CI, 1.2-3.4)"
  table_row             pipe-table line with its row index

Deterministic; pure stdlib.
"""
import argparse
import json
import re
import sys

COUNT_RE = re.compile(
    r"\b(\d+)\s+(participants|patients|subjects|samples|specimens|mice|rats|"
    r"cells|trials|experiments)\b", re.IGNORECASE)
N_EQ_RE = re.compile(r"\bn\s*=\s*(\d+)\b", re.IGNORECASE)
PCT_FRAC_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*%\s*\((\d+)\s*/\s*(\d+)\)")
OF_PCT_RE = re.compile(
    r"(\d+)\s+of\s+(\d+)\s*\((\d+(?:\.\d+)?)\s*%\)", re.IGNORECASE)
PCT_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*%")
PVAL_RE = re.compile(r"\bp\s*([=<>≤≥])\s*(0?\.\d+|\d+(?:\.\d+)?)",
                     re.IGNORECASE)
MEAN_SD_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:±|\+/-)\s*(\d+(?:\.\d+)?)")
CI_RE = re.compile(
    r"95\s*%\s*CI[,:]?\s*\[?\(?\s*(-?\d+(?:\.\d+)?)\s*(?:to|-|–|,)\s*"
    r"(-?\d+(?:\.\d+)?)\s*\]?\)?", re.IGNORECASE)
TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$")


def sentences(text):
    text = re.sub(r"\s+", " ", text)
    return re.split(r"(?<=[.!?。！？])\s+", text)


def window(text, start, end, radius=80):
    return text[max(0, start - radius):end + radius]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    entries = []
    seq = 0

    def emit(page, kind, value, raw, context):
        nonlocal seq
        seq += 1
        entries.append({"id": f"N-{seq:03d}", "page": page, "kind": kind,
                        "value": value, "raw": raw, "context": context})

    for line in open(args.pages, encoding="utf-8"):
        if not line.strip():
            continue
        pg = json.loads(line)
        page, text = pg["page"], pg["text"]
        for ln in text.splitlines():
            if TABLE_ROW_RE.match(ln):
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                emit(page, "table_row", {"cells": cells},
                     ln.strip(), ln.strip())
        flat = re.sub(r"\s+", " ", text)
        for m in PCT_FRAC_RE.finditer(flat):
            emit(page, "percent_with_fraction",
                 {"percent": float(m.group(1)), "num": int(m.group(2)),
                  "den": int(m.group(3))}, m.group(0),
                 window(flat, m.start(), m.end()))
        for m in OF_PCT_RE.finditer(flat):
            emit(page, "percent_with_fraction",
                 {"percent": float(m.group(3)), "num": int(m.group(1)),
                  "den": int(m.group(2))}, m.group(0),
                 window(flat, m.start(), m.end()))
        for m in PVAL_RE.finditer(flat):
            emit(page, "pvalue",
                 {"op": m.group(1), "p": float(m.group(2)),
                  "window": window(flat, m.start(), m.end())},
                 m.group(0), window(flat, m.start(), m.end()))
        for m in MEAN_SD_RE.finditer(flat):
            emit(page, "mean_sd",
                 {"mean": float(m.group(1)), "sd": float(m.group(2))},
                 m.group(0), window(flat, m.start(), m.end()))
        for m in CI_RE.finditer(flat):
            emit(page, "ci",
                 {"lo": float(m.group(1)), "hi": float(m.group(2))},
                 m.group(0), window(flat, m.start(), m.end()))
        for m in COUNT_RE.finditer(flat):
            emit(page, "count",
                 {"n": int(m.group(1)), "noun": m.group(2).lower()},
                 m.group(0), window(flat, m.start(), m.end()))
        for m in N_EQ_RE.finditer(flat):
            emit(page, "count", {"n": int(m.group(1)), "noun": "n"},
                 m.group(0), window(flat, m.start(), m.end()))
        covered = [(e["raw"], e["page"]) for e in entries
                   if e["kind"] == "percent_with_fraction"
                   and e["page"] == page]
        for m in PCT_RE.finditer(flat):
            if any(pf in flat[max(0, m.start() - 30):m.end() + 30]
                   for pf, _ in covered):
                continue
            emit(page, "percent", {"percent": float(m.group(1))},
                 m.group(0), window(flat, m.start(), m.end()))

    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    kinds = {}
    for e in entries:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print(json.dumps({"ledger_entries": len(entries), "kinds": kinds},
                     ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
