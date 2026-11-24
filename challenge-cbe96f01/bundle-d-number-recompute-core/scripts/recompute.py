#!/usr/bin/env python3
"""recompute.py -- number-recompute-core stage 2: contradiction engine.

Runs five deterministic checks over numbers.jsonl (+ pages for table
context); see references/numeric_checks.md for semantics.

  N1 percent recompute (tolerance 0.5 pp)              -> hard
  N2 p-value vs significance wording                   -> hard
  N3 group counts in one sentence vs declared totals   -> hard
  N4 same-noun count cross-consistency                 -> note
  N5 pipe-table Total/合计 row re-sum                   -> hard

Writes contradictions.json: {"hard": [...], "notes": [...], "checks": {...}}
Exit 1 if any hard contradiction is found.
"""
import argparse
import json
import re
import sys

TOTAL_NOUNS = ("participants", "patients", "subjects", "samples")
GROUP_RE = re.compile(
    r"([A-Za-z\u4e00-\u9fff][\w\- ]{0,30}?)\s+group\s+"
    r"(?:contained|had|included|comprised|of|with)\s*(\d+)\b",
    re.IGNORECASE)
TOTAL_ROW_RE = re.compile(r"^\s*([A-Za-z\u4e00-\u9fff ]*?)\s*$")
TOL_PP = 0.5  # percentage-point tolerance for rounding


def sig_word_check(word, op, p):
    w = word.lower()
    if "highly significant" in w:
        return p < 0.01, "highly significant requires p < 0.01"
    if re.search(r"\b(not|no)\s+(?:statistically\s+)?significant\b", w):
        return p >= 0.05, "not significant requires p >= 0.05"
    if "significant" in w:
        return p < 0.05, "significant requires p < 0.05"
    return True, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    ledger = [json.loads(l) for l in open(args.ledger, encoding="utf-8")
              if l.strip()]
    pages = {}
    for l in open(args.pages, encoding="utf-8"):
        if l.strip():
            pg = json.loads(l)
            pages[pg["page"]] = pg["text"]

    hard, notes = [], []
    checks = {"N1": "run", "N2": "run", "N3": "run", "N4": "run",
              "N5": "run"}
    seq = 0

    def add(bucket, check, entry, claimed, recomputed, rule):
        nonlocal seq
        seq += 1
        bucket.append({
            "id": f"C-{seq:02d}", "check": check, "page": entry["page"],
            "quote": entry["raw"], "claimed": claimed,
            "recomputed": recomputed, "rule": rule,
            "context": entry.get("context", "")[:200],
            "ledger_id": entry["id"]})

    # N1 percent recompute
    for e in ledger:
        if e["kind"] != "percent_with_fraction":
            continue
        v = e["value"]
        if v["den"] == 0:
            continue
        recomputed = 100.0 * v["num"] / v["den"]
        if abs(recomputed - v["percent"]) > TOL_PP:
            add(hard, "N1", e, f"{v['percent']}%",
                f"{v['num']}/{v['den']} = {recomputed:.2f}%",
                f"|claimed - recomputed| > {TOL_PP} pp")

    # N2 p-value vs wording
    for e in ledger:
        if e["kind"] != "pvalue":
            continue
        w = e["value"].get("window", "")
        ok, rule = sig_word_check(w, e["value"]["op"], e["value"]["p"])
        if not ok:
            add(hard, "N2", e, f"p {e['value']['op']} {e['value']['p']}",
                w.strip(), rule)

    # N3 group sums vs declared totals (per page, sentence granularity)
    declared = {}
    for e in ledger:
        if e["kind"] == "count" and e["value"]["noun"] in TOTAL_NOUNS:
            declared.setdefault(e["value"]["noun"], set()).add(
                e["value"]["n"])
    for page, text in pages.items():
        flat = re.sub(r"\s+", " ", text)
        for sent in re.split(r"(?<=[.!?。！？])\s+", flat):
            groups = GROUP_RE.findall(sent)
            if len(groups) >= 2:
                total = sum(int(g[1]) for g in groups)
                for noun, vals in declared.items():
                    if total not in vals:
                        add(hard, "N3",
                            {"id": "-", "page": page, "raw": sent[:120],
                             "context": sent[:200]},
                            f"group sum = {total}",
                            f"declared {noun} totals: {sorted(vals)}",
                            "group counts must sum to a declared total")
                        break

    # N4 same-noun cross-consistency (note level)
    for noun, vals in declared.items():
        if len(vals) > 1:
            pages_of = sorted({e["page"] for e in ledger
                               if e["kind"] == "count"
                               and e["value"]["noun"] == noun})
            notes.append({"check": "N4", "noun": noun,
                          "values": sorted(vals), "pages": pages_of,
                          "rule": "same noun carries multiple count values; "
                                  "verify abstract vs body consistency"})

    # N5 pipe-table Total re-sum (column-wise, per contiguous table block)
    for page, text in pages.items():
        rows = [ln for ln in text.splitlines()
                if re.match(r"^\s*\|.+\|\s*$", ln)]
        parsed = []
        for ln in rows:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if all(re.match(r"^:?-{2,}:?$", c) for c in cells):
                continue
            parsed.append((ln, cells))
        for i, (ln, cells) in enumerate(parsed):
            if cells and re.search(r"total|合计", cells[0], re.IGNORECASE):
                for col in range(1, len(cells)):
                    try:
                        claimed = float(cells[col])
                    except (ValueError, IndexError):
                        continue
                    s = 0.0
                    ok = True
                    for j in range(i - 1, -1, -1):
                        prev = parsed[j][1]
                        if prev and re.search(r"total|合计", prev[0],
                                              re.IGNORECASE):
                            break
                        try:
                            s += float(prev[col])
                        except (ValueError, IndexError):
                            if j == 0:
                                continue  # header row, not data
                            ok = False
                    if ok and abs(s - claimed) > 1e-9:
                        add(hard, "N5",
                            {"id": "-", "page": page, "raw": ln.strip(),
                             "context": ln.strip()},
                            f"column {col} total {claimed}",
                            f"sum of rows above = {s}",
                            "Total row must equal column-wise sum")
    out = {"hard": hard, "notes": notes, "checks": checks,
           "summary": {"hard": len(hard), "notes": len(notes)}}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps(out["summary"], ensure_ascii=False))
    sys.exit(1 if hard else 0)


if __name__ == "__main__":
    main()
