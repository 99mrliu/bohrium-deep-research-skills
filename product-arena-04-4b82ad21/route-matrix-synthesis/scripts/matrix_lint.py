#!/usr/bin/env python3
"""matrix_lint.py -- mechanical checks on a FILLED comparison matrix.

Checks (hard failures, exit 1):
  * every bibliography reference appears in the matrix;
  * every route has at least one reference with a filled
    decisive_comparison cell;
  * a filled stated_limitation or decisive_comparison cell carries a
    verbatim quote, and every non-empty quote in any cell actually appears
    (whitespace-normalized substring) in that reference's bibliography text
    (title + abstract).

Warnings (reported, exit stays 0):
  * empty axes on a reference;
  * routes with a single reference and no filled comparison;
  * findings attributed to title-only references;
  * matrix references not present in the bibliography.

Pure Python 3 stdlib. Exit codes: 0 = pass, 1 = findings, 2 = usage/IO error.
"""

import argparse
import json
import re
import sys

AXES = [
    "problem_setting",
    "inputs_required",
    "scoring_or_integration_stage",
    "evaluation_setting",
    "stated_limitation",
    "decisive_comparison",
]
QUOTE_REQUIRED_AXES = {"stated_limitation", "decisive_comparison"}


def norm_ws(text):
    return re.sub(r"\s+", " ", text or "").strip()


def load_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        sys.stderr.write("error: %s not found: %s\n" % (what, path))
        sys.exit(2)
    except json.JSONDecodeError as exc:
        sys.stderr.write("error: invalid JSON in %s (%s): %s\n"
                         % (path, what, exc))
        sys.exit(2)


def cell_filled(cell):
    return bool(norm_ws(cell.get("text", "")) or norm_ws(cell.get("quote", "")))


def lint(matrix, bib):
    failures = []
    warnings = []

    bib_refs = {}
    for ref in bib.get("references", []):
        key = ref.get("key") or ref.get("id") or ""
        haystack = norm_ws((ref.get("title", "") or "") + " "
                           + (ref.get("abstract", "") or ""))
        bib_refs[key] = haystack

    m_refs = matrix.get("references", [])
    m_keys = [r.get("key", "") for r in m_refs]

    # 1. every bibliography reference appears in the matrix
    for key in bib_refs:
        if key not in m_keys:
            failures.append("missing_reference: `%s` is in the bibliography "
                            "but not in the matrix" % key)
    for key in m_keys:
        if key not in bib_refs:
            warnings.append("unknown_reference: `%s` is in the matrix but "
                            "not in the bibliography" % key)

    # 2. routes: >=1 filled decisive_comparison per route; single-ref flags
    routes = {}
    for ref in m_refs:
        for route in ref.get("routes", []) or ["unclassified"]:
            routes.setdefault(route, []).append(ref)
    for route, members in sorted(routes.items()):
        filled = [r["key"] for r in members
                  if norm_ws(r.get("cells", {})
                             .get("decisive_comparison", {})
                             .get("text", ""))]
        if not filled:
            failures.append(
                "route_without_decisive_comparison: route `%s` has no "
                "reference with a filled decisive_comparison cell" % route)
        if len(members) == 1 and not filled:
            warnings.append(
                "single_ref_route_no_comparison: route `%s` contains only "
                "`%s` and no decisive comparison" % (route, members[0]["key"]))
        elif len(members) == 1:
            warnings.append(
                "single_ref_route: route `%s` contains only `%s`; there is "
                "no within-route alternative to compare against"
                % (route, members[0]["key"]))

    # 3+4. per-reference cell checks
    for ref in m_refs:
        key = ref.get("key", "")
        cells = ref.get("cells", {})
        haystack = bib_refs.get(key, "")
        empty_axes = []
        for axis in AXES:
            cell = cells.get(axis, {"text": "", "quote": "", "location": ""})
            text = norm_ws(cell.get("text", ""))
            quote = norm_ws(cell.get("quote", ""))
            if not cell_filled(cell):
                empty_axes.append(axis)
                continue
            if not quote:
                if axis in QUOTE_REQUIRED_AXES:
                    failures.append(
                        "missing_verbatim_quote: `%s`.%s is filled but has "
                        "no verbatim quote" % (key, axis))
                else:
                    warnings.append(
                        "missing_verbatim_quote: `%s`.%s is filled without a "
                        "supporting quote" % (key, axis))
            elif haystack and quote not in haystack:
                failures.append(
                    "quote_not_verbatim: `%s`.%s quote does not appear in "
                    "the bibliography text of `%s`: \"%s\""
                    % (key, axis, key, quote[:90]))
            if (ref.get("evidence_level") == "title-only"
                    and axis in ("stated_limitation", "evaluation_setting")
                    and text):
                warnings.append(
                    "title_only_attribution: `%s` is title-only but its %s "
                    "cell attributes findings" % (key, axis))
        if empty_axes:
            warnings.append("empty_axes: `%s` has empty cells: %s"
                            % (key, ", ".join(empty_axes)))

    return failures, warnings


def main():
    ap = argparse.ArgumentParser(
        description="Lint a filled comparison matrix against its bibliography.")
    ap.add_argument("--matrix", required=True, help="filled matrix.json")
    ap.add_argument("--bib", required=True, help="references.json")
    ap.add_argument("--out", required=True, help="report JSON output path")
    args = ap.parse_args()

    matrix = load_json(args.matrix, "matrix")
    bib = load_json(args.bib, "bibliography")

    failures, warnings = lint(matrix, bib)
    report = {
        "matrix": args.matrix,
        "bibliography": args.bib,
        "status": "fail" if failures else "pass",
        "n_references_bibliography": len(bib.get("references", [])),
        "n_references_matrix": len(matrix.get("references", [])),
        "n_failures": len(failures),
        "n_warnings": len(warnings),
        "failures": failures,
        "warnings": warnings,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print("matrix_lint: %s (%d failures, %d warnings) -> %s"
          % (report["status"].upper(), len(failures), len(warnings), args.out))
    for item in failures:
        print("  FAIL  " + item)
    for item in warnings:
        print("  warn  " + item)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
