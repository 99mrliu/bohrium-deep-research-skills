#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_fidelity.py — gate: compare source invariants against target translations.

Usage:
  python3 check_fidelity.py --invariants invariants.json --pairs pairs.jsonl \
      --out fidelity_report.json [--md fidelity_report.md]

Severity model:
  BLOCKER: number-dropped, number-changed, unit-changed, citation-lost, ref-lost, negation-lost
  WARNING: hedge-lost, number-format
Exit code: 1 if any blocker, else 0.
Python 3.8+, stdlib only. No network, no ML — deterministic string checks only.
"""
import argparse
import json
import re
import sys
from collections import Counter, OrderedDict

# ---------------------------------------------------------------- shared lexicon
UNITS = [
    "cm\\^2", "cm2", "m/s",
    "μm", "µm", "um", "μL", "µL", "uL", "μM", "µM", "uM",
    "μmol", "umol", "mmol",
    "nm", "mm", "cm", "mV", "mA", "mW", "kW", "mM", "nM",
    "kHz", "MHz", "GPa", "MPa", "keV", "kJ",
    "°C", "℃",
    "min", "ms", "mL", "mol",
    "Hz", "Pa", "eV",
    "mg", "kg",
    "h", "s", "g", "V", "A", "W", "K", "J", "M", "L",
    "rpm", "lx", "%",
]
UNIT_RE = "(?:" + "|".join(UNITS) + ")"

NUMBER_RE = re.compile(
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?P<unit>\s*" + UNIT_RE + r")?"
)

REF_RE = re.compile(
    r"(?P<kind>Fig(?:ure)?s?\.?|Tables?|图|表|Eq(?:uation)?s?\.?|式)\s*[（(]?"
    r"(?P<num>\d+(?:\s*[-–,]\s*\d+)*)[）)]?"
)

ZH_NEGATION = ["无法", "不能", "没有", "缺乏", "不", "未", "无", "非", "否"]
ZH_HEDGE = ["可能", "或许", "大约", "约", "至多", "至少", "仅", "然而", "尽管", "虽然"]

BLOCKER = "blocker"
WARNING = "warning"
REFERENCES_LIST_MIN_CITATIONS = 3


def normalize_unit(unit):
    if unit is None:
        return None
    u = unit.strip().replace(" ", "")
    u = u.replace("µ", "μ")          # micro sign -> greek mu
    u = re.sub(r"(?<![A-Za-zμ°])u(?=m|M|L)", "μ", u)  # ASCII 'u' as micro prefix
    u = u.replace("℃", "°C")
    return u or None


def value_variants(value, raw):
    """Candidate surface forms for a source numeric value."""
    forms = {value, raw}
    try:
        f = float(value)
        if f == int(f):
            forms.add(str(int(f)))
        forms.add(("%f" % f).rstrip("0").rstrip("."))
    except ValueError:
        pass
    return {v for v in forms if v}


def value_in_text(value, raw, text):
    """True if the value appears in text, tolerating thousands separators and spacing."""
    text_nocomma = text.replace(",", "")
    text_nospace = text_nocomma.replace(" ", "").replace("　", "")
    for v in value_variants(value, raw):
        if v in text_nocomma or v.replace(",", "") in text_nocomma:
            return True
        if v.replace(",", "") in text_nospace:
            return True
    return False


CIT_BRACKET_RE = re.compile(r"\[(\d+(?:\s*[-,]\s*\d+)*)\]")


def _mask_spans(text, *regexes):
    chars = list(text)
    for rx in regexes:
        for m in rx.finditer(text):
            for i in range(m.start(), m.end()):
                chars[i] = " "
    return "".join(chars)


def extract_target_numbers(text):
    out = []
    text = _mask_spans(text, CIT_BRACKET_RE, REF_RE)
    for m in NUMBER_RE.finditer(text):
        out.append({
            "raw": m.group(0).strip(),
            "value": m.group("num").replace(",", ""),
            "unit": normalize_unit(m.group("unit")),
            "start": m.start(),
            "end": m.end(),
        })
    return out


def target_refs(text):
    out = []
    for m in REF_RE.finditer(text):
        kind = m.group("kind")
        nums = re.sub(r"\s+", "", m.group("num"))
        low = kind.lower().rstrip(".")
        if low.startswith("fig") or kind == "图":
            canon = "Fig."
        elif low.startswith("table") or kind == "表":
            canon = "Table"
        else:
            canon = "Eq."
        out.append(canon + " " + nums)
    return out


def snippet(text, needle, width=40):
    if not needle:
        return text[:width] + ("..." if len(text) > width else "")
    i = text.find(needle)
    if i < 0:
        return text[:width] + ("..." if len(text) > width else "")
    a = max(0, i - 10)
    b = min(len(text), i + len(needle) + width - 10)
    return text[a:b]


def unit_adjacent_to_value(target, value):
    """Find an occurrence of value in target and return the normalized unit right after it."""
    t = target.replace(",", "")
    for m in re.finditer(re.escape(value), t):
        tail = t[m.end(): m.end() + 12]
        um = re.match(r"\s*(" + UNIT_RE + r")", tail)
        if um:
            return normalize_unit(um.group(1))
        return None
    return None


def check_segment(seg, target_text, findings):
    seg_id = seg["seg_id"]
    inv = seg["invariants"]
    checks = 0
    src_numbers = inv["numbers"]
    src_num_values = {n["value"] for n in src_numbers}
    tgt_numbers = extract_target_numbers(target_text)

    # ---- numbers -----------------------------------------------------------
    for n in src_numbers:
        checks += 1
        if not value_in_text(n["value"], n["raw"], target_text):
            findings.append(OrderedDict([
                ("seg_id", seg_id), ("code", "number-dropped"), ("severity", BLOCKER),
                ("evidence_source", snippet(seg_source(seg), n["raw"])),
                ("evidence_target", ""),
                ("note", "源文数字 %s 在译文中未出现（含归一化形式）" % n["raw"]),
            ]))
            continue
        if "," in n["raw"]:
            findings.append(OrderedDict([
                ("seg_id", seg_id), ("code", "number-format"), ("severity", WARNING),
                ("evidence_source", n["raw"]),
                ("evidence_target", snippet(target_text, n["value"])),
                ("note", "数字以归一化形式匹配（千分位/格式差异），请人工确认"),
            ]))
        src_unit = normalize_unit(n.get("unit"))
        if src_unit:
            checks += 1
            tgt_unit = unit_adjacent_to_value(target_text, n["value"])
            if tgt_unit and tgt_unit != src_unit:
                findings.append(OrderedDict([
                    ("seg_id", seg_id), ("code", "unit-changed"), ("severity", BLOCKER),
                    ("evidence_source", n["raw"]),
                    ("evidence_target", snippet(target_text, n["value"])),
                    ("note", "源文单位 %s，译文相邻单位 %s" % (src_unit, tgt_unit)),
                ]))

    # ---- number-changed: target number with same unit but alien value -------
    for tn in tgt_numbers:
        if tn["unit"] is None:
            continue
        checks += 1
        for n in src_numbers:
            src_unit = normalize_unit(n.get("unit"))
            if src_unit and tn["unit"] == src_unit and tn["value"] != n["value"]:
                if tn["value"] not in src_num_values:
                    findings.append(OrderedDict([
                        ("seg_id", seg_id), ("code", "number-changed"), ("severity", BLOCKER),
                        ("evidence_source", n["raw"]),
                        ("evidence_target", snippet(target_text, tn["raw"])),
                        ("note", "译文数字 %s（单位 %s 与源文一致）取值与源文 %s 不同且未见于源文"
                                 % (tn["raw"], tn["unit"], n["value"])),
                    ]))
                break

    # ---- citations ----------------------------------------------------------
    checks += 1
    src_cits = Counter(inv["citations"])
    tgt_cits = Counter(extract_citations_from_target(target_text))
    missing = src_cits - tgt_cits
    for cit, cnt in sorted(missing.items()):
        findings.append(OrderedDict([
            ("seg_id", seg_id), ("code", "citation-lost"), ("severity", BLOCKER),
            ("evidence_source", snippet(seg_source(seg), cit)),
            ("evidence_target", ""),
            ("note", "引文 %s 在译文中缺失（少 %d 处）" % (cit, cnt)),
        ]))

    # ---- figure/table/equation refs ----------------------------------------
    checks += 1
    src_refs = Counter(inv["refs"])
    tgt_refs = Counter(target_refs(target_text))
    missing_refs = src_refs - tgt_refs
    for ref, cnt in sorted(missing_refs.items()):
        findings.append(OrderedDict([
            ("seg_id", seg_id), ("code", "ref-lost"), ("severity", BLOCKER),
            ("evidence_source", snippet(seg_source(seg), ref.split()[-1])),
            ("evidence_target", ""),
            ("note", "图表/公式引用 %s 在译文中缺失（少 %d 处）" % (ref, cnt)),
        ]))

    # ---- negation / hedge (skipped for reference-list-like segments) --------
    is_ref_list = len(inv["citations"]) >= REFERENCES_LIST_MIN_CITATIONS
    if not is_ref_list:
        if inv["negations"]:
            checks += 1
            if not any(c in target_text for c in ZH_NEGATION):
                findings.append(OrderedDict([
                    ("seg_id", seg_id), ("code", "negation-lost"), ("severity", BLOCKER),
                    ("evidence_source", snippet(seg_source(seg), inv["negations"][0])),
                    ("evidence_target", snippet(target_text, "")),
                    ("note", "源文含否定提示（%s），译文无任何否定标记（%s）"
                             % ("/".join(sorted(set(inv["negations"]))), "/".join(ZH_NEGATION))),
                ]))
        if inv["hedges"]:
            checks += 1
            if not any(c in target_text for c in ZH_HEDGE):
                findings.append(OrderedDict([
                    ("seg_id", seg_id), ("code", "hedge-lost"), ("severity", WARNING),
                    ("evidence_source", snippet(seg_source(seg), inv["hedges"][0])),
                    ("evidence_target", snippet(target_text, "")),
                    ("note", "源文含模糊/转折提示（%s），译文未体现（%s），请人工确认语气"
                             % ("/".join(sorted(set(inv["hedges"]))), "/".join(ZH_HEDGE))),
                ]))
    return checks


def extract_citations_from_target(text):
    out = []
    for m in re.finditer(r"\[(\d+(?:\s*[-,]\s*\d+)*)\]", text):
        out.append("[" + re.sub(r"\s+", "", m.group(1)) + "]")
    for m in re.finditer(r"\(([A-Z][A-Za-z\-']+(?:\s+(?:et\s+al\.?|and\s+[A-Z][A-Za-z\-']+))?,\s*\d{4}[a-z]?)\)", text):
        out.append("(" + re.sub(r"\s+", " ", m.group(1)).strip() + ")")
    return out


_SEG_SOURCE = {}


def seg_source(seg):
    return _SEG_SOURCE.get(seg["seg_id"], "")


def load_pairs(path):
    pairs = {}
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if "seg_id" not in obj:
                sys.exit("error: %s line %d missing seg_id" % (path, lineno))
            pairs[obj["seg_id"]] = obj
    return pairs


def render_md(report):
    lines = ["# Fidelity report", ""]
    s = report["summary"]
    lines.append("segments=%d checks=%d blockers=%d warnings=%d"
                 % (s["segments"], s["checks"], s["blockers"], s["warnings"]))
    lines.append("")
    lines.append("| seg_id | code | severity | source evidence | target evidence |")
    lines.append("|---|---|---|---|---|")
    for f in report["findings"]:
        lines.append("| %s | %s | %s | %s | %s |" % (
            f["seg_id"], f["code"], f["severity"],
            f["evidence_source"].replace("|", "\\|"),
            f["evidence_target"].replace("|", "\\|") or "—",
        ))
    if not report["findings"]:
        lines.append("| — | clean | — | — | — |")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Fidelity gate: source invariants vs target text.")
    ap.add_argument("--invariants", required=True)
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--md", help="optional markdown rendering of the report")
    args = ap.parse_args()

    with open(args.invariants, "r", encoding="utf-8") as fh:
        invariants = json.load(fh)
    pairs = load_pairs(args.pairs)

    findings = []
    total_checks = 0
    for seg in invariants["segments"]:
        sid = seg["seg_id"]
        pair = pairs.get(sid)
        if pair is None or "target" not in pair:
            findings.append(OrderedDict([
                ("seg_id", sid), ("code", "target-missing"), ("severity", BLOCKER),
                ("evidence_source", ""), ("evidence_target", ""),
                ("note", "缺少对应译文段落，无法核验（不静默通过）"),
            ]))
            continue
        _SEG_SOURCE[sid] = pair.get("source", "")
        total_checks += check_segment(seg, pair["target"], findings)

    blockers = sum(1 for f in findings if f["severity"] == BLOCKER)
    warnings = sum(1 for f in findings if f["severity"] == WARNING)
    report = OrderedDict([
        ("summary", OrderedDict([
            ("segments", len(invariants["segments"])),
            ("checks", total_checks),
            ("blockers", blockers),
            ("warnings", warnings),
        ])),
        ("findings", findings),
    ])
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    if args.md:
        with open(args.md, "w", encoding="utf-8") as fh:
            fh.write(render_md(report))
    print("segments=%d checks=%d blockers=%d warnings=%d -> %s"
          % (report["summary"]["segments"], total_checks, blockers, warnings, args.out))
    sys.exit(1 if blockers > 0 else 0)


if __name__ == "__main__":
    main()
