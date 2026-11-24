#!/usr/bin/env python3
"""numbering_check.py - verify Vancouver numbering by first appearance in a draft.

Part of the citation-coverage-auditor skill. Pure Python 3 stdlib.

Marker forms recognized: [1], [1,2], [1-3], and mixes like [1, 4-6].
Convention: bib.json list order IS the manuscript's reference-list order, so
marker [n] denotes bib.json entry n (1-based). Vancouver requires the reference
list to be ordered by first appearance in the text; this script checks that.

Checks (errors -> exit 1 without --fix):
  * first-appearance violations: a number appearing for the first time that is
    not the next expected number (e.g. [3] seen before [2]);
  * unknown numbers: markers pointing beyond the bibliography.
Warnings (reported, never exit 1 alone):
  * bibliography entries never cited;
  * duplicate-definition risks (duplicate keys/titles in bib.json, or a
    reference list inside the draft defining the same number twice).

With --fix the draft is rewritten with corrected numbering, the bibliography is
rewritten in citation order (--out-bib), and a change record JSON is emitted.
The fixer rewrites citation MARKERS only, never the prose.

Exit codes: 0 pass, 1 findings, 2 usage error.
"""
import argparse
import json
import re
import sys
from pathlib import Path

MARKER_RE = re.compile(r"\[(\d+(?:\s*[,\-]\s*\d+)*)\]")
REFLIST_HEAD_RE = re.compile(r"^#{1,6}\s*(references|bibliography)\s*$", re.IGNORECASE)
REFLIST_ITEM_RE = re.compile(r"^\s*(\d+)\.\s+\S")


def expand_marker(body):
    """'1, 4-6' -> [1, 4, 5, 6]. Raises ValueError on malformed ranges."""
    nums = []
    for part in body.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            a, b = int(a), int(b)
            if b < a:
                raise ValueError("descending range [%s]" % part)
            nums.extend(range(a, b + 1))
        else:
            nums.append(int(part))
    return nums


def collapse_nums(nums):
    """[1,2,3,5] -> '1-3,5' (runs of >=3 become ranges)."""
    nums = sorted(set(nums))
    runs, start, prev = [], None, None
    for n in nums:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            runs.append((start, prev))
            start = prev = n
    if start is not None:
        runs.append((start, prev))
    out = []
    for a, b in runs:
        if b - a >= 2:
            out.append("%d-%d" % (a, b))
        else:
            out.extend(str(x) for x in range(a, b + 1))
    return ",".join(out)


def find_markers(text):
    """Return list of {start, end, body, numbers}."""
    out = []
    for m in MARKER_RE.finditer(text):
        try:
            nums = expand_marker(m.group(1))
        except ValueError as exc:
            print("error: malformed marker at offset %d: %s" % (m.start(), exc), file=sys.stderr)
            raise
        out.append({"start": m.start(), "end": m.end(), "body": m.group(1), "numbers": nums})
    return out


def analyze(text, bib):
    markers = find_markers(text)
    n_bib = len(bib)
    seen = []            # distinct numbers in first-appearance order
    violations = []      # first-appearance violations
    unknown = []         # numbers with no bibliography entry
    cited = set()
    for mk in markers:
        for n in mk["numbers"]:
            cited.add(n)
            if n > n_bib or n < 1:
                unknown.append({"offset": mk["start"], "marker": "[" + mk["body"] + "]",
                                "number": n, "bibliography_size": n_bib})
            if n not in seen:
                expected = len(seen) + 1
                if n != expected:
                    violations.append({
                        "offset": mk["start"], "marker": "[" + mk["body"] + "]",
                        "number": n, "expected": expected,
                        "note": "first appearance of [%d] here violates numbering by "
                                "first appearance (expected next new number %d)" % (n, expected),
                    })
                seen.append(n)
    uncited = [{"number": i + 1, "key": e.get("key", ""), "title": e.get("title", "")}
               for i, e in enumerate(bib) if (i + 1) not in cited]

    # duplicate-definition risks
    dup_risks = []
    keys = [e.get("key", "") for e in bib]
    for k in sorted(set(k for k in keys if keys.count(k) > 1)):
        dup_risks.append({"kind": "duplicate_bib_key", "key": k,
                          "note": "same key twice in bib.json; marker numbers would be ambiguous"})
    titles = [re.sub(r"\s+", " ", e.get("title", "")).strip().lower() for e in bib]
    for t in sorted(set(t for t in titles if t and titles.count(t) > 1)):
        dup_risks.append({"kind": "duplicate_bib_title", "title": t,
                          "note": "same title twice in bib.json; possible duplicate reference"})
    lines = text.splitlines()
    in_reflist = False
    defined = {}
    for ln in lines:
        if REFLIST_HEAD_RE.match(ln.strip()):
            in_reflist = True
            continue
        if in_reflist:
            if ln.strip().startswith("#"):
                in_reflist = False
                continue
            m = REFLIST_ITEM_RE.match(ln)
            if m:
                num = int(m.group(1))
                if num in defined:
                    dup_risks.append({"kind": "duplicate_definition_in_draft_reflist",
                                      "number": num,
                                      "note": "number %d defined twice in the draft's own "
                                              "reference list" % num})
                defined[num] = True
    return markers, seen, violations, unknown, uncited, dup_risks


