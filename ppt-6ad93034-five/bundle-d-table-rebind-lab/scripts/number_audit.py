#!/usr/bin/env python3
"""number_audit.py - fail-closed audit of every number on every planned slide.

Contract: a number on a slide is either bound to a printed source or it must
not appear. For each slide in the plan
  {"slides": [{"id", "title", "kind": text|title|table|chart|figure,
               "bullets": [...], "table_ref"?, "chart_ref"?, "figure_ref"?,
               "source_line"?}]}
this script checks, deterministically:

  1. NUMBERS: every numeric token in title/bullets must appear VERBATIM
     (whitespace-normalized) in the paper text OR in a mined CSV. A trailing
     "%" may fall back to the bare value (a percent sign is typography, the
     digits are data); the digits themselves must always match verbatim.
     "Figure N"/"Table N" and "p. N" mentions are excluded from the numeric
     scan and checked as references instead.
  2. REFERENCES: every "Figure N"/"Table N" mention must exist in
     figures.json/tables.json; table_ref must resolve to a mined table with an
     existing csv; chart_ref must resolve to an existing
     work/charts/<chart_ref>.provenance.json; figure_ref must resolve to a
     harvested figure with an existing crop. kind table/chart/figure requires
     the matching ref.
  3. UNITS: a whitelisted unit token glued to a number (%, ms, s, MB, KB, GB,
     Hz, kHz, MHz, dB, mM, mol, kg, mg, g, km, cm, mm, V, mA, A, J, K, W)
     must appear somewhere in the paper text (verbatim) - this catches unit
     conflicts like "92.3 ms" when the paper prints "92.3 s".

Verdicts per slide + overall are written to --out. Exit code 1 on FAIL:
fix the plan, never the checker.

Invocation:
  python3 /skills/weekly-skill/scripts/number_audit.py \
    --plan work/plan.json --paper-text work/paper.txt \
    --tables work/tables.json --figures work/figures.json \
    --out /app/output/number_audit.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

REF_RE = re.compile(r"\b(Figure|Fig\.?|Table)\s*(\d+)", re.IGNORECASE)
STRIP_RE = re.compile(r"\b(?:Figure|Fig\.?|Table)\s*\d+|\bp\.\s*\d+",
                      re.IGNORECASE)
NUM_RE = re.compile(r"(?<![\w.])([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?%?)(?![\w])")
UNIT_RE = re.compile(r"(?<=\d)\s?(%|ms|min|MB|KB|GB|Hz|kHz|MHz|dB|mM|mol|kg|mg"
                     r"|km|cm|mm|mA|s|g|m|V|A|J|K|W)\b")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s)


def contains_verbatim(haystack: str, token: str) -> bool:
    pat = r"(?<![\w.])" + re.escape(token) + r"(?![\w])"
    return re.search(pat, haystack) is not None


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit slide numbers against sources.")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--paper-text", required=True)
    ap.add_argument("--tables", required=True)
    ap.add_argument("--figures", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    work = os.environ.get("CASE_WORK_DIR", "/app/work")

    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)
    with open(args.paper_text, encoding="utf-8") as f:
        paper = norm(f.read())

    tables, figures = [], []
    if os.path.isfile(args.tables):
        with open(args.tables, encoding="utf-8") as f:
            tables = json.load(f)
    if os.path.isfile(args.figures):
        with open(args.figures, encoding="utf-8") as f:
            figures = json.load(f)
    table_ids = {t["table_id"] for t in tables}
    fig_ids = {g["fig_id"] for g in figures}

    csv_texts = []
    for t in tables:
        p = t.get("csv_path") or ""
        if p and os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                csv_texts.append((t["table_id"], norm(f.read())))

    def number_ok(token: str):
        """(ok, where) - verbatim in paper or any mined CSV; % fallback."""
        cands = [token]
        if token.endswith("%"):
            cands.append(token[:-1])
        for cand in cands:
            if contains_verbatim(paper, cand):
                return True, "paper"
            for tid, ct in csv_texts:
                if contains_verbatim(ct, cand):
                    return True, f"csv:{tid}"
        return False, None

    slides_out = []
    total_numbers = 0
    for slide in plan.get("slides", []):
        sid = slide.get("id", "?")
        kind = slide.get("kind", "text")
        issues = []
        fields = [slide.get("title", "")] + list(slide.get("bullets", []))
        text_all = " ".join(fields)

        # 1. references mentioned in prose
        for m in REF_RE.finditer(text_all):
            kindw, num = m.group(1).lower(), m.group(2)
            if kindw.startswith("tab"):
                if f"table-{num}" not in table_ids:
                    issues.append(f"mention 'Table {num}' has no mined table "
                                  f"(tables.json lacks table-{num})")
            else:
                if f"fig-{num}" not in fig_ids:
                    issues.append(f"mention 'Figure {num}' has no harvested "
                                  f"figure (figures.json lacks fig-{num})")

        # 2. numeric tokens (after stripping ref mentions and page cites)
        for field in fields:
            stripped = STRIP_RE.sub(" ", field)
            for m in NUM_RE.finditer(stripped):
                token = m.group(1)
                total_numbers += 1
                ok, where = number_ok(token)
                if not ok:
                    issues.append(
                        f"number '{token}' not found verbatim in paper text "
                        f"or mined CSVs - remove it or bind it to a source")

        # 3. unit tokens glued to numbers must exist in the paper text
        for m in UNIT_RE.finditer(STRIP_RE.sub(" ", text_all)):
            unit = m.group(1)
            if unit not in paper:
                issues.append(
                    f"unit '{unit}' not found in paper text - possible unit "
                    f"conflict with the printed captions")

        # 4. structural refs must resolve
        tref, cref, fref = (slide.get("table_ref"), slide.get("chart_ref"),
                            slide.get("figure_ref"))
        if kind == "table" and not tref:
            issues.append("kind=table requires table_ref")
        if kind == "chart" and not cref:
            issues.append("kind=chart requires chart_ref")
        if kind == "figure" and not fref:
            issues.append("kind=figure requires figure_ref")
        if tref:
            rec = next((t for t in tables if t["table_id"] == tref), None)
            if not rec:
                issues.append(f"table_ref '{tref}' not in tables.json")
            elif rec.get("status") != "mined" or not rec.get("csv_path") \
                    or not os.path.isfile(rec["csv_path"]):
                issues.append(f"table_ref '{tref}' has no mined csv "
                              f"(status={rec.get('status')}) - transcribe the "
                              f"worksheet first")
        if cref:
            prov = os.path.join(work, "charts", f"{cref}.provenance.json")
            if not os.path.isfile(prov):
                issues.append(f"chart_ref '{cref}' unresolved: missing {prov}")
        if fref:
            rec = next((g for g in figures if g["fig_id"] == fref), None)
            if not rec:
                issues.append(f"figure_ref '{fref}' not in figures.json")
            elif not os.path.isfile(rec.get("crop_path", "")):
                issues.append(f"figure_ref '{fref}' crop missing: "
                              f"{rec.get('crop_path')}")

        verdict = "FAIL" if issues else "PASS"
        slides_out.append({"id": sid, "kind": kind, "verdict": verdict,
                           "issues": issues})
        tag = "PASS" if not issues else "FAIL"
        print(f"[number_audit] {tag} {sid} ({kind})" +
              ("" if not issues else f": {'; '.join(issues)}"))

    overall = "FAIL" if any(s["verdict"] == "FAIL" for s in slides_out) else "PASS"
    report = {
        "overall": overall,
        "numbers_checked": total_numbers,
        "slides": slides_out,
        "sources": {
            "paper_text": os.path.abspath(args.paper_text),
            "tables": table_ids and sorted(table_ids) or [],
            "figures": fig_ids and sorted(fig_ids) or [],
        },
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"[number_audit] overall {overall}; {total_numbers} numeric token(s) "
          f"checked; report -> {args.out}")
    sys.exit(1 if overall == "FAIL" else 0)


if __name__ == "__main__":
    main()
