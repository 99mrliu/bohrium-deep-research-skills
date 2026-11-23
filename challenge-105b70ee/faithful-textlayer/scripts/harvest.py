#!/usr/bin/env python3
"""Harvest an evidence bank from the anchored text layer (no model requests).

Reads <work-dir>/textlayer.jsonl, writes:
  evidence_bank.jsonl  one entry per harvested sentence:
      {"bank_id","page","pid","source","quote","numbers","cues"}
  harvest_report.json  sweep statistics (per-page counts, zero-candidate
      pages) so a later `not_reported` status is auditable.

Sentences are harvested when they contain a number with a unit / range /
inequality / statistic marker, or a conclusion/limitation/hedge cue
(English + Chinese).
"""
import json
import os
import re
import sys

NUM = r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?"
NUM_RE = re.compile(
    r"(%s(?:\s*[±x×]\s*%s)?(?:\s*[–—-]\s*%s)?)" % (NUM, NUM, NUM))
UNIT_RE = re.compile(
    r"(%|‰|ppm|ppb|mAh|Wh|kg|mg|g|cm|mm|nm|µm|um|mV|kV|V|mA|A|kWh|kW|W|MPa|GPa|Pa"
    r"|K|°C|deg C|s|min|h|Hz|kHz|mol|mM|M|J|kJ|mL|L|nmol|cycles?|r\.?p\.?m|K\.)",
    re.IGNORECASE)
STAT_RE = re.compile(
    r"(±|std|SD|SEM|CI|R\^?2|R²|p\s*[<=>]|n\s*=|±\s*\d|error|deviation)",
    re.IGNORECASE)
CUES = {
    "conclusion": re.compile(
        r"\b(we (demonstrate|show|conclude|report|achiev)|in conclusion|"
        r"our results (show|demonstrate)|these results (show|demonstrate))\b"
        r"|本文(证明|表明|提出)|结果表明|综上", re.IGNORECASE),
    "limitation": re.compile(
        r"\b(limitation|limited to|drawback|however,? (we|the)|remains? "
        r"(unclear|unreported|unknown)|not (reported|determined))\b"
        r"|局限|受限于|尚未(报道|报道过)|仍不清楚", re.IGNORECASE),
    "speculation": re.compile(
        r"\b(may|might|could|suggests?|suggesting|likely|possibly|potential"
        r"ly?|we speculate|hypothesi[sz]e|indicate that)\b"
        r"|可能|提示|或许|有望|推测", re.IGNORECASE),
}
SENT_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")


def sentences(text):
    parts = SENT_SPLIT.split(text.replace("\n", " "))
    return [p.strip() for p in parts if p.strip()]


def main():
    work = sys.argv[sys.argv.index("--work-dir") + 1] if "--work-dir" in sys.argv \
        else os.environ.get("WORK_DIR", "/app/work")
    tl_path = os.path.join(work, "textlayer.jsonl")
    if not os.path.isfile(tl_path):
        print("missing %s — run textlayer.py first" % tl_path, file=sys.stderr)
        return 2
    bank, report = [], {"pages": {}, "by_kind": {"quantified": 0, "cued": 0}}
    eid = 0
    for line in open(tl_path, encoding="utf-8"):
        e = json.loads(line)
        page_key = "%s:%d" % (e["source"], e["page"])
        report["pages"].setdefault(page_key, 0)
        for s in sentences(e["text"]):
            nums = NUM_RE.findall(s)
            has_unit = bool(UNIT_RE.search(s)) or bool(STAT_RE.search(s))
            cues = [k for k, rx in CUES.items() if rx.search(s)]
            is_range = bool(re.search(r"\d\s*[–—]\s*\d", s))
            quantified = bool(nums) and (has_unit or is_range or
                                         bool(re.search(r"[<>≥≤≈~]\s*\d", s)))
            if not quantified and not cues:
                continue
            eid += 1
            bank.append({
                "bank_id": "E%04d" % eid,
                "page": e["page"], "pid": e["pid"], "source": e["source"],
                "quote": s,
                "numbers": nums if quantified else [],
                "cues": cues + (["quantified"] if quantified else []),
            })
            report["pages"][page_key] += 1
            report["by_kind"]["quantified" if quantified else "cued"] += 1
    with open(os.path.join(work, "evidence_bank.jsonl"), "w", encoding="utf-8") as f:
        for b in bank:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")
    report["total"] = len(bank)
    report["zero_candidate_pages"] = [p for p, c in report["pages"].items()
                                      if c == 0]
    with open(os.path.join(work, "harvest_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("harvest -> %d bank entries (%s)" % (len(bank), report["by_kind"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
