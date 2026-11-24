#!/usr/bin/env python3
"""verify_claims.py -- the hard evidence-chain gate.

For every evidence quote of every note, normalize both the quote and the cited
page text (Unicode NFKC + whitespace collapse) and check that the quote occurs
in sources/<file>/page-NNN.txt of the cited file. Writes claims_report.json.

Exit codes:
  0  every claim verified
  2  usage / IO error
  3  at least one claim NOT verified (file_missing / page_missing /
     quote_not_found); offenders listed on stderr with their note_id
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

TOOL_VERSION = "deliverable-forge 1.0.0"


def die(msg, code=2):
    print(f"verify_claims: ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def normalize_text(s):
    """Unicode NFKC + whitespace collapse (same rule as compose_notes.py)."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def load_jsonl(path, what):
    p = Path(path)
    if not p.is_file():
        die(f"{what} not found: {path}")
    records = []
    with p.open(encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                die(f"{what}:{lineno}: invalid JSON: {e}")
    return records


def check_evidence(sources_dir, ev):
    """Return status in verified / file_missing / page_missing /
    quote_not_found."""
    fdir = Path(sources_dir) / ev["file"]
    if not fdir.is_dir():
        return "file_missing"
    pfile = fdir / f"page-{int(ev['page']):03d}.txt"
    if not pfile.is_file():
        return "page_missing"
    page_text = pfile.read_text(encoding="utf-8")
    if normalize_text(ev["quote"]) in normalize_text(page_text):
        return "verified"
    return "quote_not_found"


def main():
    ap = argparse.ArgumentParser(
        description="Verify every evidence quote against the cited page text.")
    ap.add_argument("--notes", required=True, help="notes.jsonl from "
                    "compose_notes.py")
    ap.add_argument("--sources-dir", required=True,
                    help="directory with sources/<filekey>/page-NNN.txt")
    ap.add_argument("--out", required=True, help="output claims_report.json")
    args = ap.parse_args()

    notes = load_jsonl(args.notes, "notes file")
    if not Path(args.sources_dir).is_dir():
        die(f"sources dir not found: {args.sources_dir}")

    results, total, verified = [], 0, 0
    for note in notes:
        ev_results, note_status = [], "verified"
        for ev in note.get("evidence", []):
            status = check_evidence(args.sources_dir, ev)
            total += 1
            if status == "verified":
                verified += 1
            elif note_status == "verified":
                note_status = status
            ev_results.append({
                "file": ev.get("file"),
                "page": ev.get("page"),
                "annotation_id": ev.get("annotation_id"),
                "status": status,
                "quote_preview": normalize_text(ev.get("quote", ""))[:60],
            })
        results.append({"note_id": note.get("note_id"), "status": note_status,
                        "evidence": ev_results})

    rate = round(verified / total, 4) if total else 1.0
    all_ok = verified == total
    report = {
        "tool": TOOL_VERSION,
        "notes_file": args.notes,
        "sources_dir": args.sources_dir,
        "total_claims": total,
        "verified": verified,
        "unverified": total - verified,
        "verified_rate": rate,
        "all_verified": all_ok,
        "results": results,
    }
    with Path(args.out).open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")

    print(f"verify_claims {TOOL_VERSION}")
    print(f"claims: {total}  verified: {verified}  "
          f"unverified: {total - verified}  verified_rate: {rate}")
    for r in results:
        for ev in r["evidence"]:
            if ev["status"] != "verified":
                print(f"UNVERIFIED note {r['note_id']}: {ev['status']} "
                      f"({ev['file']} p.{ev['page']} "
                      f"ann={ev['annotation_id']}) "
                      f"quote='{ev['quote_preview']}...'", file=sys.stderr)
    print(f"wrote: {args.out}")
    if not all_ok:
        print("evidence-chain gate FAILED: fix or remove unverified claims.",
              file=sys.stderr)
        sys.exit(3)
    print("evidence-chain gate PASSED.")
    sys.exit(0)


if __name__ == "__main__":
    main()
