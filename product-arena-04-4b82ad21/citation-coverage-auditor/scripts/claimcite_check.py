#!/usr/bin/env python3
"""claimcite_check.py - verify claim-to-citation correspondence.

Part of the citation-coverage-auditor skill. Pure Python 3 stdlib.

claims.json is an array of claim objects in the facts_and_sources shape:
  {"id": ..., "section": ..., "text": ..., "type": ..., "refs": [...], ...}

Verifies:
  1. every claim about prior work (section == "related_work", or a type/section
     string indicating prior work) lists >= 1 ref;
  2. every ref key used in claims exists in bib.json AND is actually cited in
     the draft (its Vancouver number appears in some [n] marker);
  3. every [n] marker in the draft sits in a sentence whose text appears
     (whitespace-normalized substring, truncation tolerated in either
     direction) in some claim object that lists the ref behind [n]
     -> no citation without a claim record;
  4. every prior-work claim text appears in the (marker-stripped) draft
     -> no claim record disconnected from the draft.

Orphans are reported in both directions. Exit 1 on hard failures,
0 when clean, 2 on usage error.
"""
import argparse
import json
import re
import sys
from pathlib import Path

MARKER_RE = re.compile(r"\[(\d+(?:\s*[,\-]\s*\d+)*)\]")
SENT_END_RE = re.compile(r"[.!?](?=\s+[A-Z(]|$)")
PRIOR_WORK_TYPES = {"prior_work", "prior-work", "related_work", "related-work",
                    "literature", "background_literature"}


def norm_ws(s):
    return re.sub(r"\s+", " ", str(s)).strip()


def strip_markers(s):
    s = MARKER_RE.sub(" ", s)
    return re.sub(r"\s+([.,;:!?])", r"\1", s)  # heal "word [1]." -> "word."


def expand_marker(body):
    nums = []
    for part in body.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            nums.extend(range(int(a), int(b) + 1))
        else:
            nums.append(int(part))
    return nums


def sentence_spans(text):
    spans, start = [], 0
    for m in SENT_END_RE.finditer(text):
        spans.append((start, m.end()))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    return [(a, b, text[a:b]) for a, b in spans if text[a:b].strip()]


def is_prior_work_claim(claim):
    section = norm_ws(claim.get("section", "")).lower()
    ctype = norm_ws(claim.get("type", "")).lower()
    if section == "related_work" or ctype in PRIOR_WORK_TYPES:
        return True
    return "prior" in ctype or "prior" in section or "related" in ctype


def texts_match(a, b):
    """Whitespace-normalized substring in either direction (truncation tolerated)."""
    a, b = norm_ws(a), norm_ws(b)
    if not a or not b:
        return False
    return a in b or b in a


def main(argv=None):
    ap = argparse.ArgumentParser(description="Verify claim-to-citation correspondence.")
    ap.add_argument("--draft", required=True, help="manuscript draft markdown")
    ap.add_argument("--claims", required=True, help="claims.json (facts_and_sources shape)")
    ap.add_argument("--bib", required=True, help="bib.json produced by bib_parse.py")
    ap.add_argument("--out", required=True, help="report JSON path")
    args = ap.parse_args(argv)

    draft_path, claims_path, bib_path = Path(args.draft), Path(args.claims), Path(args.bib)
    for p, flag in ((draft_path, "--draft"), (claims_path, "--claims"), (bib_path, "--bib")):
        if not p.is_file():
            print("error: %s file not found: %s" % (flag, p), file=sys.stderr)
            return 2

    text = draft_path.read_text(encoding="utf-8")
    claims = json.loads(claims_path.read_text(encoding="utf-8"))
    bib = json.loads(bib_path.read_text(encoding="utf-8"))
    if not isinstance(claims, list):
        print("error: claims.json must be an array of claim objects", file=sys.stderr)
        return 2

    bib_keys = [e.get("key", "ref%02d" % (i + 1)) for i, e in enumerate(bib)]
    num_of_key = {k: i + 1 for i, k in enumerate(bib_keys)}
    key_of_num = {i + 1: k for i, k in enumerate(bib_keys)}

    markers = [(m.start(), "[" + m.group(1) + "]", expand_marker(m.group(1)))
               for m in MARKER_RE.finditer(text)]
    spans = sentence_spans(text)
    cited_numbers = {n for _, _, nums in markers for n in nums}
    cited_keys = {key_of_num[n] for n in cited_numbers if n in key_of_num}

    failures = []
    claim_issues = []
    marker_issues = []

    # --- direction 1: claims -> bib and draft -------------------------------
    for c in claims:
        cid = c.get("id", "?")
        refs = c.get("refs") or []
        prior = is_prior_work_claim(c)
        if prior and not refs:
            claim_issues.append({"id": cid, "issue": "prior_work_claim_without_refs",
                                 "text": norm_ws(c.get("text", ""))[:120]})
            failures.append("claim %s is about prior work but lists no refs" % cid)
        for r in refs:
            if r not in num_of_key:
                claim_issues.append({"id": cid, "issue": "ref_key_not_in_bibliography",
                                     "ref": r})
                failures.append("claim %s cites unknown ref key %r (not in bib.json)" % (cid, r))
            elif r not in cited_keys:
                claim_issues.append({"id": cid, "issue": "ref_not_cited_in_draft",
                                     "ref": r})
                failures.append("claim %s lists ref %s, but [%d] never appears in the draft"
                                % (cid, r, num_of_key[r]))
        if prior:
            draft_wo = norm_ws(strip_markers(text))
            ctext = norm_ws(c.get("text", ""))
            if ctext and ctext not in draft_wo and not any(
                    texts_match(s, ctext) for _, _, s in spans):
                claim_issues.append({"id": cid, "issue": "claim_text_not_found_in_draft",
                                     "text": ctext[:120]})
                failures.append("claim %s text is disconnected from the draft "
                                "(no matching sentence)" % cid)

    # --- direction 2: draft markers -> claims -------------------------------
    for off, marker, nums in markers:
        sent = next((s for a, b, s in spans if a <= off < b), "")
        sent_wo = norm_ws(strip_markers(sent))
        for n in nums:
            key = key_of_num.get(n)
            if key is None:
                marker_issues.append({"marker": marker, "offset": off, "number": n,
                                      "issue": "number_outside_bibliography"})
                failures.append("marker %s at offset %d has no bibliography entry"
                                % (marker, off))
                continue
            hit = None
            for c in claims:
                if key in (c.get("refs") or []) and texts_match(sent_wo, c.get("text", "")):
                    hit = c.get("id", "?")
                    break
            if hit is None:
                marker_issues.append({
                    "marker": marker, "offset": off, "number": n, "key": key,
                    "issue": "orphan_citation_no_claim_record",
                    "sentence": sent_wo[:160]})
                failures.append("orphan citation: %s (ref %s) has no claim record whose "
                                "text matches its sentence" % (marker, key))

    report = {
        "draft": str(draft_path),
        "claims": str(claims_path),
        "n_claims": len(claims),
        "n_prior_work_claims": sum(1 for c in claims if is_prior_work_claim(c)),
        "n_markers": len(markers),
        "claim_issues": claim_issues,
        "marker_issues": marker_issues,
        "failures": failures,
        "status": "pass" if not failures else "fail",
    }
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    print("claim-citation check: %s | claims %d (prior-work %d) | markers %d | failures %d"
          % (report["status"], len(claims), report["n_prior_work_claims"],
             len(markers), len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
