#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ocr_qc.py -- before/after quality control and contract-aware result assembly.

Stage 3 of the ocr-rescue-postprocess pipeline. Compares the raw OCR text
with the corrected text, quantifies the suspicious-token rate (tokens that
look like OCR residue: digits inside words, symbol mash, unknown words),
counts applied changes by rule, lists remaining (unapplied) candidates and
per-line heat. Emits qc_report.json and result.json.

result.json echoes the case_id and every field of the case's output_contract;
any contract field that cannot be produced is left empty with an explanation
(honest status policy).

Stdlib only. Exit codes: 0 = ok, 2 = input/usage error, 3 = runtime failure.
"""
import argparse
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

TOKEN_RE = re.compile(r"\S+")
STRIP_CHARS = ".,;:!?()\"'“”‘’[]"
GARBAGE_CHARS = set("#@$%^&*~§¥¢|{}<>")
STANDALONE_SUSPECT = {"l", "I", "O"}

# map of known output_contract fields to the file this pipeline produces
CONTRACT_PRODUCERS = {
    "corrected_text": "corrected.txt",
    "change_log": "change_log.jsonl",
    "qc_metrics": "qc_report.json",
    "uncertainty": "review_list.json",
}


def tokenize(line):
    for match in TOKEN_RE.finditer(line):
        raw = match.group(0).strip(STRIP_CHARS)
        if raw:
            yield raw


def is_suspicious(tok, lexicon):
    if any(c in GARBAGE_CHARS for c in tok):
        return True
    if tok in STANDALONE_SUSPECT:
        return True
    has_alpha = any(c.isalpha() for c in tok)
    has_digit = any(c.isdigit() for c in tok)
    if has_alpha and has_digit:
        return True
    if tok.isalpha() and len(tok) >= 3 and tok.isascii() and tok.lower() not in lexicon:
        return True
    return False


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


def load_jsonl(path):
    rows = []
    p = Path(path)
    if not p.exists():
        return rows
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def heat(text, lexicon):
    """Return (total_tokens, suspicious_tokens, per_line list)."""
    total = 0
    suspect = 0
    per_line = []
    lineno = 0
    for page_no, page in enumerate(text.split("\f"), start=1):
        for line in page.split("\n"):
            lineno += 1
            toks = list(tokenize(line))
            bad = [t for t in toks if is_suspicious(t, lexicon)]
            total += len(toks)
            suspect += len(bad)
            if toks:
                per_line.append({"page": page_no, "line": lineno,
                                 "tokens": len(toks), "suspicious": len(bad)})
    return total, suspect, per_line


def main():
    ap = argparse.ArgumentParser(
        description="Before/after OCR QC and contract-aware result.json assembly.")
    ap.add_argument("--raw", required=True, help="raw OCR text")
    ap.add_argument("--corrected", required=True, help="corrected text")
    ap.add_argument("--candidates", required=True, help="candidates.jsonl")
    ap.add_argument("--change-log", required=True, help="change_log.jsonl")
    ap.add_argument("--review", required=True, help="review_list.json")
    ap.add_argument("--case", default=None, help="case.json with case_id and output_contract")
    ap.add_argument("--lexicon", default=str(Path(__file__).resolve().parent.parent
                                             / "references" / "lexicon-en.txt"))
    ap.add_argument("--out", required=True, help="output directory")
    args = ap.parse_args()

    for label, path in [("raw", args.raw), ("corrected", args.corrected),
                        ("candidates", args.candidates)]:
        if not Path(path).exists():
            sys.stderr.write("error: missing %s file %s\n" % (label, path))
            sys.exit(2)

    lexicon = load_lexicon(args.lexicon)
    raw = Path(args.raw).read_text(encoding="utf-8")
    corrected = Path(args.corrected).read_text(encoding="utf-8")
    candidates = load_jsonl(args.candidates)
    changes = load_jsonl(args.change_log)
    try:
        review = json.loads(Path(args.review).read_text(encoding="utf-8")) \
            if Path(args.review).exists() else []
    except json.JSONDecodeError as exc:
        sys.stderr.write("error: bad review list: %s\n" % exc)
        sys.exit(2)

    case = {}
    if args.case:
        try:
            case = json.loads(Path(args.case).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            sys.stderr.write("error: cannot read case file %s: %s\n" % (args.case, exc))
            sys.exit(2)
    case_id = case.get("case_id", "unknown-case")
    contract = case.get("output_contract", {})

    t_b, s_b, heat_b = heat(raw, lexicon)
    t_a, s_a, heat_a = heat(corrected, lexicon)
    rate_b = round(s_b / t_b, 4) if t_b else 0.0
    rate_a = round(s_a / t_a, 4) if t_a else 0.0

    by_rule = defaultdict(int)
    for entry in changes:
        by_rule[entry["rule"]] += 1
    applied_ids = {entry["id"] for entry in changes}
    remaining = [c for c in candidates if c["id"] not in applied_ids]

    qc_report = {
        "status": "ok",
        "suspicious_token_definition": "digit-in-word | symbol mash | standalone l/I/O | "
                                       "ascii alpha token (len>=3) not in lexicon",
        "before": {"tokens": t_b, "suspicious": s_b, "rate": rate_b},
        "after": {"tokens": t_a, "suspicious": s_a, "rate": rate_a},
        "delta": {"suspicious": s_b - s_a,
                  "rate_reduction": round(rate_b - rate_a, 4)},
        "applied_changes": len(changes),
        "applied_by_rule": dict(sorted(by_rule.items())),
        "remaining_candidates": [
            {"id": c["id"], "span": c["span"], "suggestion": c["suggestion"],
             "confidence": c["confidence"], "rule": c["rule"]} for c in remaining],
        "per_line_heat": {
            "before": [h for h in heat_b if h["suspicious"]],
            "after": [h for h in heat_a if h["suspicious"]],
        },
    }

    out_dir = Path(args.out)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "qc_report.json").write_text(
            json.dumps(qc_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        sys.stderr.write("error: cannot write qc report: %s\n" % exc)
        sys.exit(3)

    # ---- contract-aware result.json -------------------------------------
    outputs = {}
    for field in contract:
        produced = CONTRACT_PRODUCERS.get(field)
        if produced and (out_dir / produced).exists():
            outputs[field] = {"path": produced, "status": "produced",
                              "contract_hint": contract[field]}
        else:
            outputs[field] = {"path": "", "status": "empty",
                              "explanation": "no producer implemented for contract "
                                             "field '%s' in this pipeline" % field,
                              "contract_hint": contract[field]}

    import os
    try:
        lexicon_ref = os.path.relpath(str(args.lexicon), str(out_dir))
    except ValueError:
        lexicon_ref = str(args.lexicon)

    warnings = []
    if not args.case:
        warnings.append("no case.json supplied; case_id set to 'unknown-case'")
    if not changes:
        warnings.append("no corrections were applied; check threshold or input quality")
    if remaining:
        warnings.append("%d candidate(s) left unapplied (see uncertainty)" % len(remaining))

    result = {
        "case_id": case_id,
        "status": "ok",
        "skill": "ocr-rescue-postprocess",
        "outputs": outputs,
        "sources": {
            "tools": {
                "tesseract": shutil.which("tesseract") or "not found (not required: "
                                                          "this skill post-processes existing OCR text)",
                "platform_ocr_tool": shutil.which("ocr-tool") or "not detected in this environment",
            },
            "references": {"lexicon": lexicon_ref},
            "input_raw_ocr": str(args.raw),
        },
        "metrics": {
            "suspicious_rate_before": rate_b,
            "suspicious_rate_after": rate_a,
            "suspicious_tokens_before": s_b,
            "suspicious_tokens_after": s_a,
        },
        "change_record": {
            "applied": len(changes),
            "marked_unreadable": sum(1 for e in changes if e["kind"] == "unreadable"),
            "deferred_or_rejected": len(review),
            "by_rule": dict(sorted(by_rule.items())),
            "change_log": "change_log.jsonl",
        },
        "uncertainty": [
            {"span": item["span"], "suggestion": item["suggestion"],
             "confidence": item["confidence"], "reason": item["reason"]}
            for item in review
        ],
        "warnings": warnings,
    }
    try:
        (out_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        sys.stderr.write("error: cannot write result.json: %s\n" % exc)
        sys.exit(3)

    sys.stdout.write(json.dumps({
        "status": "ok", "case_id": case_id,
        "suspicious_rate_before": rate_b, "suspicious_rate_after": rate_a,
        "applied": len(changes), "deferred_or_rejected": len(review),
    }, ensure_ascii=False, indent=2) + "\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
