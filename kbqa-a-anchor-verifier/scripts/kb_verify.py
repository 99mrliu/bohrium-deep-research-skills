#!/usr/bin/env python3
"""kb_verify.py — machine-verify every citation against the indexed content.

Input citations: JSONL, one object per line:
  {"answer_id": "Q1", "claim": "...", "file_id": "F07",
   "locator": "L14-L17", "quote": "原文逐字片段"}

Checks per citation:
  1. file_id exists in the index
  2. the file was extracted (status ok)
  3. quote is a verbatim substring of the extracted text (whitespace-normalized)
  4. if locator "Lx-Ly" is given, the quote appears within those lines
     (mismatch is reported separately as locator_mismatch, still a hard fail)

On quote_not_found a best_match (difflib >=0.60) with its true coordinates is
reported so the agent can repair the citation. Exit code is always 0.

Output: JSON report {summary:{...}, citations:[{...,pass,reason,best_match?}]}.
"""
import argparse
import difflib
import json
import re
import sys


def norm(s):
    # remove ALL whitespace: robust for quotes spanning line breaks, and
    # symmetric (both sides normalized identically) so verbatim matching holds
    return re.sub(r"\s+", "", s)


def line_range_of(locator, n_lines):
    m = re.findall(r"L(\d+)", locator or "")
    if not m:
        return None
    nums = [int(x) for x in m]
    lo, hi = min(nums), max(nums)
    return max(1, lo), min(n_lines, hi)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--citations", required=True)
    ap.add_argument("--report", required=True)
    a = ap.parse_args()

    with open(a.index, encoding="utf-8") as f:
        index = json.load(f)
    by_id = {r["file_id"]: r for r in index.get("files", [])}

    texts = {}
    for rec in by_id.values():
        if rec.get("extract_status") == "ok" and rec.get("extract_path"):
            try:
                with open(rec["extract_path"], encoding="utf-8", errors="replace") as f:
                    texts[rec["file_id"]] = f.read().splitlines()
            except OSError:
                texts[rec["file_id"]] = None

    checked = []
    with open(a.citations, encoding="utf-8") as f:
        raw = [json.loads(l) for l in f if l.strip()]

    for c in raw:
        entry = dict(c)
        entry["pass"] = False
        entry["reason"] = None
        fid = c.get("file_id")
        rec = by_id.get(fid)
        if rec is None:
            entry["reason"] = "file_not_in_index"
        elif rec.get("extract_status") != "ok" or texts.get(fid) is None:
            entry["reason"] = "file_unreadable:%s" % rec.get("extract_status")
        else:
            lines = texts[fid]
            full = norm("\n".join(lines))
            q = norm(c.get("quote", ""))
            if not q:
                entry["reason"] = "empty_quote"
            elif q in full:
                rng = line_range_of(c.get("locator"), len(lines))
                if rng is None:
                    entry["pass"] = True
                else:
                    lo, hi = rng
                    window = norm("\n".join(lines[lo - 1: hi]))
                    if q in window:
                        entry["pass"] = True
                    else:
                        entry["reason"] = "locator_mismatch:quote_found_elsewhere"
                        entry["true_locator"] = find_locator(q, lines)
            else:
                entry["reason"] = "quote_not_found"
                bm = best_match(q, lines)
                if bm and bm["similarity"] >= 0.60:
                    entry["best_match"] = bm
        checked.append(entry)

    report = {
        "total": len(checked),
        "passed": sum(1 for e in checked if e["pass"]),
        "failed": sum(1 for e in checked if not e["pass"]),
        "citations": checked,
    }
    with open(a.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("verify total=%d passed=%d failed=%d" %
          (report["total"], report["passed"], report["failed"]))
    return 0


def find_locator(quote_norm, lines):
    """Return 'Lx-Ly' spanning lines whose joined text contains the quote."""
    joined = [norm(l) for l in lines]
    n = len(joined)
    for i in range(n):
        buf = ""
        for j in range(i, min(n, i + 40)):
            buf = norm(buf + " " + joined[j]) if buf else joined[j]
            if quote_norm in buf:
                return "L%d-L%d" % (i + 1, j + 1)
            if len(buf) > len(quote_norm) + 200:
                break
    return None


def best_match(quote_norm, lines, limit=400):
    """Best difflib match of quote against line windows; needs similarity>=0.6."""
    sm = difflib.SequenceMatcher(None, quote_norm, "")
    best = None
    step = max(1, len(lines) // limit)
    for i in range(0, len(lines), step):
        window = norm("\n".join(lines[i: i + 6]))
        if len(window) < 4:
            continue
        sm.set_seq2(window[: max(len(quote_norm) * 3, 400)])
        r = sm.ratio()
        if best is None or r > best["similarity"]:
            best = {"similarity": round(r, 3),
                    "locator": "L%d-L%d" % (i + 1, min(len(lines), i + 6)),
                    "text": window[:300]}
        if r >= 0.98:
            break
    return best


if __name__ == "__main__":
    sys.exit(main())
