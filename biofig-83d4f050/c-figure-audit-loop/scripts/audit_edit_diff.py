#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_edit_diff.py — before/after element-level diff for case kind (3),
source-preserving edits of an existing figure.

Both SVGs are parsed; every element carrying an id is canonicalized
(sorted attributes, recursive children) and compared:

  edit.target_unchanged   claims.edit_expectations.changed_elements[]   [error]
                          entry did NOT change (edit not applied)
  edit.unexpected_change  element outside changed_elements changed      [error]
                          (or was added/removed)
  edit.sample_changed     claims.edit_expectations.unchanged_sample[]   [error]
                          entry changed (should have been preserved)
  edit.missing_element    an expected element id absent in after.svg    [error]

If claims has no edit_expectations, the full changed/added/removed lists
are reported as warnings so the agent can eyeball them.

Usage:
  audit_edit_diff.py --before before.svg --after after.svg
                     [--claims claims.json] --out violations.json
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svg_conventions as C  # noqa: E402


def viol(check, severity, detail, element=None, source=None):
    return {"auditor": "edit_diff", "check": check, "severity": severity,
            "detail": detail, "element": element, "source": source}


def id_map(root):
    out = {}
    for el in root.iter():
        eid = el.get("id")
        if eid:
            out[eid] = C.serialize_element(el)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--claims")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    violations, skipped = [], []
    try:
        bmap = id_map(C.parse_svg(args.before).getroot())
    except Exception as exc:
        print("ERROR: cannot parse before SVG: %s" % exc, file=sys.stderr)
        return 2
    try:
        amap = id_map(C.parse_svg(args.after).getroot())
    except Exception as exc:
        print("ERROR: cannot parse after SVG: %s" % exc, file=sys.stderr)
        return 2

    changed = sorted(k for k in bmap.keys() & amap.keys()
                     if bmap[k] != amap[k])
    added = sorted(amap.keys() - bmap.keys())
    removed = sorted(bmap.keys() - amap.keys())

    expectations = {}
    if args.claims and os.path.exists(args.claims):
        with open(args.claims, encoding="utf-8") as fh:
            expectations = (json.load(fh).get("edit_expectations") or {})
    exp_changed = set(expectations.get("changed_elements", []))
    exp_unchanged = set(expectations.get("unchanged_sample", []))

    if expectations:
        for eid in sorted(exp_changed):
            if eid in removed:
                violations.append(viol(
                    "edit.missing_element", "error",
                    "expected changed element '%s' was REMOVED" % eid,
                    element=eid))
            elif eid not in changed and eid not in added:
                violations.append(viol(
                    "edit.target_unchanged", "error",
                    "expected changed element '%s' is byte-identical to "
                    "before.svg — edit NOT applied" % eid, element=eid))
        for eid in sorted(exp_unchanged):
            if eid in changed or eid in removed:
                violations.append(viol(
                    "edit.sample_changed", "error",
                    "element '%s' was expected to stay unchanged but %s" % (
                        eid, "was removed" if eid in removed else "changed"),
                    element=eid))
            elif eid not in amap:
                violations.append(viol(
                    "edit.missing_element", "error",
                    "unchanged_sample element '%s' absent from after.svg"
                    % eid, element=eid))
        for eid in changed:
            if eid not in exp_changed and eid not in exp_unchanged:
                violations.append(viol(
                    "edit.unexpected_change", "error",
                    "element '%s' changed but is not listed in "
                    "edit_expectations.changed_elements" % eid, element=eid))
        for eid in added:
            if eid not in exp_changed:
                violations.append(viol(
                    "edit.unexpected_change", "error",
                    "element '%s' was ADDED but not declared in "
                    "changed_elements" % eid, element=eid))
        for eid in removed:
            if eid not in exp_changed:
                violations.append(viol(
                    "edit.unexpected_change", "error",
                    "element '%s' was REMOVED but not declared in "
                    "changed_elements" % eid, element=eid))
    else:
        for eid in changed + added + removed:
            kind = "changed" if eid in changed else (
                "added" if eid in added else "removed")
            violations.append(viol(
                "edit.unexpected_change", "warning",
                "element '%s' %s (no edit_expectations in claims to check "
                "against — review manually)" % (eid, kind), element=eid))

    result = {"auditor": "edit_diff",
              "summary": {"changed": changed, "added": added,
                          "removed": removed},
              "violations": violations, "skipped": skipped}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
    errs = sum(1 for v in violations if v["severity"] == "error")
    print("edit_diff: %d changed, %d added, %d removed; %d errors" % (
        len(changed), len(added), len(removed), errs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