def build_mapping(seen, n_bib):
    """old number -> new number, by first-appearance order."""
    mapping = {}
    for new, old in enumerate(seen, start=1):
        mapping[old] = new
    # uncited entries keep stable numbers after the cited ones, in bib order
    nxt = len(seen) + 1
    for i in range(1, n_bib + 1):
        if i not in mapping:
            mapping[i] = nxt
            nxt += 1
    return mapping


def render_bib_md(bib, mapping):
    """Render the bibliography renumbered into citation order."""
    inv = sorted(((new, old) for old, new in mapping.items()))
    lines = ["# References (renumbered by citation order)", ""]
    for new, old in inv:
        e = bib[old - 1]
        authors = ", ".join(e.get("authors", []))
        lines.append("%d. %s (%s). %s. *%s* doi:%s  <!-- key: %s -->" % (
            new, authors, e.get("year", ""), e.get("title", ""),
            e.get("journal", ""), e.get("doi", ""), e.get("key", "")))
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Check Vancouver numbering by first appearance; optionally fix it.")
    ap.add_argument("--bib", required=True, help="bib.json produced by bib_parse.py "
                    "(list order = manuscript reference-list order)")
    ap.add_argument("--draft", required=True, help="manuscript draft markdown")
    ap.add_argument("--out", required=True, help="report JSON path")
    ap.add_argument("--fix", action="store_true",
                    help="rewrite the draft with corrected numbering")
    ap.add_argument("--out-draft", help="fixed draft output path (requires --fix)")
    ap.add_argument("--out-bib", help="renumbered bibliography markdown path (requires --fix)")
    ap.add_argument("--out-changes",
                    help="change record JSON path (default: <out-draft stem>.changes.json)")
    args = ap.parse_args(argv)

    bib_path, draft_path = Path(args.bib), Path(args.draft)
    for p, flag in ((bib_path, "--bib"), (draft_path, "--draft")):
        if not p.is_file():
            print("error: %s file not found: %s" % (flag, p), file=sys.stderr)
            return 2
    if args.fix and not args.out_draft:
        print("error: --fix requires --out-draft", file=sys.stderr)
        return 2
    if (args.out_draft or args.out_bib) and not args.fix:
        print("error: --out-draft/--out-bib only make sense together with --fix", file=sys.stderr)
        return 2

    bib = json.loads(bib_path.read_text(encoding="utf-8"))
    text = draft_path.read_text(encoding="utf-8")
    try:
        markers, seen, violations, unknown, uncited, dup_risks = analyze(text, bib)
    except ValueError:
        return 2

    unknown_numbers = sorted({u["number"] for u in unknown})
    fixable = not unknown_numbers  # cannot renumber markers that have no entry

    report = {
        "draft": str(draft_path),
        "bib": str(bib_path),
        "n_markers": len(markers),
        "distinct_numbers_cited": len(seen),
        "first_appearance_order": seen,
        "first_appearance_violations": violations,
        "unknown_numbers": unknown,
        "uncited_bibliography_entries": uncited,
        "duplicate_definition_risks": dup_risks,
        "fixed": False,
        "status": None,
    }

    rc = 0
    if args.fix:
        if not fixable:
            report["status"] = "fix_aborted_unknown_numbers"
            print("error: cannot --fix while unknown numbers %s have no bibliography entry"
                  % unknown_numbers, file=sys.stderr)
            rc = 1
        else:
            mapping = build_mapping(seen, len(bib))
            edited = 0

            def _sub(m):
                nonlocal edited
                nums = expand_marker(m.group(1))
                new_nums = [mapping[n] for n in nums]
                new_body = collapse_nums(new_nums)
                if new_body != m.group(1).replace(" ", ""):
                    edited += 1
                return "[" + new_body + "]"

            fixed_text = MARKER_RE.sub(_sub, text)
            Path(args.out_draft).write_text(fixed_text, encoding="utf-8")
            changes = {
                "old_to_new": {str(k): v for k, v in sorted(mapping.items())},
                "markers_edited": edited,
                "markers_total": len(markers),
                "violations_fixed": len(violations),
                "out_draft": args.out_draft,
                "out_bib": args.out_bib,
                "note": "citation MARKERS rewritten only; prose untouched",
            }
            changes_path = Path(args.out_changes) if args.out_changes else \
                Path(args.out_draft).with_suffix(".changes.json")
            changes_path.write_text(json.dumps(changes, indent=2, ensure_ascii=False) + "\n",
                                    encoding="utf-8")
            if args.out_bib:
                Path(args.out_bib).write_text(render_bib_md(bib, mapping), encoding="utf-8")
            report["fixed"] = True
            report["change_record"] = str(changes_path)
            report["old_to_new"] = changes["old_to_new"]
            report["markers_edited"] = edited
            report["status"] = "fixed" if (violations or uncited) else "pass"
    else:
        report["status"] = "violations" if (violations or unknown) else "pass"
        if violations or unknown:
            rc = 1

    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    print("markers: %d | distinct cited: %d | first-appearance violations: %d | "
          "unknown numbers: %d | uncited entries: %d | status: %s"
          % (len(markers), len(seen), len(violations), len(unknown), len(uncited),
             report["status"]))
    return rc


if __name__ == "__main__":
    sys.exit(main())
