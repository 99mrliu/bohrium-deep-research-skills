#!/usr/bin/env python3
"""extract_refs.py -- source-truth-gate stage 1a: pages.jsonl -> refs.json

Locates the reference section, parses numbered ([1] / 1.) and author-year
entries, extracts DOI (with syntax validation), year, first-author surname
and a title guess. Unparseable entries are kept with parse_ok=false, never
dropped. Also emits the in-text citation-mark index (mark -> page) so later
stages can cross-check reference usage.
"""
import argparse
import json
import re
import sys

REF_HEAD_RE = re.compile(
    r"^\s*(references|bibliography|works\s+cited|参考文献|文献)\s*:?\s*$",
    re.IGNORECASE)
NUM_ENTRY_RE = re.compile(r"^\s*(?:\[(\d{1,3})\]|(\d{1,3})[.\)])\s+(.*)$")
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)")
# loose fallback: an explicit "doi:" marker followed by anything non-space;
# used to detect malformed DOI strings (kept, flagged doi_syntax_ok=false)
DOI_LOOSE_RE = re.compile(r"(?i)\bdoi[: ]?\s*(10\.\S+)")
YEAR_RE = re.compile(r"\b((?:19|20)\d{2})[a-z]?\b")
INTEXT_NUM_RE = re.compile(r"\[(\d{1,3}(?:\s*[-,]\s*\d{1,3})*)\]")
INTEXT_AY_RE = re.compile(
    r"\(([A-Z][A-Za-zÀ-ÿ'\-]+(?:\s+et\s+al\.?|(?:\s+and\s+|\s*&\s*)"
    r"[A-Z][A-Za-zÀ-ÿ'\-]+)?),?\s+((?:19|20)\d{2})[a-z]?\)")


def normalize_doi(doi: str) -> str:
    d = doi.strip().rstrip(".,;)]").strip()
    for p in ("https://doi.org/", "http://doi.org/", "doi:", "DOI:"):
        if d.lower().startswith(p.lower()):
            d = d[len(p):]
    return d


def doi_syntax_ok(doi: str) -> bool:
    return bool(re.fullmatch(r"10\.\d{4,9}/\S+", doi)) and " " not in doi


def guess_author_year(text: str):
    m = re.match(r"\s*(?:\[\d+\]|\d+[.\)])?\s*([A-Z][A-Za-zÀ-ÿ'\-]+)", text)
    author = m.group(1) if m else None
    # remove the DOI tail before year extraction: DOIs often embed years
    body = re.split(r"(?i)\bdoi[: ]", text)[0]
    years = YEAR_RE.findall(body)
    year = int(years[-1]) if years else None
    return author, year


def guess_title(text: str):
    # heuristic: longest quoted or sentence-like segment between author block
    # and journal/year tail
    m = re.search(r'["“](.+?)["”]', text)
    if m:
        return m.group(1).strip()
    parts = re.split(r"\.\s+", text)
    cands = [p for p in parts if 20 <= len(p) <= 300
             and not YEAR_RE.search(p) and "doi" not in p.lower()]
    return max(cands, key=len).strip() if cands else None


def parse_reference_block(lines):
    entries = []
    cur = None
    for ln in lines:
        m = NUM_ENTRY_RE.match(ln)
        if m:
            if cur:
                entries.append(cur)
            cur = {"num": int(m.group(1) or m.group(2)), "raw": m.group(3)}
        elif cur is not None and ln.strip() and not REF_HEAD_RE.match(ln):
            cur["raw"] += " " + ln.strip()
        elif cur is not None and not ln.strip():
            entries.append(cur)
            cur = None
    if cur:
        entries.append(cur)
    if not entries:
        # author-year style: one entry per non-empty line
        entries = [{"num": i + 1, "raw": ln.strip()}
                   for i, ln in enumerate(lines) if ln.strip()]
    out = []
    for e in entries:
        raw = re.sub(r"\s+", " ", e["raw"]).strip()
        doi_m = DOI_RE.search(raw)
        if doi_m:
            doi = normalize_doi(doi_m.group(1))
        else:
            loose = DOI_LOOSE_RE.search(raw)
            doi = normalize_doi(loose.group(1)) if loose else None
        author, year = guess_author_year(raw)
        out.append({
            "ref_id": e["num"],
            "raw": raw,
            "parse_ok": bool(author or doi),
            "first_author": author,
            "year": year,
            "title_guess": guess_title(raw),
            "doi": doi,
            "doi_syntax_ok": doi_syntax_ok(doi) if doi else None,
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    pages = []
    with open(args.pages, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                pages.append(json.loads(line))

    ref_start = None
    for pi, pg in enumerate(pages):
        for ln in pg["text"].splitlines():
            if REF_HEAD_RE.match(ln):
                ref_start = (pi, ln)
                break
        if ref_start:
            break

    result = {"reference_section_found": ref_start is not None,
              "entries": [], "intext_marks": [], "warnings": []}

    if ref_start:
        pi = ref_start[0]
        ref_lines = []
        for pg in pages[pi:]:
            for ln in pg["text"].splitlines():
                if REF_HEAD_RE.match(ln):
                    continue
                ref_lines.append(ln)
        result["entries"] = parse_reference_block(ref_lines)
    else:
        result["warnings"].append(
            "reference section not located; citation inventory must be "
            "rebuilt from in-text marks only")

    for pg in pages:
        for m in INTEXT_NUM_RE.finditer(pg["text"]):
            result["intext_marks"].append(
                {"kind": "numbered", "mark": m.group(0), "page": pg["page"]})
        for m in INTEXT_AY_RE.finditer(pg["text"]):
            result["intext_marks"].append(
                {"kind": "author-year",
                 "mark": f"{m.group(1)} {m.group(2)}", "page": pg["page"]})

    n_bad_doi = sum(1 for e in result["entries"]
                    if e["doi"] and not e["doi_syntax_ok"])
    if n_bad_doi:
        result["warnings"].append(f"{n_bad_doi} entries have malformed DOI")
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"entries": len(result["entries"]),
                      "intext_marks": len(result["intext_marks"]),
                      "reference_section_found":
                          result["reference_section_found"]},
                     ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
