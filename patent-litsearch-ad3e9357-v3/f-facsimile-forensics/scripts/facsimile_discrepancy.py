#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""facsimile_discrepancy.py - compare fields extracted from a facsimile source
against a database-style record and emit a discrepancy ledger.

Both sides' values are anchored in their respective extracted texts (pages
JSON produced by facsimile_register.py) using the same declared-tolerance
rules as page_anchor.py. Identical values produce a "consistent" ledger entry;
case/whitespace-only differences are severity "minor"; anything else is
severity "major". Unanchorable values are integrity violations (exit 1).

Usage:
  python3 facsimile_discrepancy.py --spec fields.json \
      --facsimile-pages FAC.pages.json --record-pages REC.pages.json \
      [--policy anchor_policy.json] --out ledger.json

Spec format:
  {"fields": [{"name": ..., "facsimile_value": ..., "record_value": ...}, ...]}

Exit codes: 0 ok (ledger written; discrepancies are data, not failures),
1 check/violation (any value could not be anchored), 2 usage error.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import page_anchor  # noqa: E402


def _norm(s):
    return " ".join(s.split()).casefold()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True, help="fields spec JSON")
    ap.add_argument("--facsimile-pages", required=True)
    ap.add_argument("--record-pages", required=True)
    ap.add_argument("--policy", help="anchor tolerance policy JSON")
    ap.add_argument("--out", required=True, help="ledger output JSON")
    args = ap.parse_args(argv)

    spec = page_anchor.load_json(args.spec)
    facsimile_pages = page_anchor.load_json(args.facsimile_pages)
    record_pages = page_anchor.load_json(args.record_pages)
    policy = page_anchor.load_policy(args.policy)

    fields = spec.get("fields")
    if not isinstance(fields, list) or not fields:
        print("usage error: spec must contain a non-empty 'fields' list", file=sys.stderr)
        return 2

    entries = []
    unanchored = 0
    for f in fields:
        name = f.get("name")
        fval = f.get("facsimile_value", "")
        rval = f.get("record_value", "")
        fa, fviol = page_anchor.find_anchors(facsimile_pages, name, fval, policy)
        ra, rviol = page_anchor.find_anchors(record_pages, name, rval, policy)
        notes = []
        if fviol:
            notes.extend("facsimile: " + v for v in fviol)
        if rviol:
            notes.extend("record: " + v for v in rviol)
        if not fa or not ra:
            status, severity = "unanchored", "blocking"
            unanchored += 1
            if not fa:
                notes.append("facsimile value could not be anchored in %s"
                             % facsimile_pages.get("file"))
            if not ra:
                notes.append("record value could not be anchored in %s"
                             % record_pages.get("file"))
        elif fval == rval:
            status, severity = "consistent", "none"
        elif _norm(fval) == _norm(rval):
            status, severity = "discrepancy", "minor"
            notes.append("values differ only in case/whitespace")
        else:
            status, severity = "discrepancy", "major"
        entries.append({
            "field": name,
            "status": status,
            "severity": severity,
            "facsimile": {
                "value": fval,
                "source_file": facsimile_pages.get("file"),
                "anchors": fa,
            },
            "record": {
                "value": rval,
                "source_file": record_pages.get("file"),
                "anchors": ra,
            },
            "notes": notes,
        })

    ledger = {
        "generated_by": "facsimile_discrepancy.py",
        "facsimile_source": {
            "file": facsimile_pages.get("file"),
            "file_sha256": facsimile_pages.get("file_sha256"),
        },
        "record_source": {
            "file": record_pages.get("file"),
            "file_sha256": record_pages.get("file_sha256"),
        },
        "policy_applied": {
            "allow_whitespace_collapse": bool(policy.get("allow_whitespace_collapse")),
            "allow_page_boundary_merge": bool(policy.get("allow_page_boundary_merge")),
        },
        "summary": {
            "fields": len(entries),
            "consistent": sum(1 for e in entries if e["status"] == "consistent"),
            "discrepancy": sum(1 for e in entries if e["status"] == "discrepancy"),
            "unanchored": unanchored,
        },
        "entries": entries,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, ensure_ascii=False, indent=2)
    s = ledger["summary"]
    print("ledger written: %s (fields=%d consistent=%d discrepancy=%d unanchored=%d)"
          % (args.out, s["fields"], s["consistent"], s["discrepancy"], s["unanchored"]))
    if unanchored:
        print("VIOLATION: %d field value(s) could not be anchored; see ledger" % unanchored,
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
