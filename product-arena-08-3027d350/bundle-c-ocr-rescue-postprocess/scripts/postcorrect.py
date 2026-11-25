#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
postcorrect.py -- evidence-gated application of OCR corrections.

Stage 2 of the ocr-rescue-postprocess pipeline. Reads candidates.jsonl from
confusion_scan.py plus the raw OCR text, and applies ONLY high-confidence
candidates whose suggestion improves lexicon plausibility. Medium
candidates are applied only with --aggressive (or --threshold medium).
Low-confidence candidates are NEVER applied -- the original text is left
untouched and the candidate is recorded in the review list. Garbage spans
(rule kind 'unreadable') are marked as [unreadable]; the marker replaces
the span, it does not guess its content.

Outputs: corrected.txt, change_log.jsonl (every applied edit), review_list.json
(rejected/deferred candidates with reasons).

Stdlib only. Exit codes: 0 = ok, 2 = input/usage error, 3 = runtime failure.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_LEXICON = Path(__file__).resolve().parent.parent / "references" / "lexicon-en.txt"

CONF_RANK = {"low": 1, "medium": 2, "high": 3}
UNREADABLE_MARK = "[unreadable]"
GREEK_RE = re.compile(r"[α-ωΑ-Ω]")


def load_lexicon(path):
    words = set()
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            word = line.strip().lower()
            if word and not word.startswith("#"):
                words.add(word)
    except OSError as exc:
        sys.stderr.write("error: cannot read lexicon %s: %s\n" % (path, exc))
        sys.exit(2)
    return words


def load_candidates(path):
    cands = []
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                cands.append(json.loads(line))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("error: cannot read candidates %s: %s\n" % (path, exc))
        sys.exit(2)
    return cands


def plausible(cand, lexicon):
    """Evidence gate: does the suggestion improve lexicon plausibility?"""
    kind = cand["kind"]
    sug = cand["suggestion"]
    if kind == "unreadable":
        return True, "mark replaces garbage; no content guessed"
    if kind == "greek_latin":
        return True, "Greek-letter restoration gated by physics context"
    if sug.lower() in lexicon:
        return True, "suggestion '%s' is in lexicon" % sug
    return False, "suggestion '%s' is not in lexicon" % sug


def gate(cand, lexicon, threshold_rank, aggressive):
    """Return (action, reason). action in {apply, defer, reject}."""
    conf = cand["confidence"]
    rank = CONF_RANK.get(conf, 0)
    if conf == "low":
        return "defer", "low confidence; policy never alters low-confidence text"
    if conf == "medium":
        if not (aggressive or threshold_rank <= CONF_RANK["medium"]):
            return "defer", ("medium confidence requires --aggressive or "
                             "--threshold medium; original left untouched")
    elif rank < threshold_rank:
        return "defer", "confidence '%s' below threshold" % conf
    ok, why = plausible(cand, lexicon)
    if not ok:
        return "reject", "plausibility gate: " + why
    return "apply", why


def main():
    ap = argparse.ArgumentParser(
        description="Apply whitelisted high-confidence OCR corrections with a full change log.")
    ap.add_argument("--input", required=True, help="raw OCR text file")
    ap.add_argument("--candidates", required=True, help="candidates.jsonl from confusion_scan.py")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--lexicon", default=str(DEFAULT_LEXICON))
    ap.add_argument("--threshold", default="high", choices=["high", "medium"],
                    help="minimum confidence tier to apply (default: high)")
    ap.add_argument("--aggressive", action="store_true",
                    help="also apply medium-confidence candidates (low is never applied)")
    args = ap.parse_args()

    try:
        raw = Path(args.input).read_text(encoding="utf-8")
    except OSError as exc:
        sys.stderr.write("error: cannot read input %s: %s\n" % (args.input, exc))
        sys.exit(2)

    lexicon = load_lexicon(args.lexicon)
    candidates = load_candidates(args.candidates)
    threshold_rank = CONF_RANK[args.threshold]

    pages = raw.split("\f")
    # map global line number -> mutable line text
    lines = []
    page_of_line = []
    for page_no, page_text in enumerate(pages, start=1):
        for line in page_text.split("\n"):
            lines.append(line)
            page_of_line.append(page_no)

    change_log = []
    review_list = []
    accepted = defaultdict(list)  # line index -> list of candidates

    for cand in candidates:
        action, reason = gate(cand, lexicon, threshold_rank, args.aggressive)
        if action == "apply":
            accepted[cand["line"]].append(cand)
        else:
            review_list.append({
                "id": cand["id"], "page": cand["page"], "line": cand["line"],
                "col": cand["col"], "span": cand["span"],
                "suggestion": cand["suggestion"], "rule": cand["rule"],
                "confidence": cand["confidence"], "decision": action,
                "reason": reason,
            })

    for lineno in sorted(accepted):
        line = lines[lineno - 1]
        cands = sorted(accepted[lineno], key=lambda c: c["col"], reverse=True)
        occupied = []
        for cand in cands:
            col, span = cand["col"], cand["span"]
            end = col + len(span)
            if any(col < e and end > s for s, e in occupied):
                review_list.append({
                    "id": cand["id"], "page": cand["page"], "line": cand["line"],
                    "col": col, "span": span, "suggestion": cand["suggestion"],
                    "rule": cand["rule"], "confidence": cand["confidence"],
                    "decision": "reject",
                    "reason": "overlaps an already accepted edit on the same line",
                })
                continue
            if line[col:end] != span:
                review_list.append({
                    "id": cand["id"], "page": cand["page"], "line": cand["line"],
                    "col": col, "span": span, "suggestion": cand["suggestion"],
                    "rule": cand["rule"], "confidence": cand["confidence"],
                    "decision": "reject",
                    "reason": "span mismatch at recorded column; text drifted",
                })
                continue
            if cand["kind"] == "unreadable":
                replacement = UNREADABLE_MARK
            else:
                replacement = cand["suggestion"]
            line = line[:col] + replacement + line[end:]
            occupied.append((col, col + len(replacement)))
            change_log.append({
                "id": cand["id"],
                "page": cand["page"], "line": lineno, "col": col,
                "before": span, "after": replacement,
                "rule": cand["rule"], "kind": cand["kind"],
                "confidence": cand["confidence"],
            })
        lines[lineno - 1] = line

    change_log.sort(key=lambda e: (e["page"], e["line"], e["col"]))
    corrected = "\f".join(
        "\n".join(lines[i] for i in range(len(lines)) if page_of_line[i] == page_no)
        for page_no in range(1, len(pages) + 1))

    out_dir = Path(args.out)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "corrected.txt").write_text(corrected, encoding="utf-8")
        with (out_dir / "change_log.jsonl").open("w", encoding="utf-8") as fh:
            for entry in change_log:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        (out_dir / "review_list.json").write_text(
            json.dumps(review_list, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    except OSError as exc:
        sys.stderr.write("error: cannot write output: %s\n" % exc)
        sys.exit(3)

    by_rule = defaultdict(int)
    for entry in change_log:
        by_rule[entry["rule"]] += 1
    summary = {
        "status": "ok",
        "applied": len(change_log),
        "marked_unreadable": sum(1 for e in change_log if e["kind"] == "unreadable"),
        "deferred_or_rejected": len(review_list),
        "by_rule": dict(sorted(by_rule.items())),
        "threshold": args.threshold,
        "aggressive": bool(args.aggressive),
    }
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
