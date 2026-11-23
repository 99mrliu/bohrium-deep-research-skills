#!/usr/bin/env python3
"""Assumption / approximation / boundary-condition radar.

Scans the prose of the publisher XML (or a plain-text fallback) for markers
that license or limit a derivation step, anchors each hit to its section and
the formulas of that section, and quotes the sentence verbatim as evidence.
Stdlib only.
"""
import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

MARKERS = [
    (r"\bassum\w+", "assumption"),
    (r"\bapproximat\w+", "approximation"),
    (r"\bvalid\s+(?:for|when|only)", "validity_domain"),
    (r"\bunder\s+the\s+condition", "condition"),
    (r"\bneglect\w*", "neglected_term"),
    (r"\bignore[sd]?\b", "neglected_term"),
    (r"\blimit\b", "limiting_case"),
    (r"\bfirst[- ]order\b", "series_order"),
    (r"\bTaylor\b", "series_expansion"),
    (r"\bboundary\s+condition", "boundary_condition"),
    (r"\bvanish\w*", "limiting_case"),
    (r"\bsmall\b", "small_parameter"),
    (r"假设", "assumption"),
    (r"近似", "approximation"),
    (r"边界条件", "boundary_condition"),
    (r"忽略", "neglected_term"),
    (r"成立条件", "validity_domain"),
    (r"极限", "limiting_case"),
]


def local(tag):
    return tag.rsplit("}", 1)[-1]


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.。；;!！？?])\s+", text) if s.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--input", default=None)
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()
    case_path = Path(args.case)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    input_root = Path(args.input) if args.input else case_path.parent
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    artifacts = (case.get("artifacts") or {})
    pub = artifacts.get("publisher_source_xml")

    hits = []
    if pub and (input_root / pub).exists():
        root = ET.parse(input_root / pub).getroot()
        for sec in [el for el in root.iter() if local(el.tag) == "sec"] or [root]:
            sid = sec.get("id", "?")
            formulas = sorted({el.get("id") for el in sec.iter()
                               if local(el.tag) == "math" and el.get("id")})
            text = "\n".join("".join(el.itertext()) for el in sec.iter()
                             if local(el.tag) in ("p", "title"))
            for sent in sentences(text):
                kinds = [k for pat, k in MARKERS if re.search(pat, sent)]
                if kinds:
                    hits.append({"section": sid, "kinds": sorted(set(kinds)),
                                 "nearby_formulas": formulas,
                                 "quote": sent[:400]})
    report = {"hits": hits, "marker_kinds": sorted({k for h in hits for k in h["kinds"]}),
              "note": "pattern hits are evidence-bearing quotes; the agent "
                      "confirms which ones actually license a step"}
    (work / "assumptions.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("assumption radar: %d hits, kinds=%s -> %s"
          % (len(hits), report["marker_kinds"], work / "assumptions.json"))


if __name__ == "__main__":
    main()
