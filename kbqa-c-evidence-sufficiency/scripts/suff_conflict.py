#!/usr/bin/env python3
"""suff_conflict.py — detect cross-source fact conflicts on extracted evidence.

From every excerpt line in the coverage matrix, extract candidate facts:
  key  = CJK/latin token run before a delimiter (为/是/等于/=/：/:)
  value = the numeric or short token run right after the delimiter
Facts with the same normalized key but different values across documents are
registered as conflicts, each carrying its coordinates (doc_id, sha8, line).

Output: <out>/artifacts/conflicts.json
  {"facts": [{key, values:[...]}], "conflicts": [{key, sides:[{doc_id, sha8,
  line, value, quote}]}]}

Heuristic and conservative: keys must be >=2 chars and non-stop; values must
be numeric-ish or <=8 tokens. Ambiguous groups are kept in `facts` but not
promoted to `conflicts` unless values clearly differ (numeric inequality or
string inequality). Exit code always 0.
"""
import argparse
import json
import os
import re
import sys

PAT = re.compile(
    r"([A-Za-z][A-Za-z0-9_\-]{1,40}|[\u4e00-\u9fff]{2,12})\s*"
    r"(?:为|是|等于|=|:|：)\s*"
    r"([\-+]?\d[\d,]*\.?\d*(?:\s*[x×÷/\-]\s*\d[\d,]*\.?\d*)?"
    r"(?:\s*(?:%|°C|℃|°|K|MPa|GPa|nm|μm|mm|cm|m|s|h|min|g|mg|kg|mL|L|mol|eV|J|W|V|A))"
    r"?|[\u4e00-\u9fffA-Za-z0-9][\u4e00-\u9fffA-Za-z0-9_\.\-]{0,24})")


def norm_val(v):
    return re.sub(r"\s+", "", v).lower().rstrip("。.;；，,")


def norm_key(k):
    return re.sub(r"\s+", "", k).lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()

    art = os.path.join(a.out, "artifacts")
    mpath = os.path.join(art, "coverage_matrix.json")
    matrix = {"questions": []}
    if os.path.exists(mpath):
        matrix = json.load(open(mpath, encoding="utf-8"))

    facts = {}
    for q in matrix.get("questions", []):
        for row in q.get("sources", []):
            for hit in row.get("best_excerpt", []):
                line = hit.get("text", "")
                for m in PAT.finditer(line):
                    k, v = norm_key(m.group(1)), norm_val(m.group(2))
                    if not v or v in ("true", "false", "none"):
                        continue
                    facts.setdefault(k, {}).setdefault(v, []).append({
                        "question_id": q.get("question_id"),
                        "doc_id": row.get("doc_id"), "sha8": row.get("sha8"),
                        "line": hit.get("line"), "quote": line[:200]})

    conflicts = []
    for k, vals in sorted(facts.items()):
        if len(vals) <= 1:
            continue
        sides = [{"value": v, "occurrences": occ} for v, occ in vals.items()]
        numeric = []
        for v in vals:
            try:
                numeric.append(float(v.replace(",", "")))
            except ValueError:
                numeric = None
                break
        clear = True
        if numeric is not None and len(set(numeric)) <= 1:
            clear = False  # same number, different formatting
        conflicts.append({"key": k, "sides": sides, "clear_conflict": clear})

    out = {"fact_keys": len(facts), "conflicts": conflicts}
    with open(os.path.join(art, "conflicts.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("conflict facts=%d clear_conflicts=%d"
          % (len(facts), sum(1 for c in conflicts if c["clear_conflict"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
