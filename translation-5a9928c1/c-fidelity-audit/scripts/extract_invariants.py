#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_invariants.py — mine fidelity invariants from the SOURCE side of bilingual segment pairs.

Usage:
  python3 extract_invariants.py --pairs pairs.jsonl --out invariants.json
  python3 extract_invariants.py --src source.txt --out invariants.json

pairs.jsonl: one JSON object per line, keys {"seg_id","source","target"} (target may be absent here).
--src: plain text, blank-line separated segments, seg_id auto-assigned S001, S002, ...

Output (deterministic order):
{"segments":[{"seg_id","invariants":{"numbers":[{"raw","value","unit"}],
  "citations":[...],"refs":[...],"negations":[...],"hedges":[...]}}], "stats":{...}}

Python 3.8+, stdlib only.
"""
import argparse
import json
import re
import sys
from collections import OrderedDict

# ---------------------------------------------------------------- unit lexicon
# Longer alternatives first so regex prefers them (e.g. "mL" before "L", "kHz" before "Hz").
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

# Numbers: integers/decimals with optional thousands separators, optional unit, optional sci-notation.
NUMBER_RE = re.compile(
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?P<sci>\s*(?:×|x)\s*10\^?-?\d+|\s*[eE][+-]?\d+)?"
    r"(?P<unit>\s*" + UNIT_RE + r")?"
)

# Citations: [12], [3,4], [5-9], [3, 7-9]; and (Surname, 2020) / (Surname et al., 2020).
CIT_BRACKET_RE = re.compile(r"\[(\d+(?:\s*[-,]\s*\d+)*)\]")
CIT_AUTHOR_RE = re.compile(
    r"\(([A-Z][A-Za-z\-']+(?:\s+(?:et\s+al\.?|and\s+[A-Z][A-Za-z\-']+))?,\s*\d{4}[a-z]?)\)"
)

# Figure/Table/Equation references (EN + ZH).
REF_RE = re.compile(
    r"(?P<kind>Fig(?:ure)?s?\.?|Tables?|图|表|Eq(?:uation)?s?\.?|式)\s*[（(]?"
    r"(?P<num>\d+(?:\s*[-–,]\s*\d+)*)[）)]?"
)

# Negation cues (word-boundary, EN source side).
NEGATION_RE = re.compile(
    r"\b(?:no|not|never|without|cannot|can't|fails?\s+to|failed\s+to|neither|nor|none|unable)\b",
    re.IGNORECASE,
)

# Hedge / contrast cues.
HEDGE_RE = re.compile(
    r"\b(?:however|although|though|whereas|while|may|might|could|approximately|about|around|"
    r"up\s+to|at\s+most|at\s+least|only)\b",
    re.IGNORECASE,
)


def normalize_number_value(raw_num):
    """Strip thousands separators -> canonical value string (keep as written otherwise)."""
    return raw_num.replace(",", "")


def parse_sci(sci_text):
    """Return multiplier exponent int from '×10^3' / 'x10-2' / 'e+4' style text, else None."""
    if not sci_text:
        return None
    t = sci_text.strip()
    m = re.search(r"(?:×|x)\s*10\^?(-?\d+)", t)
    if m:
        return int(m.group(1))
    m = re.search(r"[eE]([+-]?\d+)$", t)
    if m:
        return int(m.group(1))
    return None


def _mask_spans(text, *regexes):
    """Blank out citation / ref spans so their digits are not mined as numbers."""
    chars = list(text)
    for rx in regexes:
        for m in rx.finditer(text):
            for i in range(m.start(), m.end()):
                chars[i] = " "
    return "".join(chars)


def extract_numbers(text):
    out = []
    text = _mask_spans(text, CIT_BRACKET_RE, CIT_AUTHOR_RE, REF_RE)
    for m in NUMBER_RE.finditer(text):
        raw_num = m.group("num")
        value = normalize_number_value(raw_num)
        sci = parse_sci(m.group("sci"))
        unit = (m.group("unit") or "").strip() or None
        raw = m.group(0).strip()
        entry = OrderedDict()
        entry["raw"] = raw
        entry["value"] = value
        entry["unit"] = unit
        if sci is not None:
            entry["sci_exp"] = sci
        out.append(entry)
    return out


def extract_citations(text):
    out = []
    for m in CIT_BRACKET_RE.finditer(text):
        out.append("[" + re.sub(r"\s+", "", m.group(1)) + "]")
    for m in CIT_AUTHOR_RE.finditer(text):
        out.append("(" + re.sub(r"\s+", " ", m.group(1)).strip() + ")")
    return out


def extract_refs(text):
    out = []
    for m in REF_RE.finditer(text):
        kind = m.group("kind")
        nums = re.sub(r"\s+", "", m.group("num"))
        # canonical kind bucket
        low = kind.lower().rstrip(".")
        if low.startswith("fig"):
            canon = "Fig."
        elif low.startswith("table"):
            canon = "Table"
        elif kind == "图":
            canon = "Fig."
        elif kind == "表":
            canon = "Table"
        else:
            canon = "Eq."
        out.append(canon + " " + nums)
    return out


def extract_cues(regex, text):
    return [re.sub(r"\s+", " ", m.group(0)).lower() for m in regex.finditer(text)]


def analyze_segment(seg_id, source):
    inv = OrderedDict()
    inv["numbers"] = extract_numbers(source)
    inv["citations"] = extract_citations(source)
    inv["refs"] = extract_refs(source)
    inv["negations"] = extract_cues(NEGATION_RE, source)
    inv["hedges"] = extract_cues(HEDGE_RE, source)
    return OrderedDict([("seg_id", seg_id), ("invariants", inv)])


def read_pairs(path):
    pairs = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                sys.exit("error: %s line %d: invalid JSON: %s" % (path, lineno, exc))
            if "seg_id" not in obj or "source" not in obj:
                sys.exit("error: %s line %d: need keys seg_id and source" % (path, lineno))
            pairs.append(obj)
    return pairs


def read_src(path):
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    chunks = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
    return [{"seg_id": "S%03d" % (i + 1), "source": c} for i, c in enumerate(chunks)]


def main():
    ap = argparse.ArgumentParser(description="Mine fidelity invariants from source segments.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pairs", help="JSONL with {seg_id, source, target} per line")
    src.add_argument("--src", help="plain text, blank-line separated segments (auto seg_id)")
    ap.add_argument("--out", required=True, help="output invariants.json")
    args = ap.parse_args()

    segs = read_pairs(args.pairs) if args.pairs else read_src(args.src)
    segments = [analyze_segment(s["seg_id"], s["source"]) for s in segs]

    stats = OrderedDict()
    stats["segments"] = len(segments)
    for key in ("numbers", "citations", "refs", "negations", "hedges"):
        stats[key] = sum(len(s["invariants"][key]) for s in segments)

    out = OrderedDict([("segments", segments), ("stats", stats)])
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("wrote %s: %d segments, stats=%s" % (args.out, stats["segments"], dict(stats)))


if __name__ == "__main__":
    main()
