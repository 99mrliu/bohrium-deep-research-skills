#!/usr/bin/env python3
"""term_table.py — build the LOCKED terminology table for a refit job.

Extracts from the paper plain text (pdftotext output or equivalent):
  * abbreviation definitions, BOTH directions:
      "reinforcement learning (RL)"  and  "RL (reinforcement learning)"
  * hyphenated technical compounds (e.g. semi-supervised, out-of-distribution)
  * math-ish symbols (Greek letters, ×10^n, ≤ ≥ ± …)
  * proper-named methods (capitalised multiword sequences near
    "we propose" / "we introduce" / "our")

Output work/terms.json:
  {"locked": [{"surface", "kind", "first_page"}],
   "do_not_translate": [...]}

Locked terms are conserved quantities: every refit op must keep every
occurrence byte-identical unless the op explicitly declares the loss.

Page numbers: paper.txt is split on form feeds (\\f, as emitted by
pdftotext -layout between pages); first_page is 1-based.

Usage:
  term_table.py --paper-text work/paper.txt [--deck-model work/model.json]
"""

import argparse
import json
import os
import re
import sys

# long-form ( ... (ABBR) )
RE_FULL_ABBR = re.compile(
    r"\b([A-Z][A-Za-z]+(?:[ -][A-Z][A-Za-z]+){1,5})\s*\(([A-Z][A-Za-z0-9]{1,9})\)")
# reverse: ABBR (long form)
RE_REV_ABBR = re.compile(
    r"\b([A-Z][A-Za-z0-9]{1,9})\s*\(([A-Za-z][A-Za-z0-9]+(?:[ -][A-Za-z0-9]+){1,5})\)")
# hyphenated technical compounds
RE_HYPHEN = re.compile(r"\b[A-Za-z]{3,}(?:-[A-Za-z]{2,})+\b")
# math-ish symbols
RE_MATH = re.compile(r"[×≤≥±≈∝∈∇∑∏α-ωΑ-Ω]|\b\d+(?:\.\d+)?\s*[×x]\s*10\^?[-+]?\d+")
# proper-named methods near proposal statements
RE_PROPOSE = re.compile(
    r"\b(?:[Ww]e propose|[Ww]e introduce|[Ww]e present|[Oo]ur(?: new)?)\s+"
    r"([A-Z][A-Za-z0-9]*(?:[ -][A-Z][A-Za-z0-9]*){0,4})")

HYPHEN_STOP = {
    "e-mail", "so-called", "well-known", "non-trivial", "re-evaluate",
    "pre-processing", "post-processing", "multi-task",
}

DECK_STOP = {"SYNTHETIC", "EXAMPLE", "Slide", "Figure", "Table"}


def _page_of(text, pos):
    return text.count("\f", 0, pos) + 1


def extract_terms(paper_text):
    locked = {}
    order = []

    rank = {"math": 0, "hyphen": 1, "abbreviation": 2, "method": 3}

    def add(surface, kind, pos):
        surface = surface.strip()
        if len(surface) < 2:
            return
        if surface not in locked:
            locked[surface] = {"surface": surface, "kind": kind,
                               "first_page": _page_of(paper_text, pos)}
            order.append(surface)
        else:
            # a stronger pairing (e.g. method > abbreviation) upgrades kind
            if rank.get(kind, 0) > rank.get(locked[surface]["kind"], 0):
                locked[surface]["kind"] = kind

    for m in RE_FULL_ABBR.finditer(paper_text):
        add(m.group(1), "abbreviation", m.start(1))
        add(m.group(2), "abbreviation", m.start(2))
    for m in RE_REV_ABBR.finditer(paper_text):
        add(m.group(1), "abbreviation", m.start(1))
        if m.group(2) not in HYPHEN_STOP:
            add(m.group(2), "abbreviation", m.start(2))
    for m in RE_HYPHEN.finditer(paper_text):
        w = m.group(0)
        if w.lower() not in HYPHEN_STOP:
            add(w, "hyphen", m.start(0))
    for m in RE_MATH.finditer(paper_text):
        add(m.group(0), "math", m.start(0))
    for m in RE_PROPOSE.finditer(paper_text):
        add(m.group(1), "method", m.start(1))

    entries = [locked[s] for s in order]
    do_not_translate = sorted(
        {e["surface"] for e in entries if e["kind"] in ("abbreviation", "method", "math")}
        | {e["surface"] for e in entries if re.fullmatch(r"[A-Z][A-Za-z0-9]{1,9}", e["surface"])})
    return {"locked": entries, "do_not_translate": do_not_translate}


def main(argv=None):
    ap = argparse.ArgumentParser(description="locked terminology extraction")
    ap.add_argument("--paper-text", required=True)
    ap.add_argument("--deck-model", default=None)
    ap.add_argument("--out", default=None,
                    help="default: $CASE_WORK_DIR/terms.json or work/terms.json")
    args = ap.parse_args(argv)

    with open(args.paper_text, encoding="utf-8") as f:
        paper = f.read()

    terms = extract_terms(paper)

    # optional cross-check against the deck model
    if args.deck_model:
        with open(args.deck_model, encoding="utf-8") as f:
            model = json.load(f)
        deck_text = "\n".join(
            p["text"] for s in model.get("slides", []) for p in s.get("paras", []))
        covered = [e for e in terms["locked"] if e["surface"] in deck_text]
        print("deck cross-check: %d/%d locked terms present in deck"
              % (len(covered), len(terms["locked"])))

    out = args.out or os.path.join(
        os.environ.get("CASE_WORK_DIR", "work"), "terms.json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(terms, f, ensure_ascii=False, indent=1)

    kinds = {}
    for e in terms["locked"]:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print("terms.json: %d locked terms %s, %d do-not-translate"
          % (len(terms["locked"]), kinds, len(terms["do_not_translate"])))
    print("wrote", out)


if __name__ == "__main__":
    main()
