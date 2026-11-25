#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
confusion_scan.py -- data-driven scanner for characteristic OCR errors.

Stage 1 of the ocr-rescue-postprocess pipeline. Reads raw OCR text (pages
separated by form feeds), a TSV table of confusion rules
(references/ocr-confusions.tsv) and a domain lexicon
(references/lexicon-en.txt) that is used as plausibility evidence. Emits
candidates.jsonl -- one JSON object per candidate correction. NOTHING is
modified at this stage; gating and application happen in postcorrect.py.

Stdlib only. Exit codes: 0 = ok, 2 = input/usage error, 3 = runtime failure.
"""
import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_RULES = Path(__file__).resolve().parent.parent / "references" / "ocr-confusions.tsv"
DEFAULT_LEXICON = Path(__file__).resolve().parent.parent / "references" / "lexicon-en.txt"

# Token = run of non-whitespace, stripped of surrounding sentence punctuation.
# Brackets are stripped so that the [unreadable] mark never re-flags itself.
TOKEN_RE = re.compile(r"\S+")
STRIP_CHARS = ".,;:!?()\"'“”‘’[]"

# Suffixes that make a latin single letter before a hyphen a Greek-letter
# candidate (a-particles -> alpha-particles).
PHYS_SUFFIX = {"particle", "particles", "decay", "ray", "rays",
               "radiation", "emission", "transition", "transitions"}

# Tokens that make a standalone single letter a numeric-context candidate.
UNIT_TOKENS = {"nm", "mm", "cm", "um", "km", "mv", "v", "ev", "kev", "mev",
               "kg", "mg", "ml", "s", "ms", "min", "hz", "khz", "mhz",
               "ghz", "ma", "pa", "kpa", "mpa", "gpa", "mol", "mmol"}

REQUIRED_COLUMNS = ["id", "kind", "pattern", "replacement",
                    "context", "confidence", "comment"]
VALID_CONFIDENCE = {"high", "medium", "low"}


def load_rules(path):
    rules = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        sys.stderr.write("error: cannot read rules table %s: %s\n" % (path, exc))
        sys.exit(2)
    lines = text.splitlines()
    if not lines:
        sys.stderr.write("error: rules table %s is empty\n" % path)
        sys.exit(2)
    header = lines[0].split("\t")
    if header != REQUIRED_COLUMNS:
        sys.stderr.write("error: rules table header %r != %r\n" % (header, REQUIRED_COLUMNS))
        sys.exit(2)
    for lineno, line in enumerate(lines[1:], start=2):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != len(REQUIRED_COLUMNS):
            sys.stderr.write("error: rules table line %d has %d fields, expected %d\n"
                             % (lineno, len(parts), len(REQUIRED_COLUMNS)))
            sys.exit(2)
        rule = dict(zip(REQUIRED_COLUMNS, parts))
        if rule["confidence"] not in VALID_CONFIDENCE:
            sys.stderr.write("error: rules table line %d: bad confidence %r\n"
                             % (lineno, rule["confidence"]))
            sys.exit(2)
        rules.append(rule)
    return rules


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
    if not words:
        sys.stderr.write("error: lexicon %s is empty\n" % path)
        sys.exit(2)
    return words


def tokenize(line):
    """Yield (token, column) pairs; strip surrounding punctuation."""
    for match in TOKEN_RE.finditer(line):
        raw = match.group(0)
        stripped = raw.strip(STRIP_CHARS)
        if not stripped:
            continue
        offset = raw.find(stripped)
        yield stripped, match.start() + offset


def restore_case(original, suggestion):
    if original[:1].isupper():
        return suggestion[:1].upper() + suggestion[1:]
    return suggestion


def make_candidate(seq, page, lineno, col, span, suggestion, rule, reason):
    return {
        "id": "c%04d" % seq,
        "page": page,
        "line": lineno,
        "col": col,
        "span": span,
        "suggestion": suggestion,
        "rule": rule["id"],
        "kind": rule["kind"],
        "confidence": rule["confidence"],
        "context": rule["context"],
        "reason": reason,
    }


def scan(raw_text, rules, lexicon):
    """Return list of candidate dicts, deterministically ordered."""
    candidates = []
    seq = 0
    pages = raw_text.split("\f")
    lineno = 0
    for page_no, page_text in enumerate(pages, start=1):
        for line in page_text.split("\n"):
            lineno += 1
            tokens = list(tokenize(line))
            for idx, (tok, col) in enumerate(tokens):
                low = tok.lower()
                prev_tok = tokens[idx - 1][0] if idx > 0 else ""
                next_tok = tokens[idx + 1][0] if idx + 1 < len(tokens) else ""
                for rule in rules:
                    kind = rule["kind"]
                    pat, rep = rule["pattern"], rule["replacement"]

                    if kind == "unreadable":
                        if re.fullmatch(pat, tok) and low not in lexicon:
                            seq += 1
                            candidates.append(make_candidate(
                                seq, page_no, lineno, col, tok, rep, rule,
                                "symbol-mash token with no lexicon explanation"))

                    elif kind == "char_in_word":
                        if pat not in tok:
                            continue
                        # skip chemical-formula-like tokens (C12, Fe2O3 ...)
                        if tok[:1].isupper() and any(c.isdigit() for c in tok):
                            continue
                        if sum(c.isalpha() for c in tok) < 2:
                            continue
                        suggestion = tok.replace(pat, rep)
                        if not suggestion.isalpha():
                            continue
                        if low in lexicon:
                            continue  # original is a known word: leave it alone
                        if suggestion.lower() in lexicon:
                            seq += 1
                            candidates.append(make_candidate(
                                seq, page_no, lineno, col, tok,
                                restore_case(tok, suggestion.lower()), rule,
                                "'%s' not in lexicon; '%s' with %s->%s is"
                                % (tok, suggestion, pat, rep)))

                    elif kind == "seq_in_word":
                        if not tok.isalpha() or len(tok) < 3 or low in lexicon:
                            continue
                        if pat not in tok:
                            continue
                        hits = []
                        start = 0
                        while True:
                            i = tok.find(pat, start)
                            if i < 0:
                                break
                            sug = tok[:i] + rep + tok[i + len(pat):]
                            if sug.lower() in lexicon and sug.lower() not in [h.lower() for h in hits]:
                                hits.append(sug)
                            start = i + 1
                        if len(hits) == 1:
                            seq += 1
                            candidates.append(make_candidate(
                                seq, page_no, lineno, col, tok,
                                restore_case(tok, hits[0].lower()), rule,
                                "'%s' not in lexicon; %s->%s yields lexicon word '%s'"
                                % (tok, pat, rep, hits[0])))
                        elif len(hits) > 1:
                            for sug in hits:
                                seq += 1
                                cand = make_candidate(
                                    seq, page_no, lineno, col, tok,
                                    restore_case(tok, sug.lower()), rule,
                                    "multiple lexicon matches %s: ambiguous"
                                    % [h.lower() for h in hits])
                                cand["confidence"] = "low"
                                candidates.append(cand)

                    elif kind == "ligature_insert":
                        if not tok.isalpha() or len(tok) < 3 or low in lexicon:
                            continue
                        hits = []
                        for i in range(len(tok) + 1):
                            sug = tok[:i] + pat + tok[i:]
                            if sug.lower() in lexicon and sug.lower() not in [h.lower() for h in hits]:
                                hits.append(sug)
                        if len(hits) == 1:
                            seq += 1
                            candidates.append(make_candidate(
                                seq, page_no, lineno, col, tok,
                                restore_case(tok, hits[0].lower()), rule,
                                "dropped ligature '%s'; unique lexicon completion '%s'"
                                % (pat, hits[0])))
                        elif len(hits) > 1:
                            for sug in hits:
                                seq += 1
                                cand = make_candidate(
                                    seq, page_no, lineno, col, tok,
                                    restore_case(tok, sug.lower()), rule,
                                    "multiple ligature completions %s: ambiguous"
                                    % [h.lower() for h in hits])
                                cand["confidence"] = "low"
                                candidates.append(cand)

                    elif kind == "greek_latin":
                        m = re.fullmatch(r"([A-Za-z])-([a-z]+)", tok)
                        if not m or m.group(1) != pat:
                            continue
                        if m.group(2) in PHYS_SUFFIX:
                            seq += 1
                            candidates.append(make_candidate(
                                seq, page_no, lineno, col, tok,
                                rep + "-" + m.group(2), rule,
                                "latin '%s' before physics suffix '-%s' is likely Greek '%s'"
                                % (pat, m.group(2), rep)))

                    elif kind == "standalone_confusable":
                        if tok != pat:
                            continue
                        numeric_ctx = (next_tok.isdigit() or prev_tok.isdigit()
                                       or next_tok.lower() in UNIT_TOKENS
                                       or prev_tok.lower() in UNIT_TOKENS)
                        if numeric_ctx:
                            seq += 1
                            candidates.append(make_candidate(
                                seq, page_no, lineno, col, tok, rep, rule,
                                "standalone '%s' in numeric context; genuinely ambiguous"
                                % tok))

                    elif kind == "space_merge":
                        pass  # handled at pair level below

            # pair-level pass: spurious split of one word into two tokens
            merge_rules = [r for r in rules if r["kind"] == "space_merge"]
            if merge_rules:
                rule = merge_rules[0]
                for idx in range(len(tokens) - 1):
                    t1, c1 = tokens[idx]
                    t2, _ = tokens[idx + 1]
                    if not (t1.isalpha() and t2.isalpha()):
                        continue
                    if len(t1) < 2 or len(t2) < 2:
                        continue
                    joined = t1 + t2
                    if len(joined) < 6:
                        continue
                    if joined.lower() in lexicon and (
                            t1.lower() not in lexicon or t2.lower() not in lexicon):
                        seq += 1
                        candidates.append(make_candidate(
                            seq, page_no, lineno, c1, t1 + " " + t2,
                            joined.lower(), rule,
                            "split word: join '%s' is in lexicon, parts are not"
                            % joined))
    return candidates


def main():
    ap = argparse.ArgumentParser(
        description="Scan raw OCR text for characteristic confusion patterns; "
                    "emit candidates.jsonl (no text is modified).")
    ap.add_argument("--input", required=True, help="raw OCR text file (pages separated by form feeds)")
    ap.add_argument("--out", required=True, help="output directory for candidates.jsonl")
    ap.add_argument("--rules", default=str(DEFAULT_RULES), help="confusion rules TSV")
    ap.add_argument("--lexicon", default=str(DEFAULT_LEXICON), help="domain lexicon (one word per line)")
    args = ap.parse_args()

    try:
        raw = Path(args.input).read_text(encoding="utf-8")
    except OSError as exc:
        sys.stderr.write("error: cannot read input %s: %s\n" % (args.input, exc))
        sys.exit(2)

    rules = load_rules(args.rules)
    lexicon = load_lexicon(args.lexicon)

    try:
        candidates = scan(raw, rules, lexicon)
    except Exception as exc:  # defensive: never crash silently
        sys.stderr.write("error: scan failed: %s\n" % exc)
        sys.exit(3)

    n_tokens = sum(1 for page in raw.split("\f") for line in page.split("\n")
                   for _ in tokenize(line))
    if n_tokens == 0:
        sys.stderr.write("error: no tokens found; input may be image-only without an OCR text layer\n")
        sys.exit(3)

    out_dir = Path(args.out)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "candidates.jsonl"
        with out_path.open("w", encoding="utf-8") as fh:
            for cand in candidates:
                fh.write(json.dumps(cand, ensure_ascii=False) + "\n")
    except OSError as exc:
        sys.stderr.write("error: cannot write output: %s\n" % exc)
        sys.exit(3)

    by_conf = {"high": 0, "medium": 0, "low": 0}
    by_kind = {}
    for cand in candidates:
        by_conf[cand["confidence"]] += 1
        by_kind[cand["kind"]] = by_kind.get(cand["kind"], 0) + 1
    summary = {
        "status": "ok",
        "input": str(args.input),
        "tokens": n_tokens,
        "candidates": len(candidates),
        "by_confidence": by_conf,
        "by_kind": by_kind,
        "output": str(out_path),
    }
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
