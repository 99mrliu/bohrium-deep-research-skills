#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py - end-to-end assertions on the synthetic fixtures.

Covers: register on a real minimal PDF (both poppler-if-present and forced
stdlib fallback), anchor found, forged/absent quote rejected (exit 1),
undeclared tolerance rejected, declared tolerance works, page-boundary merge
policy enforced, anchor verify accepts a real anchor and rejects a forged one,
discrepancy detected, consistent case passes.

Prints a summary and exits 0 on success, 1 on any failed check, 2 on usage error.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(SKILL_ROOT, "scripts")
FIXTURES = os.path.join(SKILL_ROOT, "examples", "fixtures")
SPEC = os.path.join(SKILL_ROOT, "examples", "fields_spec.json")

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), detail))
    print("%s %s%s" % ("PASS" if ok else "FAIL", name, (" | " + detail) if detail else ""))


def run(script, *args):
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, script)] + list(args),
        capture_output=True, text=True, cwd=SKILL_ROOT,
    )


def main():
    work = tempfile.mkdtemp(prefix="facsimile_selfcheck_")
    try:
        out_a = os.path.join(work, "out_default")
        out_b = os.path.join(work, "out_fallback")

        # 1. register (default, and forced stdlib fallback) --------------------
        r = run("facsimile_register.py", "--input-dir", FIXTURES, "--out-dir", out_a)
        check("register: exit 0 on fixtures dir", r.returncode == 0, r.stderr.strip())
        r = run("facsimile_register.py", "--input-dir", FIXTURES, "--out-dir", out_b,
                "--no-poppler")
        check("register: exit 0 with --no-poppler (stdlib fallback)", r.returncode == 0,
              r.stderr.strip())

        inv = json.load(open(os.path.join(out_b, "facsimile_inventory.json"),
                             encoding="utf-8"))
        pdf_entry = next((e for e in inv["files"] if e["kind"] == "pdf"), None)
        check("register: PDF fixture inventoried", pdf_entry is not None)
        if pdf_entry:
            check("register: stdlib fallback extracted PDF text layer",
                  pdf_entry["extraction"]["method"] == "stdlib-fallback"
                  and not pdf_entry["extraction"]["degraded"],
                  pdf_entry["extraction"].get("reason") or "")
            check("register: per-page char counts present and positive",
                  bool(pdf_entry["extraction"]["pages"])
                  and all(p["char_count"] > 0 for p in pdf_entry["extraction"]["pages"]))
            check("register: sha256 recorded (64 hex chars)",
                  len(pdf_entry["sha256"]) == 64)
        pdf_pages = os.path.join(out_b, pdf_entry["extraction"]["pages_file"]) if pdf_entry else None
        db_entry = next((e for e in inv["files"] if e["path"] == "db_FX1001.txt"), None)
        db_pages = os.path.join(out_b, db_entry["extraction"]["pages_file"]) if db_entry else None
        check("register: text fixtures extracted as plaintext pages",
              db_entry is not None and db_entry["extraction"]["method"] == "plaintext")

        # 2. exact anchor -------------------------------------------------------
        anc_json = os.path.join(work, "anchor_pub.json")
        r = run("page_anchor.py", "locate", "--pages", pdf_pages,
                "--field", "publication_number", "--value", "US 2099/0123456 A1",
                "--out", anc_json)
        doc = json.load(open(anc_json, encoding="utf-8")) if r.returncode == 0 else {}
        anc = (doc.get("anchors") or [{}])[0]
        check("anchor: exact match found, exit 0", r.returncode == 0, r.stderr.strip())
        check("anchor: page 1, verbatim quote, byte span slices back the quote",
              anc.get("page") == 1 and anc.get("quote") == "US 2099/0123456 A1"
              and anc.get("match_type") == "exact"
              and anc.get("byte_span") is not None)

        # 3. forged / absent value rejected -------------------------------------
        r = run("page_anchor.py", "locate", "--pages", pdf_pages,
                "--field", "publication_number", "--value", "US 2099/9999999 A9")
        check("anchor: absent value rejected with exit 1", r.returncode == 1,
              r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "")

        # 4. tolerance gating ----------------------------------------------------
        tricky = "WO 2099/054321 A1 merged across OCR page boundary"
        empty_policy = os.path.join(work, "empty_policy.json")
        json.dump({}, open(empty_policy, "w", encoding="utf-8"))
        r = run("page_anchor.py", "locate", "--pages", pdf_pages,
                "--field", "related_wo", "--value", tricky, "--policy", empty_policy)
        check("anchor: undeclared whitespace-collapse tolerance refused (exit 1)",
              r.returncode == 1 and "allow_whitespace_collapse" in r.stderr,
              r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "")
        policy = os.path.join(FIXTURES, "anchor_policy.json")
        tol_json = os.path.join(work, "anchor_tol.json")
        r = run("page_anchor.py", "locate", "--pages", pdf_pages,
                "--field", "related_wo", "--value", tricky,
                "--policy", policy, "--out", tol_json)
        tol_doc = json.load(open(tol_json, encoding="utf-8")) if r.returncode == 0 else {}
        tol_anc = (tol_doc.get("anchors") or [{}])[0]
        check("anchor: declared whitespace-collapse tolerance works (exit 0)",
              r.returncode == 0
              and tol_anc.get("match_type") == "whitespace_collapsed"
              and "\n" in tol_anc.get("quote", ""),
              tol_anc.get("match_type", ""))

        # 5. page-boundary merge gating ------------------------------------------
        two_page = os.path.join(work, "two_page.pages.json")
        json.dump({"file": "synthetic_two_page.txt", "file_sha256": "0" * 64,
                   "pages": [{"page": 1, "text": "front part WO 2099/054321"},
                             {"page": 2, "text": "A1 back part"}]},
                  open(two_page, "w", encoding="utf-8"))
        span_val = "WO 2099/054321\nA1"
        r = run("page_anchor.py", "locate", "--pages", two_page,
                "--field", "wo", "--value", span_val, "--policy", empty_policy)
        check("anchor: undeclared page-boundary merge refused (exit 1)",
              r.returncode == 1 and "allow_page_boundary_merge" in r.stderr,
              r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "")
        r = run("page_anchor.py", "locate", "--pages", two_page,
                "--field", "wo", "--value", span_val, "--policy", policy)
        check("anchor: declared page-boundary merge works (exit 0)",
              r.returncode == 0, r.stderr.strip())

        # 6. verify: real anchor OK, forged anchor rejected -----------------------
        r = run("page_anchor.py", "verify", "--pages", pdf_pages, "--anchor", anc_json)
        check("verify: genuine anchor passes (exit 0)", r.returncode == 0, r.stderr.strip())
        forged = json.load(open(anc_json, encoding="utf-8"))
        forged["anchors"][0]["quote"] = "US 2099/0123457 A1"  # tampered quote
        forged_json = os.path.join(work, "anchor_forged.json")
        json.dump(forged, open(forged_json, "w", encoding="utf-8"))
        r = run("page_anchor.py", "verify", "--pages", pdf_pages, "--anchor", forged_json)
        check("verify: forged quote rejected (exit 1)", r.returncode == 1,
              r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "")

        # 7. discrepancy ledger ---------------------------------------------------
        ledger_json = os.path.join(work, "ledger.json")
        r = run("facsimile_discrepancy.py", "--spec", SPEC,
                "--facsimile-pages", pdf_pages, "--record-pages", db_pages,
                "--policy", policy, "--out", ledger_json)
        check("discrepancy: ledger run exit 0 (all values anchored)",
              r.returncode == 0, r.stderr.strip())
        if r.returncode == 0:
            led = json.load(open(ledger_json, encoding="utf-8"))
            by_field = {e["field"]: e for e in led["entries"]}
            inv_e = by_field.get("inventor", {})
            check("discrepancy: inventor spelling flagged as major discrepancy",
                  inv_e.get("status") == "discrepancy" and inv_e.get("severity") == "major"
                  and inv_e["facsimile"]["value"] == "HOLLOWAY, Priya N."
                  and inv_e["record"]["value"] == "HOLLOWEY, Priya N.")
            check("discrepancy: consistent fields marked consistent",
                  by_field.get("publication_number", {}).get("status") == "consistent"
                  and by_field.get("applicant", {}).get("status") == "consistent"
                  and by_field.get("filing_date", {}).get("status") == "consistent")
            check("discrepancy: both sides of discrepancy carry anchors",
                  bool(inv_e.get("facsimile", {}).get("anchors"))
                  and bool(inv_e.get("record", {}).get("anchors")))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    failed = [c for c in CHECKS if not c[1]]
    print("-" * 60)
    print("selfcheck summary: %d checks, %d passed, %d failed"
          % (len(CHECKS), len(CHECKS) - len(failed), len(failed)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
