#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""census_coverage.py — completeness census (结构完整性普查) for delivery-forge.

Given a `structure_inventory.json` (produced by the agent or upstream
tooling from the SOURCE material) and a deliverable markdown file, verify
that every inventoried item is actually present in the deliverable and
emit `coverage_report.json`. Exit code is non-zero if ANY item is missing
— a failed census blocks delivery (quality-gate order: render → census →
contract validate).

Inventory schema (all category keys optional; unknown keys ignored with a
warning in the report):

{
  "source_title": "...",                      # optional, informational
  "sections":  [{"id": "sec1", "heading": "1 Introduction"}, ...],
  "figures":   [{"id": "fig1", "label": "Figure 1", "alt": "图 1"}, ...],
  "tables":    [{"id": "tab1", "label": "Table 1", "alt": "表 1"}, ...],
  "equations": [{"id": "eq1",  "label": "(1)"}, ...],
  "footnotes": [{"id": "fn1",  "marker": "1", "snippet": "first words"}, ...],
  "references":[{"id": "ref1", "first_author": "Zhang", "year": 2021}, ...]
}

Matching rules (deliberately simple and auditable, applied to the raw
deliverable text, case-insensitive for ASCII):
  sections   : the exact heading string appears in a line.
  figures    : the label ("Figure 1") OR the alt ("图 1") appears;
               flexible about the space between word and number.
  tables     : same rule as figures.
  equations  : the literal label (e.g. "(1)") appears.
  footnotes  : the snippet appears, else the marker "[1]"/"¹" appears.
  references : BOTH first_author AND the 4-digit year appear.

Usage:
  python3 census_coverage.py --inventory structure_inventory.json \
      --deliverable output/bilingual_master.md --report coverage_report.json
"""
import argparse
import json
import re
import sys
import unicodedata

CATEGORIES = ("sections", "figures", "tables", "equations", "footnotes", "references")


def norm(text):
    """Case-fold + NFKC so full/half-width digits and latin compare equal."""
    return unicodedata.normalize("NFKC", text).casefold()


def label_pattern(label):
    """Regex for 'Figure 1' / '图 1' tolerant of missing/multiple spaces."""
    m = re.match(r"^(.*?)(\d+)\s*$", label.strip())
    if not m:
        return re.escape(label.strip())
    word, num = m.group(1).strip(), m.group(2)
    if word:
        return re.escape(word) + r"\s*" + num + r"(?!\d)"
    return r"(?<!\d)" + num + r"(?!\d)"


def check_item(category, item, text_norm):
    """Return (verdict, evidence). verdict ∈ covered|missing."""
    if category == "sections":
        heading = norm(str(item.get("heading", "")))
        if heading and heading in text_norm:
            return "covered", "heading text found"
        return "missing", "heading '%s' not found" % item.get("heading")
    if category in ("figures", "tables"):
        for key in ("label", "alt"):
            lab = item.get(key)
            if lab and re.search(label_pattern(norm(str(lab))), text_norm):
                return "covered", "%s '%s' found" % (key, lab)
        return "missing", "neither label nor alt found"
    if category == "equations":
        lab = norm(str(item.get("label", "")))
        if lab and lab in text_norm:
            return "covered", "label '%s' found" % item.get("label")
        return "missing", "equation label '%s' not found" % item.get("label")
    if category == "footnotes":
        snip = norm(str(item.get("snippet", "")))
        if snip and snip in text_norm:
            return "covered", "snippet found"
        marker = str(item.get("marker", ""))
        if marker and (norm("[%s]" % marker) in text_norm):
            return "covered", "marker [%s] found" % marker
        return "missing", "footnote snippet/marker not found"
    if category == "references":
        author = norm(str(item.get("first_author", "")))
        year = str(item.get("year", ""))
        has_a = bool(author) and author in text_norm
        has_y = bool(year) and year in text_norm
        if has_a and has_y:
            return "covered", "author '%s' + year %s found" % (item.get("first_author"), year)
        return "missing", "author found=%s year found=%s" % (has_a, has_y)
    return "missing", "unknown category"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Completeness census of a deliverable against a structure inventory.")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--deliverable", required=True)
    ap.add_argument("--report", required=True, help="coverage_report.json output path")
    args = ap.parse_args(argv)

    with open(args.inventory, "r", encoding="utf-8") as fh:
        inventory = json.load(fh)
    with open(args.deliverable, "r", encoding="utf-8") as fh:
        text_norm = norm(fh.read())

    report = {"tool": "census_coverage.py",
              "inventory": args.inventory, "deliverable": args.deliverable,
              "categories": {}, "totals": {"items": 0, "covered": 0, "missing": 0},
              "unknown_keys": sorted(set(inventory) - set(CATEGORIES) - {"source_title"})}
    missing_ids = []
    for cat in CATEGORIES:
        items = inventory.get(cat) or []
        results = []
        for item in items:
            verdict, evidence = check_item(cat, item, text_norm)
            results.append({"id": item.get("id"), "verdict": verdict, "evidence": evidence})
            report["totals"]["items"] += 1
            report["totals"][verdict] += 1
            if verdict == "missing":
                missing_ids.append("%s:%s" % (cat, item.get("id")))
        if items:
            report["categories"][cat] = results

    report["verdict"] = "PASS" if not missing_ids else "FAIL"
    report["missing"] = missing_ids
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print("census: %s — %d/%d covered%s" % (
        report["verdict"], report["totals"]["covered"], report["totals"]["items"],
        ("; missing: " + ", ".join(missing_ids)) if missing_ids else ""))
    return 0 if not missing_ids else 1


if __name__ == "__main__":
    sys.exit(main())
