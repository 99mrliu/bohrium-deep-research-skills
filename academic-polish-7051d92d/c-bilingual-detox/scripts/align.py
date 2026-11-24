#!/usr/bin/env python3
"""align.py -- zh/en sentence alignment, cross-language conservation coverage,
and back-translation worksheet gating (c2e-detox-polish).

Python 3 standard library only. Deterministic: same input -> byte-identical output.

Subcommands:
  align              --zh <f> --en <f> --out <f|->
      Build a zh<->en sentence-pair table by order. If sentence counts differ,
      aligned pairs stop at the shorter side and ALL unaligned sentences are
      listed explicitly (never silently dropped).

  coverage           --alignment <f> --out <f|-> [--table <f|->]
      Cross-language conservation check per pair: numbers, units, years,
      latin proper nouns (capitalized/acronym strings; Chinese 《》 and quote
      strings on the zh side), citation markers [n]. Anything present on one
      side and missing on the other is listed -> catches "translator silently
      changed the data". Optionally also writes a Markdown alignment table.

  backtrans-template --alignment <f> --out <f|->
      Emit a back-translation worksheet: each pair carries zh_text, en_text and
      EMPTY back_translation / equivalence / note fields. The Agent (LLM) --
      never this script -- fills the fields.

  backtrans-check    --backtrans <f> --out <f|->
      Gate a filled worksheet. Any pair with an empty back_translation, an
      invalid/empty equivalence label, or equivalence="mismatch" is listed in
      `uncertainty`, the gate is "fail", and the overall task status MUST NOT
      be reported as success. The script only gates and counts; the semantic
      judgement was made by the Agent.

Conservation is a surface-form check: it proves nothing about style or
faithfulness of meaning; it only proves surface tokens were not dropped/added.
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import Counter

VERSION = "1.0.0"

# --- sentence splitter: identical copy of the one in detox.py --------------
TERMINALS = set("。！？!?")
CLOSERS = set("”’\"')）)]》〉」』】")


def _dot_is_terminal(text, i):
    """'.' ends a sentence only if the next sentence plausibly starts after it
    (protects decimals '3.14' and abbreviations 'et al. reported')."""
    n = len(text)
    j = i + 1
    if j >= n:
        return True
    if text[j] == "\n":
        return True
    if text[j] != " ":
        return False  # glued: decimal, URL, abbreviation like 'al.x'
    k = j
    while k < n and text[k] == " ":
        k += 1
    if k >= n:
        return True
    c = text[k]
    return c.isupper() or c.isdigit() or ord(c) > 127 or c in "([\"'“‘"


def split_sentences(text):
    """Split mixed zh/en text into sentences with stable ids and char offsets.
    Terminals: 。！？!? , sentence-final '.', and hard newlines."""
    out = []
    n = len(text)

    def emit(a, b):
        seg = text[a:b]
        stripped = seg.strip()
        if stripped:
            lead = len(seg) - len(seg.lstrip())
            s = a + lead
            out.append({
                "id": "s%04d" % (len(out) + 1),
                "start": s,
                "end": s + len(stripped),
                "text": stripped,
            })

    seg_start = 0
    i = 0
    while i < n:
        ch = text[i]
        terminal = ch in TERMINALS or (ch == "." and _dot_is_terminal(text, i))
        if ch == "\n" or terminal:
            j = i + 1
            if terminal:
                while j < n and text[j] in CLOSERS:
                    j += 1
            emit(seg_start, j)
            i = j
            seg_start = j
        else:
            i += 1
    emit(seg_start, n)
    return out


# --- surface feature extraction --------------------------------------------
def _nfkc(s):
    return unicodedata.normalize("NFKC", s)


def extract_numbers(s):
    """All digit runs (incl. decimals). '150至250' -> [150, 250]."""
    return re.findall(r"\d+(?:\.\d+)?", _nfkc(s))


def extract_years(s):
    return re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", _nfkc(s))


def extract_citations(s):
    return re.findall(r"\[(\d+)\]", _nfkc(s))


# alias -> canonical unit. ASCII aliases matched with letter boundaries;
# CJK aliases matched as plain substrings.
# NOTE: CJK length words 纳米/微米 are deliberately absent -- they are usually
# noun prefixes (纳米二氧化钛 = nano-titania), not measurement units, and would
# false-fire. Only aliases that behave as measurement units are listed.
UNIT_ALIASES = [
    ("percent", ["%", "％", "percent", "百分比"]),
    ("degC", ["°C", "℃", "摄氏度", "degrees Celsius", "degrees centigrade"]),
    ("nm", ["nm"]),
    ("um", ["μm", "µm"]),
    ("MPa", ["MPa", "兆帕"]),
    ("mL", ["mL", "毫升"]),
    ("h", ["小时"]),  # latin 'h' too noisy; CJK only
]


def extract_units(s):
    s = _nfkc(s)
    out = []
    for canon, aliases in UNIT_ALIASES:
        for a in aliases:
            if all(ord(c) < 128 for c in a):
                out += [canon] * len(re.findall(
                    r"(?<![A-Za-z])" + re.escape(a) + r"(?![A-Za-z])", s))
            else:
                out += [canon] * s.count(a)
    return out


def extract_latin_names(s):
    """Proper-noun-ish latin tokens: acronyms (SCR), formulas (NH3,
    MnOx-CeO2/TiO2), mixed-case names (NOx). Excludes plain capitalized
    sentence-start words ('The', 'In') and pure numbers."""
    toks = re.findall(r"[A-Za-z0-9]+(?:[-/·][A-Za-z0-9]+)*", _nfkc(s))
    keep = []
    for t in toks:
        if len(t) < 2:
            continue
        if all(c.isdigit() or c in "-/·" for c in t):
            continue
        ups = sum(1 for c in t if c.isupper())
        has_digit = any(c.isdigit() for c in t)
        if has_digit or ups >= 2:
            keep.append(t)
    return keep


def extract_zh_quoted(s):
    out = re.findall(r"《([^》]+)》", s)
    out += re.findall(r"“([^”]+)”", s)
    out += re.findall(r"「([^」]+)」", s)
    return out


CHECKS = [
    ("numbers", extract_numbers),
    ("units", extract_units),
    ("years", extract_years),
    ("latin_proper_nouns", extract_latin_names),
    ("citations", extract_citations),
]


# --- subcommands -------------------------------------------------------------
def cmd_align(zh_path, en_path):
    with open(zh_path, "r", encoding="utf-8") as f:
        zh_sents = split_sentences(f.read())
    with open(en_path, "r", encoding="utf-8") as f:
        en_sents = split_sentences(f.read())
    pairs = []
    for i in range(min(len(zh_sents), len(en_sents))):
        pairs.append({
            "pair_id": "p%04d" % (i + 1),
            "zh_id": zh_sents[i]["id"],
            "en_id": en_sents[i]["id"],
            "zh_text": zh_sents[i]["text"],
            "en_text": en_sents[i]["text"],
        })
    unaligned_zh = zh_sents[len(pairs):]
    unaligned_en = en_sents[len(pairs):]
    return {
        "tool": "align.py",
        "version": VERSION,
        "command": "align",
        "zh_file": zh_path,
        "en_file": en_path,
        "zh_sentence_count": len(zh_sents),
        "en_sentence_count": len(en_sents),
        "pair_count": len(pairs),
        "counts_match": len(zh_sents) == len(en_sents),
        "pairs": pairs,
        "unaligned": {
            "zh": unaligned_zh,
            "en": unaligned_en,
            "note": ("Counts match." if not (unaligned_zh or unaligned_en) else
                     "Sentence counts differ: every unaligned sentence is listed "
                     "here and must be resolved by the Agent before delivery."),
        },
    }


def _counter_diff(a, b):
    """Items in Counter a that exceed Counter b, as a sorted flat list."""
    diff = a - b
    out = []
    for k in sorted(diff):
        out.extend([k] * diff[k])
    return out


def coverage_check(alignment, alignment_name):
    pair_reports = []
    for pair in alignment["pairs"]:
        mismatches = {}
        for check_name, extractor in CHECKS:
            zh_items = Counter(extractor(pair["zh_text"]))
            en_items = Counter(extractor(pair["en_text"]))
            missing_in_en = _counter_diff(zh_items, en_items)
            missing_in_zh = _counter_diff(en_items, zh_items)
            if missing_in_en or missing_in_zh:
                mismatches[check_name] = {
                    "missing_in_en": missing_in_en,
                    "missing_in_zh": missing_in_zh,
                }
        unverified = []
        for q in extract_zh_quoted(pair["zh_text"]):
            if not any(ord(c) > 127 for c in q) and q in pair["en_text"]:
                continue  # latin quoted string found verbatim on en side
            unverified.append({
                "zh_quoted_string": q,
                "reason": "CJK quoted/titled string cannot be matched "
                          "mechanically; verify its English rendering by eye.",
            })
        pair_reports.append({
            "pair_id": pair["pair_id"],
            "zh_id": pair["zh_id"],
            "en_id": pair["en_id"],
            "status": "fail" if mismatches else "pass",
            "mismatches": mismatches,
            "unverified": unverified,
        })
    passed = sum(1 for p in pair_reports if p["status"] == "pass")
    failed = len(pair_reports) - passed
    return {
        "tool": "align.py",
        "version": VERSION,
        "command": "coverage",
        "alignment_file": alignment_name,
        "checks": [c for c, _ in CHECKS],
        "pairs": pair_reports,
        "summary": {
            "pair_count": len(pair_reports),
            "passed": passed,
            "failed": failed,
            "all_conserved": failed == 0,
            "gate_rule": ("If all_conserved is false, the failed pairs must be "
                          "fixed or explicitly justified, and the overall task "
                          "status MUST NOT be reported as success."),
        },
        "caveat": ("Surface conservation only: proves no number/unit/year/name/"
                   "citation was dropped or added. Does NOT prove faithful "
                   "meaning or idiomatic English."),
    }


def render_alignment_table(alignment, coverage):
    cov_by_pair = {p["pair_id"]: p for p in coverage["pairs"]}

    def esc(s):
        return s.replace("|", "\\|")

    lines = []
    lines.append("# zh–en alignment table (synthetic minimal example)")
    lines.append("")
    lines.append("Aligned by sentence order: %d zh sentences, %d en sentences, %d pairs."
                 % (alignment["zh_sentence_count"], alignment["en_sentence_count"],
                    alignment["pair_count"]))
    if not alignment["counts_match"]:
        lines.append("")
        lines.append("**WARNING: sentence counts differ; unaligned sentences listed below.**")
    lines.append("")
    lines.append("| pair | zh (source) | en (translation) | conservation |")
    lines.append("|---|---|---|---|")
    for pair in alignment["pairs"]:
        cov = cov_by_pair[pair["pair_id"]]
        if cov["status"] == "pass":
            cov_cell = "pass"
        else:
            bits = []
            for check, detail in sorted(cov["mismatches"].items()):
                frag = []
                if detail["missing_in_en"]:
                    frag.append("en missing %s" % ",".join(detail["missing_in_en"]))
                if detail["missing_in_zh"]:
                    frag.append("zh missing %s" % ",".join(detail["missing_in_zh"]))
                bits.append("%s: %s" % (check, "; ".join(frag)))
            cov_cell = "FAIL — " + "; ".join(bits)
        lines.append("| %s | %s | %s | %s |" % (
            pair["pair_id"], esc(pair["zh_text"]), esc(pair["en_text"]), cov_cell))
    lines.append("")
    un = alignment["unaligned"]
    if un["zh"] or un["en"]:
        lines.append("## Unaligned sentences (must be resolved, never dropped)")
        lines.append("")
        for s in un["zh"]:
            lines.append("- zh %s: %s" % (s["id"], s["text"]))
        for s in un["en"]:
            lines.append("- en %s: %s" % (s["id"], s["text"]))
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("Coverage summary: %d/%d pairs conserved; all_conserved=%s. %s"
                 % (coverage["summary"]["passed"], coverage["summary"]["pair_count"],
                    str(coverage["summary"]["all_conserved"]).lower(),
                    coverage["caveat"]))
    lines.append("")
    return "\n".join(lines)


def backtrans_template(alignment, alignment_name):
    return {
        "tool": "align.py",
        "version": VERSION,
        "command": "backtrans-template",
        "alignment_file": alignment_name,
        "instructions": {
            "who_fills": ("The Agent (LLM), never this script. For each pair, "
                          "translate en_text back into Chinese WITHOUT looking at "
                          "zh_text, then compare."),
            "equivalence_labels": {
                "equivalent": "same facts, same strength; wording may differ",
                "minor-difference": "meaning preserved but strength/detail shifted; record it in note",
                "mismatch": "fact, number, negation or strength changed; pair must be fixed",
            },
            "after_filling": "Run: align.py backtrans-check --backtrans <this file> --out <json>",
        },
        "pairs": [
            {
                "pair_id": p["pair_id"],
                "zh_text": p["zh_text"],
                "en_text": p["en_text"],
                "back_translation": "",
                "equivalence": "",
                "note": "",
            } for p in alignment["pairs"]
        ],
    }


def backtrans_check(worksheet, worksheet_name):
    VALID = ("equivalent", "minor-difference", "mismatch")
    counts = {"equivalent": 0, "minor_difference": 0, "mismatch": 0,
              "missing": 0, "invalid_label": 0}
    uncertainty = []
    for p in worksheet.get("pairs", []):
        pid = p.get("pair_id", "?")
        bt = (p.get("back_translation") or "").strip()
        eq = (p.get("equivalence") or "").strip()
        note = (p.get("note") or "").strip()
        if not bt:
            counts["missing"] += 1
            uncertainty.append({"pair_id": pid,
                                "reason": "back_translation not filled"})
            continue
        if eq not in VALID:
            counts["invalid_label"] += 1
            uncertainty.append({"pair_id": pid,
                                "reason": "equivalence label empty/invalid "
                                          "(expected one of %s)" % "|".join(VALID)})
            continue
        if eq == "mismatch":
            counts["mismatch"] += 1
            uncertainty.append({"pair_id": pid,
                                "reason": "equivalence=mismatch",
                                "note": note})
        elif eq == "minor-difference":
            counts["minor_difference"] += 1
        else:
            counts["equivalent"] += 1
    total = sum(counts.values())
    gate = "pass" if not uncertainty else "fail"
    return {
        "tool": "align.py",
        "version": VERSION,
        "command": "backtrans-check",
        "backtrans_file": worksheet_name,
        "total_pairs": total,
        "counts": counts,
        "gate": gate,
        "uncertainty": uncertainty,
        "gate_rule": ("Pairs with an empty back_translation, an invalid/empty "
                      "equivalence label, or equivalence=mismatch MUST enter "
                      "uncertainty and forbid status=success. The Agent (LLM) "
                      "produced the back-translations and labels; this script "
                      "only gates and counts -- it cannot judge semantic "
                      "equivalence itself."),
    }


def _write_out(text, out_path):
    if out_path == "-":
        sys.stdout.write(text)
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="zh/en alignment, conservation coverage, back-translation gating.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_a = sub.add_parser("align", help="Build zh<->en sentence-pair table by order.")
    p_a.add_argument("--zh", required=True)
    p_a.add_argument("--en", required=True)
    p_a.add_argument("--out", required=True, help="Output JSON path or '-'.")

    p_c = sub.add_parser("coverage", help="Cross-language conservation check.")
    p_c.add_argument("--alignment", required=True)
    p_c.add_argument("--out", required=True, help="Output JSON path or '-'.")
    p_c.add_argument("--table", default=None,
                     help="Optional Markdown alignment table path or '-'.")

    p_t = sub.add_parser("backtrans-template", help="Emit back-translation worksheet.")
    p_t.add_argument("--alignment", required=True)
    p_t.add_argument("--out", required=True, help="Output JSON path or '-'.")

    p_b = sub.add_parser("backtrans-check", help="Gate a filled worksheet.")
    p_b.add_argument("--backtrans", required=True)
    p_b.add_argument("--out", required=True, help="Output JSON path or '-'.")

    args = ap.parse_args(argv)

    if args.cmd == "align":
        result = cmd_align(args.zh, args.en)
        _write_out(_dump(result), args.out)
        print("align: %d zh + %d en -> %d pairs (counts_match=%s) -> %s"
              % (result["zh_sentence_count"], result["en_sentence_count"],
                 result["pair_count"], result["counts_match"], args.out),
              file=sys.stderr)
    elif args.cmd == "coverage":
        with open(args.alignment, "r", encoding="utf-8") as f:
            alignment = json.load(f)
        cov = coverage_check(alignment, args.alignment)
        _write_out(_dump(cov), args.out)
        print("coverage: %d/%d pairs conserved (all_conserved=%s) -> %s"
              % (cov["summary"]["passed"], cov["summary"]["pair_count"],
                 cov["summary"]["all_conserved"], args.out), file=sys.stderr)
        if args.table:
            with open(args.alignment, "r", encoding="utf-8") as f:
                alignment = json.load(f)
            _write_out(render_alignment_table(alignment, cov), args.table)
            print("coverage: alignment table -> %s" % args.table, file=sys.stderr)
    elif args.cmd == "backtrans-template":
        with open(args.alignment, "r", encoding="utf-8") as f:
            alignment = json.load(f)
        ws = backtrans_template(alignment, args.alignment)
        _write_out(_dump(ws), args.out)
        print("backtrans-template: %d empty pairs -> %s (Agent must fill)"
              % (len(ws["pairs"]), args.out), file=sys.stderr)
    elif args.cmd == "backtrans-check":
        with open(args.backtrans, "r", encoding="utf-8") as f:
            ws = json.load(f)
        result = backtrans_check(ws, args.backtrans)
        _write_out(_dump(result), args.out)
        print("backtrans-check: gate=%s, uncertainty=%d -> %s"
              % (result["gate"], len(result["uncertainty"]), args.out),
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
