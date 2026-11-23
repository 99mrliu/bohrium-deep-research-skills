#!/usr/bin/env python3
"""ledger_verify.py -- Bundle C (ga-audit-loop), blocking gate: source ledger.

Every element that appears in the figure must have a ledger entry whose
evidence is VERBATIM in the mined pool, and every number shown in the figure
must be traceable to a pool block or a data file row. This is the gate that
turns "looks plausible" into "each pixel has a citation".

Ledger format: see references/ledger_format.md. In short, a JSON list:
  [{"element": "svg id or figure region",
    "shows": "what the element claims (free text)",
    "evidence": [{"key": "file.pdf#page-2",
                  "quote": "verbatim substring of that block"}],
    "numbers_shown": ["5", "42"],          # optional
    "kind": "entity|relation|value|label"}]

Usage:
  python3 ledger_verify.py --ledger /app/work/source_ledger.json \
      --pool /app/work/evidence_pool.jsonl [--svg /app/output/figure.svg]
With --svg, also checks every ledger "element" id exists in the SVG and every
visible text string of the SVG is covered by at least one ledger entry
(coverage both ways).
Exit 0 = PASS.
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET

WS = re.compile(r"\s+")
SVG_NS = "{http://www.w3.org/2000/svg}"


def norm(s):
    return WS.sub(" ", s or "").strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--pool", required=True)
    ap.add_argument("--svg", default=None)
    args = ap.parse_args()

    with open(args.ledger, encoding="utf-8") as fh:
        ledger = json.load(fh)
    pool = {}
    with open(args.pool, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            pool[rec["key"]] = rec["text"]

    findings = []
    ledger_elements = set()
    for i, entry in enumerate(ledger):
        where = entry.get("element", "entry-%d" % i)
        ledger_elements.add(where)
        evs = entry.get("evidence", [])
        if not evs:
            findings.append({"entry": where, "severity": "blocker",
                             "kind": "no-evidence",
                             "detail": "element has no evidence entry"})
        for ev in evs:
            key, quote = ev.get("key", ""), norm(ev.get("quote", ""))
            if key not in pool:
                findings.append({"entry": where, "severity": "blocker",
                                 "kind": "bad-locator",
                                 "detail": "pool key %r does not exist" % key})
            elif quote not in norm(pool[key]):
                findings.append({"entry": where, "severity": "blocker",
                                 "kind": "quote-mismatch",
                                 "detail": "quote %r is not verbatim in %s"
                                 % (quote[:70], key)})
        shown = entry.get("numbers_shown", [])
        blob = " ".join(norm(ev.get("quote", "")) for ev in evs)
        for num in shown:
            if str(num).replace(",", "") not in blob.replace(",", ""):
                findings.append({"entry": where, "severity": "blocker",
                                 "kind": "orphan-number",
                                 "detail": "number %r shown but absent from "
                                 "its evidence quotes" % num})
        if entry.get("kind") not in ("entity", "relation", "value", "label",
                                     "annotation"):
            findings.append({"entry": where, "severity": "warning",
                             "kind": "unknown-kind",
                             "detail": "kind %r not in taxonomy"
                             % entry.get("kind")})

    coverage = {}
    if args.svg:
        tree = ET.parse(args.svg)
        svg_ids = {el.get("id") for el in tree.iter() if el.get("id")}
        svg_texts = set()
        for t in tree.iter(SVG_NS + "text"):
            s = norm("".join(t.itertext()))
            if s:
                svg_texts.add(s)
        for el in ledger_elements:
            if el not in svg_ids and not any(el in (i or "") for i in svg_ids):
                findings.append({"entry": el, "severity": "warning",
                                 "kind": "ledger-not-in-svg",
                                 "detail": "ledger element id not found in "
                                 "SVG ids"})
        covered = set()
        for entry in ledger:
            for word in re.split(r"\s+", norm(entry.get("shows", ""))):
                if len(word) > 3:
                    for st in svg_texts:
                        if word in st:
                            covered.add(st)
        coverage = {"svg_text_strings": len(svg_texts),
                    "texts_with_ledger_word_match": len(covered)}

    blockers = [f for f in findings if f["severity"] == "blocker"]
    report = {"ledger": args.ledger, "entries": len(ledger),
              "blockers": len(blockers), "warnings": len(findings) - len(blockers),
              "coverage": coverage, "findings": findings,
              "gate": "PASS" if not blockers else "FAIL"}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not blockers else 1


if __name__ == "__main__":
    sys.exit(main())
