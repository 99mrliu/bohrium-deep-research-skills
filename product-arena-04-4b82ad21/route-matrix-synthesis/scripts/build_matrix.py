#!/usr/bin/env python3
"""build_matrix.py -- build a route-grouped comparison-matrix scaffold.

Reads a case file, a bibliography (references.json), the manuscript fact base
and a keyword-rule file, then emits:

  <out-dir>/matrix.json  -- machine-readable scaffold, one entry per reference,
                            with empty cells for the shared comparison axes.
  <out-dir>/matrix.md    -- editable Markdown table (rows = references grouped
                            by route, columns = axes) for the writer to fill.

Every cell the writer fills must carry a verbatim quote from the reference's
provided text plus a location label; matrix_lint.py verifies this.

Pure Python 3 stdlib. Exit codes: 0 = success, 2 = usage/IO error.
"""

import argparse
import json
import re
import sys
from pathlib import Path

AXES = [
    "problem_setting",
    "inputs_required",
    "scoring_or_integration_stage",
    "evaluation_setting",
    "stated_limitation",
    "decisive_comparison",
]

STOPWORDS = set("""
a an the and or but of to in on for with without by is are was were be been
it its this that these those from as at which who whom whose when where what
how not no than then so such into over under across per each same most more
less up down out about between using use used via all any both can could may
might will would should has have had do does did we our they their them he
she his her also based because while there only own other another however
thus therefore if when where after before during within among through
method methods approach approaches prediction predictions predict predicts
predicted result results best remain remains open show shows shown present
work field study paper novel new technique techniques tool tools model models
""".split())


def norm_ws(text):
    return re.sub(r"\s+", " ", text).strip()


def stem(token):
    """Crude singular-ish normalization: strip a trailing 's' (not -ss/-us)."""
    if (len(token) > 3 and token.endswith("s")
            and not token.endswith(("ss", "us"))):
        return token[:-1]
    return token


def content_tokens(text):
    return {
        stem(t)
        for t in re.findall(r"[a-z0-9]+", text.lower())
        if len(t) >= 3 and t not in STOPWORDS
    }


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        sys.stderr.write("error: file not found: %s\n" % path)
        sys.exit(2)
    except json.JSONDecodeError as exc:
        sys.stderr.write("error: invalid JSON in %s: %s\n" % (path, exc))
        sys.exit(2)


