#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_quotes.py -- verbatim quote gate.

Every adjudicated record's quote is checked against the extracted page
text using normalized substring matching (whitespace collapse, hyphen
line-break joining, NFKC fold). If the quote is not found on the stated
page, the full text is searched and the actual page is reported. If it is
not found anywhere, the record's judgment is downgraded to 'insufficient'
and the failure is logged.

Reads : adjudicated/<doc_id>.jsonl, pages/<doc_id>.jsonl
Writes: verified/<doc_id>.jsonl, verify_report.json
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common_utils as cu

SCRIPT_VERSION = "verify_quotes/1.0"


def parse_locator(locator):
    m = re.match(r"p(\d+)", locator or "")
    return int(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser(description="Verify verbatim quotes")
    ap.add_argument("--workdir", default="/app/work")
    args = ap.parse_args()

    adj_dir = os.path.join(args.workdir, "adjudicated")
    out_dir = os.path.join(args.workdir, "verified")
    os.makedirs(out_dir, exist_ok=True)

    report = {"version": SCRIPT_VERSION, "total_quotes": 0, "verified": 0,
              "relocated": 0, "failed": 0, "failures": []}

    try:
        names = sorted(os.listdir(adj_dir))
    except Exception:
        names = []
    for name in names:
        if not name.endswith(".jsonl"):
            continue
        doc_id = name[:-len(".jsonl")]
        pages = cu.load_pages(args.workdir, doc_id)
        page_texts = {p.get("page"): p.get("text", "") for p in pages}
        rows = cu.read_jsonl(os.path.join(adj_dir, name))
        out_rows = []
        for row in rows:
            quote = (row.get("quote") or "").strip()
            if not quote:
                row["quote_verified"] = None  # nothing to verify
                out_rows.append(row)
                continue
            report["total_quotes"] += 1
            stated_page = parse_locator(row.get("locator"))
            ok_on_page = stated_page is not None and \
                cu.norm_contains(page_texts.get(stated_page, ""), quote)
            if ok_on_page:
                row["quote_verified"] = True
                row["verified_page"] = stated_page
                report["verified"] += 1
                out_rows.append(row)
                continue
            # search the whole document
            actual = None
            for pno in sorted(page_texts):
                if cu.norm_contains(page_texts[pno], quote):
                    actual = pno
                    break
            if actual is not None:
                row["quote_verified"] = True
                row["verified_page"] = actual
                row["locator_corrected"] = True
                row["locator_original"] = row.get("locator")
                row["locator"] = "p%d" % actual
                report["relocated"] += 1
                report["failures"].append({
                    "doc_id": doc_id, "domain": row.get("domain"),
                    "issue": "wrong_page",
                    "stated_page": stated_page, "actual_page": actual,
                    "quote_prefix": quote[:80]})
            else:
                row["quote_verified"] = False
                row["judgment_original"] = row.get("judgment")
                row["judgment"] = "insufficient"
                row["verification_note"] = (
                    "quote not found verbatim; downgraded to insufficient")
                report["failed"] += 1
                report["failures"].append({
                    "doc_id": doc_id, "domain": row.get("domain"),
                    "issue": "quote_not_found",
                    "stated_page": stated_page,
                    "quote_prefix": quote[:80]})
            out_rows.append(row)
        cu.write_jsonl(os.path.join(out_dir, name), out_rows)

    cu.write_json(os.path.join(args.workdir, "verify_report.json"), report)
    print({k: report[k] for k in
           ("total_quotes", "verified", "relocated", "failed")})


if __name__ == "__main__":
    main()
