#!/usr/bin/env python3
"""bind_claims.py -- bind every claim about prior work to verbatim source quotes.

Two modes:

  --scaffold   read a draft and emit a claims skeleton to fill in
  (default)    verify a filled claims.json against the evidence store

Claim shape (matches the usual facts_and_sources contract item):
  {"id": "c1", "section": "related_work", "text": "<exact draft sentence>",
   "type": "prior_work|own_work|background|gap|contribution",
   "refs": ["synth01"], "quotes": {"synth01": "<verbatim quote>"},
   "source_span": "<where in the source, e.g. abstract sentence 2>",
   "stance": "supports|contrasts|scopes|notes_limitation|identifies",
   "confidence": "high|medium|low"}
For a single-ref claim a plain "quote" string is accepted instead of "quotes".

Verification rules (all mechanical; they do not prove semantic entailment):
  R1 every ref key exists in the store
  R2 a claim attributing findings (type prior_work/background/gap) may not
     cite a title-only or metadata-only reference
  R3 every quote is a verbatim whitespace-normalized substring of that
     reference's available text
  R4 every number appearing in the claim text appears in the union of the
     claim's quotes (prior-work claims) or in the manuscript facts
     (own-work claims)
  R5 own-work claims carry no refs and must name an available anchor
     (e.g. "Fig 1") in their text
  R6 stance and confidence use the allowed vocabularies

Exit codes: 0 pass, 1 one or more hard failures, 2 usage/IO error.
"""
import argparse
import json
import re
import sys
from pathlib import Path

STANCES = {"supports", "contrasts", "scopes", "notes_limitation", "identifies"}
CONFIDENCE = {"high", "medium", "low"}
PRIOR_TYPES = {"prior_work", "background", "gap"}
NUM = re.compile(r"\d+(?:\.\d+)?")


def norm(t):
    return re.sub(r"\s+", " ", (t or "")).strip()


def split_sentences(text):
    text = re.sub(r"\[[\d,\s\-]+\]", "", text)
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if len(p.strip()) > 20]


def quotes_of(claim):
    """Return {ref_key: [quote, ...]}; quote values may be str or list of str."""
    q = claim.get("quotes")
    raw = {}
    if isinstance(q, dict):
        raw = q
    elif isinstance(q, str) and claim.get("refs"):
        raw = {claim["refs"][0]: q}
    elif isinstance(claim.get("quote"), str) and claim.get("refs"):
        raw = {claim["refs"][0]: claim["quote"]}
    out = {}
    for k, v in raw.items():
        if isinstance(v, str):
            out[k] = [v]
        elif isinstance(v, list):
            out[k] = [x for x in v if isinstance(x, str)]
    return out


def verify(store, claims):
    refs = store["refs"]
    anchors = store.get("anchors", [])
    facts_norm = store.get("facts_norm", "")
    report = {"claims_checked": len(claims), "failures": [], "warnings": []}
    for c in claims:
        cid = c.get("id", "?")
        ctype = c.get("type", "prior_work")
        text = norm(c.get("text", ""))
        qmap = quotes_of(c)
        for rk in c.get("refs", []):
            if rk not in refs:
                report["failures"].append(
                    {"claim": cid, "rule": "R1", "detail": "unknown ref key %s" % rk})
                continue
            level = refs[rk]["evidence_level"]
            if ctype in PRIOR_TYPES and level != "abstract":
                report["failures"].append(
                    {"claim": cid, "rule": "R2",
                     "detail": "findings attributed to %s-level ref %s" % (level, rk)})
            qs = qmap.get(rk, [])
            if not qs:
                report["failures"].append(
                    {"claim": cid, "rule": "R3", "detail": "no quote bound for ref %s" % rk})
            else:
                for quote in qs:
                    if norm(quote) not in refs[rk]["norm_text"]:
                        report["failures"].append(
                            {"claim": cid, "rule": "R3",
                             "detail": "quote for %s is not verbatim source text: %s"
                                       % (rk, quote[:80])})
        nums = NUM.findall(text)
        if ctype in PRIOR_TYPES and c.get("refs"):
            hay = norm(" ".join(q for qs in qmap.values() for q in qs))
            for n in nums:
                if n not in hay:
                    report["failures"].append(
                        {"claim": cid, "rule": "R4",
                         "detail": "number %s not traceable to bound quotes" % n})
        if ctype in ("own_work", "contribution"):
            if c.get("refs"):
                report["warnings"].append(
                    {"claim": cid, "rule": "R5",
                     "detail": "own-work claim cites refs; own facts come from the fact base"})
            for n in nums:
                if n not in facts_norm:
                    report["failures"].append(
                        {"claim": cid, "rule": "R4",
                         "detail": "own-work number %s absent from manuscript facts" % n})
            if ctype == "contribution" and anchors and not any(a in text for a in anchors):
                report["failures"].append(
                    {"claim": cid, "rule": "R5",
                     "detail": "contribution claim names no available anchor %s" % anchors})
        if c.get("stance") and c["stance"] not in STANCES:
            report["failures"].append(
                {"claim": cid, "rule": "R6", "detail": "bad stance %s" % c["stance"]})
        if c.get("confidence") and c["confidence"] not in CONFIDENCE:
            report["failures"].append(
                {"claim": cid, "rule": "R6", "detail": "bad confidence %s" % c["confidence"]})
        for rk in qmap:
            if rk not in (c.get("refs") or []):
                report["warnings"].append(
                    {"claim": cid, "rule": "R3", "detail": "quote bound to uncited ref %s" % rk})
    report["status"] = "pass" if not report["failures"] else "fail"
    return report


def scaffold(draft_path, store):
    text = Path(draft_path).read_text(encoding="utf-8")
    claims = []
    n = 0
    for m in re.finditer(r"[^.!?]*\[\d+(?:\s*[-,]\s*\d+)*\][^.!?]*[.!?]", text):
        n += 1
        claims.append({
            "id": "c%d" % n, "section": "related_work",
            "text": norm(m.group(0)), "type": "prior_work",
            "refs": ["<ref-key-from-evidence-store>"],
            "quotes": {"<ref-key-from-evidence-store>": "<verbatim quote>"},
            "source_span": "<e.g. abstract sentence 2>",
            "stance": "supports", "confidence": "high"})
    return claims


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True, help="evidence_store.json")
    ap.add_argument("--claims", help="filled claims.json to verify")
    ap.add_argument("--scaffold", metavar="DRAFT.md",
                    help="emit a claims skeleton for sentences with [n] markers")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    try:
        store = json.loads(Path(args.store).read_text(encoding="utf-8"))
    except Exception as exc:
        print("error: cannot read store: %s" % exc, file=sys.stderr)
        return 2
    if args.scaffold:
        claims = scaffold(args.scaffold, store)
        Path(args.out).write_text(json.dumps(claims, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print("scaffold: %d claim skeletons -> %s (fill refs and verbatim quotes)"
              % (len(claims), args.out))
        return 0
    if not args.claims:
        print("error: --claims required unless --scaffold", file=sys.stderr)
        return 2
    try:
        claims = json.loads(Path(args.claims).read_text(encoding="utf-8"))
    except Exception as exc:
        print("error: cannot read claims: %s" % exc, file=sys.stderr)
        return 2
    report = verify(store, claims)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print("bindings: %d claims, %d failures, %d warnings -> %s"
          % (report["claims_checked"], len(report["failures"]),
             len(report["warnings"]), report["status"]))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