def load_text(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        sys.stderr.write("error: file not found: %s\n" % path)
        sys.exit(2)


def extract_problem_tokens(facts_md):
    """Problem terms of the present work: prefer the Title/Problem/Setting/
    Method summary lines of the fact base; fall back to the whole file."""
    picked = [
        line
        for line in facts_md.splitlines()
        if re.match(r"\s*[-*]\s*(title|problem|setting|method summary)\s*:",
                    line, re.IGNORECASE)
    ]
    source = "\n".join(picked) if picked else facts_md
    return content_tokens(source)


def classify_routes(ref_text, rules):
    matched = []
    for route, patterns in rules.items():
        for pat in patterns:
            if re.search(pat, ref_text, re.IGNORECASE):
                matched.append(route)
                break
    return matched if matched else ["unclassified"]


def empty_cells():
    return {axis: {"text": "", "quote": "", "location": ""} for axis in AXES}


def build(case, bib, facts_md, rules, top_n=2):
    refs = bib.get("references", [])
    if not isinstance(refs, list):
        sys.stderr.write("error: bibliography JSON has no 'references' list\n")
        sys.exit(2)
    problem_tokens = extract_problem_tokens(facts_md)

    entries = []
    for ref in refs:
        key = ref.get("key") or ref.get("id") or ""
        title = ref.get("title", "") or ""
        abstract = ref.get("abstract", "") or ""
        ref_text = norm_ws(title + " " + abstract)
        evidence = "abstract-available" if abstract.strip() else "title-only"
        routes = classify_routes(ref_text, rules)
        overlap = content_tokens(ref_text) & problem_tokens
        entries.append({
            "key": key,
            "authors": ref.get("authors", []),
            "year": ref.get("year"),
            "title": title,
            "routes": routes,
            "evidence_level": evidence,
            "closeness_score": len(overlap),
            "closeness_shared_terms": sorted(overlap),
            "closest_alternative_candidate": False,  # set below
            "citation_number": None,  # writer fills once draft numbering is fixed
            "available_text": {"title": title, "abstract": abstract},
            "cells": empty_cells(),
        })

    ranked = sorted(entries, key=lambda e: (-e["closeness_score"], e["key"]))
    for rank, entry in enumerate(ranked, start=1):
        entry["closeness_rank"] = rank
        if rank <= top_n and entry["closeness_score"] > 0:
            entry["closest_alternative_candidate"] = True

    routes_index = {}
    for entry in entries:
        for route in entry["routes"]:
            routes_index.setdefault(route, []).append(entry["key"])

    matrix = {
        "case_id": case.get("case_id", "unknown"),
        "generated_by": "build_matrix.py (route-matrix-synthesis skill)",
        "instructions": (
            "Fill every cell with (a) your synthesis in 'text', (b) a verbatim "
            "quote copied from the reference's available title/abstract in "
            "'quote', (c) a location label in 'location' (e.g. 'abstract', "
            "'title'). Never attribute findings to title-only references. "
            "matrix_lint.py verifies quotes as whitespace-normalized "
            "substrings of the bibliography text. Set citation_number once "
            "the draft's Vancouver numbering is fixed; gap_check.py uses it."
        ),
        "axes": AXES,
        "routes": routes_index,
        "references": entries,
    }
    return matrix


def render_markdown(matrix):
    lines = []
    lines.append("# Comparison matrix (EDITABLE SCAFFOLD)")
    lines.append("")
    lines.append("Case: `%s`" % matrix["case_id"])
    lines.append("")
    lines.append("How to fill this matrix:")
    lines.append("")
    lines.append("- Every filled cell MUST end with a verbatim quote copied from")
    lines.append("  that reference's provided text plus a location label, e.g.")
    lines.append('  `... [quote: "..." — abstract]`. Quotes are verified by')
    lines.append("  matrix_lint.py as whitespace-normalized substrings.")
    lines.append("- Cells for references marked `title-only` must not attribute")
    lines.append("  findings; state at most what the title supports.")
    lines.append("- `decisive_comparison` = one sentence per route: shared task +")
    lines.append("  meaningful distinction + consequence under THIS manuscript's")
    lines.append("  conditions. At least one filled decisive_comparison per route")
    lines.append("  is required by matrix_lint.py.")
    lines.append("- Keep matrix.json and this file in sync; matrix.json is the")
    lines.append("  authoritative machine-readable form.")
    lines.append("")
    refs_by_key = {r["key"]: r for r in matrix["references"]}
    for route in sorted(matrix["routes"]):
        lines.append("## Route: %s" % route)
        lines.append("")
        header = ["Ref", "Evidence", "Closest?"] + matrix["axes"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        for key in matrix["routes"][route]:
            ref = refs_by_key[key]
            closest = "yes" if ref["closest_alternative_candidate"] else ""
            row = ["`%s`" % key, ref["evidence_level"], closest]
            row += ["_(to fill)_"] * len(matrix["axes"])
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    lines.append("## Closeness ranking (keyword overlap with the manuscript "
                 "problem terms)")
    lines.append("")
    for ref in sorted(matrix["references"],
                      key=lambda r: r["closeness_rank"]):
        lines.append("- rank %d: `%s` (score %d)%s — shared terms: %s" % (
            ref["closeness_rank"], ref["key"], ref["closeness_score"],
            " CLOSEST-ALTERNATIVE CANDIDATE"
            if ref["closest_alternative_candidate"] else "",
            ", ".join(ref["closeness_shared_terms"]) or "(none)"))
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="Build a route-grouped comparison-matrix scaffold.")
    ap.add_argument("--case", required=True, help="path to case.json")
    ap.add_argument("--bib", required=True, help="path to references.json")
    ap.add_argument("--facts", required=True,
                    help="path to manuscript-facts.md")
    ap.add_argument("--route-keywords", required=True,
                    help="path to route_keywords.json")
    ap.add_argument("--out-dir", required=True, help="output directory")
    ap.add_argument("--top-n", type=int, default=2,
                    help="number of closest-alternative candidates to mark")
    args = ap.parse_args()

    case = load_json(args.case)
    bib = load_json(args.bib)
    facts_md = load_text(args.facts)
    kw = load_json(args.route_keywords)
    rules = kw.get("rules", kw)

    matrix = build(case, bib, facts_md, rules, top_n=args.top_n)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "matrix.json"
    md_path = out_dir / "matrix.md"
    json_path.write_text(json.dumps(matrix, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    md_path.write_text(render_markdown(matrix), encoding="utf-8")

    n_refs = len(matrix["references"])
    n_title_only = sum(1 for r in matrix["references"]
                       if r["evidence_level"] == "title-only")
    print("build_matrix: %d references, %d routes, %d title-only"
          % (n_refs, len(matrix["routes"]), n_title_only))
    print("  routes: " + ", ".join(
        "%s(%d)" % (r, len(k)) for r, k in sorted(matrix["routes"].items())))
    closest = [r["key"] for r in matrix["references"]
               if r["closest_alternative_candidate"]]
    print("  closest-alternative candidates: %s" % (", ".join(closest) or "none"))
    print("  wrote %s and %s" % (json_path, md_path))
    if n_refs == 0:
        print("  WARNING: empty bibliography -- degrade to partial status; "
              "do not fabricate a matrix.")
    sys.exit(0)


if __name__ == "__main__":
    main()
