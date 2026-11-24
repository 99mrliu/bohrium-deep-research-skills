#!/usr/bin/env python3
"""citation_scan.py -- claim-citation-aligner stage 1: mechanical reconciliation.

Maps every in-text citation mark to reference entries and reports:
  - citing_sentences: [{sentence_id, page, sentence, mark, ref_ids}]
  - unresolved_marks: marks pointing at non-existent entries
  - uncited_refs:     entries never cited in the body

--strict: exit 1 when unresolved_marks or uncited_refs are non-empty.
Always writes the full JSON report.
"""
import argparse
import json
import re
import sys

REF_HEAD = re.compile(
    r"^\s*(references|bibliography|works\s+cited|参考文献)\s*:?\s*$",
    re.IGNORECASE)
NUM_ENTRY = re.compile(r"^\s*(?:\[(\d{1,3})\]|(\d{1,3})[.\)])\s+(.*)$")
NUM_MARK = re.compile(r"\[(\d{1,3}(?:\s*[-–,]\s*\d{1,3})*)\]")
AY_MARK = re.compile(
    r"\(([A-Z][A-Za-zÀ-ÿ'\-]+(?:\s+et\s+al\.?|(?:\s+and\s+|\s*&\s*)"
    r"[A-Z][A-Za-zÀ-ÿ'\-]+)?),?\s+((?:19|20)\d{2})[a-z]?\)")


def expand_mark(body: str):
    ids = []
    for part in re.split(r"\s*,\s*", body):
        m = re.match(r"^(\d{1,3})\s*[-–]\s*(\d{1,3})$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            ids.extend(range(min(a, b), max(a, b) + 1))
        elif part.strip().isdigit():
            ids.append(int(part.strip()))
    return ids


def split_sentences(text: str):
    # crude sentence splitter tolerant of abbreviations and reference noise
    text = re.sub(r"\s+", " ", text)
    pieces = re.split(r"(?<=[.!?。！？])\s+(?=[A-Z0-9\"“(\[])", text)
    return [p.strip() for p in pieces if p.strip()]


def parse_refs(lines):
    entries, cur = [], None
    for ln in lines:
        m = NUM_ENTRY.match(ln)
        if m:
            if cur:
                entries.append(cur)
            cur = {"ref_id": int(m.group(1) or m.group(2)), "raw": m.group(3)}
        elif cur is not None and ln.strip() and not REF_HEAD.match(ln):
            cur["raw"] += " " + ln.strip()
    if cur:
        entries.append(cur)
    for e in entries:
        e["raw"] = re.sub(r"\s+", " ", e["raw"]).strip()
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    pages = [json.loads(l) for l in open(args.pages, encoding="utf-8")
             if l.strip()]

    ref_page = None
    for pg in pages:
        if any(REF_HEAD.match(ln) for ln in pg["text"].splitlines()):
            ref_page = pg["page"]
            break

    references = []
    if ref_page is not None:
        lines = []
        for pg in pages:
            if pg["page"] < ref_page:
                continue
            for ln in pg["text"].splitlines():
                if REF_HEAD.match(ln):
                    continue
                lines.append(ln)
        references = parse_refs(lines)
    n_refs = len(references)
    first_author_by_id = {}
    for e in references:
        m = re.match(r"([A-Z][A-Za-zÀ-ÿ'\-]+)", e["raw"])
        if m:
            first_author_by_id[e["ref_id"]] = (m.group(1), e["raw"])

    citing, unresolved = [], []
    cited_ids = set()
    for pg in pages:
        if ref_page is not None and pg["page"] > ref_page:
            continue
        body_text = pg["text"]
        if ref_page is not None and pg["page"] == ref_page:
            # keep only the part of the reference page above the header
            kept = []
            for ln in pg["text"].splitlines():
                if REF_HEAD.match(ln):
                    break
                kept.append(ln)
            body_text = "\n".join(kept)
        for si, sent in enumerate(split_sentences(body_text), 1):
            marks = list(NUM_MARK.finditer(sent))
            ay = list(AY_MARK.finditer(sent))
            if not marks and not ay:
                continue
            sid = f"p{pg['page']}.S{si}"
            for mk in marks:
                ids = expand_mark(mk.group(1))
                bad = [i for i in ids if n_refs and (i < 1 or i > n_refs)]
                if bad:
                    unresolved.append({"sentence_id": sid,
                                       "mark": mk.group(0), "ref_ids": bad,
                                       "page": pg["page"]})
                cited_ids.update(i for i in ids if i not in bad)
                citing.append({"sentence_id": sid, "page": pg["page"],
                               "sentence": sent, "mark": mk.group(0),
                               "ref_ids": ids, "style": "numbered"})
            for mk in ay:
                key = mk.group(1).split()[0]
                hits = [rid for rid, (fa, raw) in first_author_by_id.items()
                        if fa.lower() == key.lower()
                        and str(mk.group(2)) in raw]
                cited_ids.update(hits)
                if not hits:
                    unresolved.append({"sentence_id": sid,
                                       "mark": mk.group(0),
                                       "author_year": mk.group(0),
                                       "page": pg["page"]})
                citing.append({"sentence_id": sid, "page": pg["page"],
                               "sentence": sent, "mark": mk.group(0),
                               "ref_ids": hits, "style": "author-year"})

    uncited = [e["ref_id"] for e in references
               if e["ref_id"] not in cited_ids]
    report = {
        "reference_section_page": ref_page,
        "n_references": n_refs,
        "references": [{"ref_id": e["ref_id"],
                        "raw_head": e["raw"][:160]} for e in references],
        "citing_sentences": citing,
        "unresolved_marks": unresolved,
        "uncited_refs": uncited,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"citing_sentences": len(citing),
                      "references": n_refs,
                      "unresolved_marks": len(unresolved),
                      "uncited_refs": len(uncited)}, ensure_ascii=False))
    if args.strict and (unresolved or uncited):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
