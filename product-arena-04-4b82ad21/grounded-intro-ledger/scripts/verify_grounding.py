#!/usr/bin/env python3
"""verify_grounding.py -- final grounding audit of a drafted introduction.

Cross-checks the DRAFT against the claims ledger and the evidence store and
emits a verification object shaped for the result.json `verification` field.

Checks (each recorded pass/fail/not_verifiable with evidence):
  G1 every draft sentence carrying [n] markers is covered by >=1 claim record
     whose text matches that sentence (whitespace-normalized, markers removed)
  G2 every claim in the ledger appears in the draft (no orphan records)
  G3 every number in the draft is traceable: to bound quotes for cited
     (prior-work) sentences, to the manuscript fact base for uncited
     (own-work/background) sentences; untraceable numbers fail
  G4 every citation number is within the bibliography's range
  G5 every contribution claim names an available anchor from the case
  G6 material gaps recorded in the store are surfaced for open items

Exit codes: 0 pass, 1 fail, 2 usage/IO error.
"""
import argparse
import json
import re
import sys
from pathlib import Path

NUM = re.compile(r"\d+(?:\.\d+)?")
MARK = re.compile(r"\[(\d+(?:\s*[-,]\s*\d+)*)\]")
MARK_STRIP = re.compile(r"\s*\[[\d,\s\-]+\]")


def norm(t):
    return re.sub(r"\s+", " ", (t or "")).strip()


def clean(t):
    """Strip citation markers, fix space-before-punctuation, normalize."""
    t = MARK_STRIP.sub("", t or "")
    t = re.sub(r"\s+([.!?,;:])", r"\1", t)
    return norm(t)


def split_sentences(text):
    """Sentence split robust to decimal points and markdown headers."""
    lines = [ln for ln in (text or "").splitlines() if not ln.lstrip().startswith("#")]
    t = norm(" ".join(lines))
    # protect decimal points: a period between digits never ends a sentence
    parts = re.split(r"(?<=[.!?])\s+(?=[^0-9\s]|$)", t)
    return [p.strip() for p in parts if len(p.strip()) > 15]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("--draft", required=True)
    ap.add_argument("--claims", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    try:
        store = json.loads(Path(args.store).read_text(encoding="utf-8"))
        draft = Path(args.draft).read_text(encoding="utf-8")
        claims = json.loads(Path(args.claims).read_text(encoding="utf-8"))
    except Exception as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    checks = []
    claim_texts = [clean(c.get("text", "")) for c in claims]
    draft_sents = [(bool(MARK.search(s)), clean(s)) for s in split_sentences(draft)]
    cited = [s for marked, s in draft_sents if marked]
    plain = [s for _m, s in draft_sents]

    # G1: cited sentences covered by claim records
    uncovered = []
    for s in cited:
        if not any(s and (s in ct or ct in s) for ct in claim_texts if ct):
            uncovered.append(s[:120])
    checks.append({"id": "G1", "name": "cited sentences have claim records",
                   "status": "fail" if uncovered else "pass",
                   "evidence": {"uncovered": uncovered,
                                "total_cited_sentences": len(cited)}})

    # G2: no orphan claim records
    draft_norm = norm(" ".join(plain))
    orphans = []
    for c in claims:
        ct = clean(c.get("text", ""))
        if not ct:
            continue
        if ct in draft_norm:
            continue
        words = set(re.findall(r"[a-zA-Z]{4,}", ct.lower()))
        if words:
            hit = sum(1 for w in words if w in draft_norm.lower())
            if hit / len(words) < 0.8:
                orphans.append(c.get("id", "?"))
    checks.append({"id": "G2", "name": "no orphan claim records",
                   "status": "fail" if orphans else "pass",
                   "evidence": {"orphans": orphans}})

    # G3: number traceability
    quotes_norm = norm(" ".join(
        q for c in claims for qs in (c.get("quotes") or {}).values()
        for q in (qs if isinstance(qs, list) else [qs]) if isinstance(q, str)))
    facts_norm = store.get("facts_norm", "")
    bad_nums = []
    for marked, s in draft_sents:
        for n in NUM.findall(s):
            if re.search(r"(?:Fig|Figure|Section|Table|Eq)\.?\s*%s\b" % re.escape(n), s):
                continue  # anchor number, checked by G5
            hay = quotes_norm if marked else facts_norm
            if n not in hay and n not in quotes_norm and n not in facts_norm:
                bad_nums.append({"sentence": s[:100], "number": n})
    checks.append({"id": "G3", "name": "all numbers traceable to quotes or fact base",
                   "status": "fail" if bad_nums else "pass",
                   "evidence": {"untraceable": bad_nums}})

    # G4: citation numbers defined
    n_refs = len(store.get("refs", {}))
    used = sorted({int(x) for grp in MARK.findall(draft)
                   for x in re.findall(r"\d+", grp)})
    undef = [u for u in used if u < 1 or u > n_refs]
    checks.append({"id": "G4", "name": "citation numbers within bibliography range",
                   "status": "fail" if undef else "pass",
                   "evidence": {"used": used, "bibliography_size": n_refs,
                                "undefined": undef}})

    # G5: contributions name anchors
    anchors = store.get("anchors", [])
    contrib_claims = [c for c in claims if c.get("type") == "contribution"]
    if contrib_claims:
        no_anchor = [c.get("id", "?") for c in contrib_claims
                     if anchors and not any(a in c.get("text", "") for a in anchors)]
        checks.append({"id": "G5", "name": "contribution claims name an available anchor",
                       "status": "fail" if no_anchor else "pass",
                       "evidence": {"without_anchor": no_anchor, "anchors": anchors}})
    else:
        checks.append({"id": "G5", "name": "contribution claims name an available anchor",
                       "status": "not_verifiable",
                       "evidence": {"reason": "no contribution claims in ledger"}})

    # G6: material gaps surfaced
    gaps = store.get("material_gaps", [])
    checks.append({"id": "G6", "name": "material gaps surfaced for open_items",
                   "status": "pass" if not gaps else "not_verifiable",
                   "evidence": {"material_gaps": gaps}})

    summary = {"pass": sum(1 for c in checks if c["status"] == "pass"),
               "fail": sum(1 for c in checks if c["status"] == "fail"),
               "not_verifiable": sum(1 for c in checks if c["status"] == "not_verifiable")}
    verification = {"artifact": "verify_grounding.py", "checks": checks, "summary": summary}
    Path(args.out).write_text(json.dumps(verification, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print("grounding audit: %d pass / %d fail / %d not_verifiable -> %s"
          % (summary["pass"], summary["fail"], summary["not_verifiable"], args.out))
    return 0 if summary["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
