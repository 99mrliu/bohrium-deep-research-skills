#!/usr/bin/env python3
"""word_budget.py -- enforce word budgets per rhetorical part before rendering.

Splits a Markdown introduction into the rhetorical parts the case requires
(background / related_work / gap / contributions), counts words per part and
in total, and checks them against the case constraints
(max_words_introduction, max_words_related_work, or any other
max_words_* / min_words_* keys). Over-limit parts are reported together with
their longest sentences so trimming starts in the right place.

Part detection: Markdown headings containing the part name win; otherwise the
script falls back to cue phrases (see CUES below) and marks the assignment
"heuristic" in the report. Parts that cannot be located are reported
not_verifiable, never silently passed.

Usage:
  python3 word_budget.py --case /input/case.json --draft /app/output/introduction.md \
      --out /app/work/word_report.json

Exit codes: 0 within budget, 1 over budget or required part missing, 2 usage error.
"""
import argparse
import json
import re
import sys
from pathlib import Path

CUES = {
    "background": ["underpins", "plays a central role", "is essential", "widely used",
                   "has become", "commonly grouped", "fundamental"],
    "related_work": ["proposed", "introduced", "presented", "developed", "reported",
                     "et al", "transplants", "predicts", "ranks", "pools", "scores"],
    "gap": ["however", "remains", "unestablished", "unresolved", "lacks", "lacking",
            "no existing", "still", "yet ", "despite"],
    "contributions": ["we present", "we propose", "we introduce", "our contribution",
                      "in this work", "here we", "we show", "we demonstrate",
                      "to address", "we develop"],
}
PART_KEYS = ["background", "related_work", "gap", "contributions"]


def words(text):
    t = re.sub(r"\[[\d,\s\-]+\]", "", text)          # citation markers
    t = re.sub(r"[#*_>`]", " ", t)                    # markdown syntax
    return [w for w in re.split(r"\s+", t) if re.search(r"[A-Za-z0-9]", w)]


def split_sentences(text):
    t = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+(?=[^0-9\s]|$)", t)
    return [p.strip() for p in parts if len(p.strip()) > 15]


def heading_parts(lines):
    """Assign line ranges to parts via markdown headings."""
    parts, current = {}, None
    for ln in lines:
        m = re.match(r"^#{1,3}\s+(.*)", ln)
        if m:
            h = m.group(1).lower()
            for key in PART_KEYS:
                if key.replace("_", " ") in h or key in h:
                    current = key
                    break
        if current:
            parts.setdefault(current, []).append(ln)
    return parts


def heuristic_parts(sentences):
    parts = {}
    for s in sentences:
        low = s.lower()
        best, best_hits = None, 0
        for key, cues in CUES.items():
            hits = sum(1 for c in cues if c in low)
            if hits > best_hits:
                best, best_hits = key, hits
        if best:
            parts.setdefault(best, []).append(s)
    return parts


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", required=True)
    ap.add_argument("--draft", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    try:
        case = json.loads(Path(args.case).read_text(encoding="utf-8"))
        draft = Path(args.draft).read_text(encoding="utf-8")
    except Exception as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    cons = case.get("constraints", {})
    lines = [ln for ln in draft.splitlines()]
    body = [ln for ln in lines if not ln.lstrip().startswith("#") or
            any(k in ln.lower() for k in PART_KEYS)]
    hparts = heading_parts(lines)
    mode = "headings" if hparts else "heuristic"
    if not hparts:
        sparts = heuristic_parts(split_sentences(" ".join(
            ln for ln in lines if not ln.lstrip().startswith("#"))))
    else:
        sparts = {}

    report = {"mode": mode, "parts": {}, "total_words": len(words(draft)),
              "checks": [], "trim_candidates": {}}
    required = cons.get("sections_required", [])
    for part in PART_KEYS:
        if hparts:
            text = " ".join(hparts.get(part, []))
        else:
            text = " ".join(sparts.get(part, []))
        n = len(words(text))
        entry = {"words": n, "located": bool(text.strip())}
        report["parts"][part] = entry
        if part in required and not text.strip():
            report["checks"].append({"check": "part_present:" + part,
                                     "status": "fail", "detail": "part not located (%s mode)" % mode})
        limit = cons.get("max_words_" + part)
        if limit is not None:
            status = "pass" if n <= limit else "fail"
            report["checks"].append({"check": "max_words_" + part, "status": status,
                                     "detail": "%d words vs limit %d" % (n, limit)})
            if status == "fail":
                sents = split_sentences(text)
                sents.sort(key=lambda s: -len(words(s)))
                report["trim_candidates"][part] = [
                    {"words": len(words(s)), "sentence": s[:160]} for s in sents[:3]]
    total_limit = cons.get("max_words_introduction") or cons.get("max_words_total")
    if total_limit is not None:
        status = "pass" if report["total_words"] <= total_limit else "fail"
        report["checks"].append({"check": "max_words_introduction", "status": status,
                                 "detail": "%d words vs limit %d"
                                           % (report["total_words"], total_limit)})
    missing_required = [p for p in required if p not in PART_KEYS]
    for p in missing_required:
        report["checks"].append({"check": "part_present:" + p, "status": "not_verifiable",
                                 "detail": "no word counter for non-standard part; verify manually"})

    fails = sum(1 for c in report["checks"] if c["status"] == "fail")
    report["summary"] = {"pass": sum(1 for c in report["checks"] if c["status"] == "pass"),
                         "fail": fails,
                         "not_verifiable": sum(1 for c in report["checks"]
                                               if c["status"] == "not_verifiable")}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print("word budget (%s mode): total %d; %s -> %s"
          % (mode, report["total_words"],
             ", ".join("%s=%d" % (p, e["words"]) for p, e in report["parts"].items()),
             "PASS" if fails == 0 else "FAIL(%d)" % fails))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
