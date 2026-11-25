#!/usr/bin/env python3
"""refs_parse.py - parse a paper's reference list into structured records.

Supported styles (mixed lists allowed):
  numbered-bracket : [1] A. Author, B. Author. Title. Journal 12, 34-56 (2020).
  author-year      : Author, A. & Author, B. (2020). Title. Journal, 12(3), 34-56.
                     https://doi.org/10.xxxx/...

Fields that cannot be extracted stay null; the entry's parse_status becomes
'partial' (some core fields) or 'raw' (nothing reliable).  Raw entries keep
the original string verbatim - fields are NEVER invented.

Input : --pages  per-page text file ('=== page N ===' markers)
        --headings  optional headings.json from heading_tree.py (used to
                    locate the References section; otherwise a trailing
                    numbered-list fallback is used)
Output: <out>/references.json

Exit codes: 0 ok, 2 usage/IO error, 3 reference section not found.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_pages, iter_lines, write_json, load_json

# ---------------------------------------------------------------- regexes --
BRACKET_START = re.compile(r"^\[\s*(\d+)\s*\]")
# initials-first author  "A. Turing"   / surname-first author  "Hopper, G."
AU_IF = r"(?:[A-Z]\.?\s*)+[A-Z][A-Za-z\-']+"
AU_SF = r"[A-Z][A-Za-z\-']+(?:\s+[A-Z][a-z][A-Za-z\-']+)*,\s*(?:[A-Z]\.?\s*)+"
AU = rf"(?:{AU_IF}|{AU_SF})"
AUTHORS_RE = re.compile(
    rf"^({AU}(?:\s*,\s*{AU})*(?:\s*,?\s*(?:and|&)\s*{AU})?)\s*\.\s+(.+)$", re.S)
AUTHOR_START = re.compile(rf"^{AU_SF}")
YEAR_PAREN = re.compile(r"\(((?:19|20)\d{2})[a-z]?\)")
YEAR_ANY = re.compile(r"\b((?:19|20)\d{2})\b")
DOI_RE = re.compile(r"(?:https?://(?:dx\.)?doi\.org/)?\b(10\.\d{4,9}/[^\s\"<>]+)",
                    re.IGNORECASE)
# "Journal of X 12, 34-56 (2020)."  (bracket style tail)
TAIL_BRACKET = re.compile(
    r"^(?P<venue>.*?)\s+(?P<volume>\d+)\s*,\s*"
    r"(?P<pages>\d[\d\s]*[-–—][\d\s]+)?\((?P<year>(?:19|20)\d{2})\)\.?\s*$")
# "Addison-Wesley (1968)."  (bracket style tail, no volume/pages)
TAIL_BRACKET_PLAIN = re.compile(
    r"^(?P<venue>.*?)\s*\((?P<year>(?:19|20)\d{2})\)\.?\s*$")
# "Journal, 12(3), 34-56."  (author-year style tail)
TAIL_AY = re.compile(
    r"^(?P<venue>.*?)[\s,]+(?P<volume>\d+)(?:\((?P<issue>\d+)\))?"
    r"(?:\s*,\s*(?P<pages>\d+\s*[-–—]\s*\d+))?\.?\s*$")
REFS_TITLES = {"references", "bibliography", "reference list",
               "literature cited", "works cited"}


# ------------------------------------------------------------- splitting --
def looks_complete(text):
    return bool(re.search(r"[.)\d]$", text) or re.search(r"doi\.org/\S+$", text))


def split_entries(region):
    """Split region lines [(page, line, text)] into reference entries."""
    entries = []           # list of {"page": int, "parts": [str]}
    cur = None

    def flush():
        nonlocal cur
        if cur and any(p.strip() for p in cur["parts"]):
            entries.append(cur)
        cur = None

    for page, _lineno, line in region:
        s = line.strip()
        if not s:
            continue
        joined = " ".join(cur["parts"]) if cur else ""
        if BRACKET_START.match(s):
            flush()
            cur = {"page": page, "parts": [s]}
        elif (cur and AUTHOR_START.match(s) and YEAR_PAREN.search(s)
              and looks_complete(joined)):
            flush()
            cur = {"page": page, "parts": [s]}
        elif (cur and not s[0].isalnum() and s[0] != "["
              and looks_complete(joined)):
            # odd starter (corrupted entry) after a complete-looking entry
            flush()
            cur = {"page": page, "parts": [s]}
        else:
            if cur is None:
                cur = {"page": page, "parts": [s]}
            else:
                cur["parts"].append(s)
    flush()
    return entries


# -------------------------------------------------------------- parsing ---
def split_authors(author_str):
    authors = [m.group(0).strip() for m in re.finditer(AU, author_str)]
    # regex backtracking may drop the period of a trailing initial
    return [a + "." if ("," in a and re.search(r"\s[A-Z]$", a)) else a
            for a in authors]


def clean_pages(raw):
    return re.sub(r"\s+", "", raw) if raw else None


def parse_entry(text):
    rec = {"raw": text, "label": None, "authors": [], "year": None,
           "title": None, "venue": None, "volume": None, "issue": None,
           "pages": None, "doi": None,
           "parse_status": "raw", "confidence": 0.0, "reasons": []}
    body = text.strip()
    style = "author-year"
    m = BRACKET_START.match(body)
    if m:
        rec["label"] = int(m.group(1))
        body = body[m.end():].strip()
        style = "bracket"
    rec["style"] = style

    md = DOI_RE.search(body)
    if md:
        rec["doi"] = md.group(1).rstrip(".,;)")
        body = (body[:md.start()] + " " + body[md.end():]).strip()
        rec["reasons"].append("doi found")

    rest = body
    ma = AUTHORS_RE.match(body)
    if ma:
        rec["authors"] = split_authors(ma.group(1))
        rest = ma.group(2).strip()
        rec["reasons"].append("authors recognized (%d)" % len(rec["authors"]))
    else:
        rec["reasons"].append("author list not recognized")

    # author-year style: "(2020)." immediately follows the author list
    my = re.match(r"^\(((?:19|20)\d{2})[a-z]?\)\.?\s*", rest)
    if my:
        rec["year"] = int(my.group(1))
        rest = rest[my.end():].strip()
    else:
        my = YEAR_PAREN.search(rest) or YEAR_ANY.search(rest)
        if my:
            rec["year"] = int(my.group(1))
    if rec["year"] is None:
        rec["reasons"].append("no year found")

    mt = re.match(r"^(.+?)\.\s+(.+)$", rest, re.S)
    tail = rest
    if mt:
        rec["title"] = mt.group(1).strip(" .")
        tail = mt.group(2).strip()
    else:
        rec["reasons"].append("title/venue boundary not found")

    for rx in (TAIL_BRACKET, TAIL_AY, TAIL_BRACKET_PLAIN):
        tv = rx.match(tail)
        if tv:
            gd = tv.groupdict()
            venue = (gd.get("venue") or "").strip(" ,.;")
            if venue:
                rec["venue"] = venue
            if gd.get("volume"):
                rec["volume"] = gd["volume"]
            if gd.get("issue"):
                rec["issue"] = gd["issue"]
            if gd.get("pages"):
                rec["pages"] = clean_pages(gd["pages"])
            if rec["year"] is None and gd.get("year"):
                rec["year"] = int(gd["year"])
            break

    core = [bool(rec["authors"]), rec["year"] is not None, rec["title"] is not None]
    if all(core):
        rec["parse_status"] = "parsed"
    elif any(core) or rec["venue"]:
        rec["parse_status"] = "partial"
    else:
        rec["parse_status"] = "raw"
        rec["reasons"].append("kept verbatim; no fields invented")

    weights = {"authors": 0.20, "year": 0.15, "title": 0.25, "venue": 0.15,
               "volume": 0.10, "pages": 0.10, "doi": 0.05}
    conf = sum(w for k, w in weights.items() if rec[k])
    rec["confidence"] = round(conf, 2)
    missing = [k for k in ("authors", "year", "title", "venue") if not rec[k]]
    if missing:
        rec["reasons"].append("missing: " + ", ".join(missing))
    return rec


# -------------------------------------------------------------- locating --
def find_region_with_headings(stream, headings_flat):
    refs = [h for h in headings_flat
            if h["title"].strip().rstrip(":").lower() in REFS_TITLES]
    if not refs:
        return None
    h = refs[-1]  # last occurrence (a printed TOC may mention it earlier)
    pos = {id_[:2]: i for i, id_ in enumerate(stream)}
    start = pos.get((h["page"], h["line"]))
    if start is None:
        return None
    end = len(stream)
    later = [x for x in headings_flat
             if (x["page"], x["line"]) > (h["page"], h["line"])
             and x["level"] <= h["level"]]
    if later:
        nxt = min(later, key=lambda x: (x["page"], x["line"]))
        end = pos.get((nxt["page"], nxt["line"]), end)
    return stream[start + 1:end]


def find_region_fallback(stream):
    idx = [i for i, (_p, _l, t) in enumerate(stream) if BRACKET_START.match(t.strip())]
    if len(idx) >= 2:
        return stream[idx[0]:]
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Parse a reference list into structured records.")
    ap.add_argument("--pages", required=True, help="per-page text file")
    ap.add_argument("--headings", default=None,
                    help="headings.json from heading_tree.py (optional)")
    ap.add_argument("--out", required=True, help="output directory")
    args = ap.parse_args(argv)

    try:
        pages, warnings = read_pages(args.pages)
    except OSError as exc:
        print("error: cannot read pages file: %s" % exc, file=sys.stderr)
        return 2

    stream = [(p, l, t) for p, l, t in iter_lines(pages)]
    region, located_by = None, None
    if args.headings:
        try:
            hflat = load_json(args.headings).get("flat", [])
        except OSError as exc:
            print("error: cannot read headings file: %s" % exc, file=sys.stderr)
            return 2
        region = find_region_with_headings(stream, hflat)
        if region is not None:
            located_by = "headings"
    if region is None:
        region = find_region_fallback(stream)
        located_by = "trailing-numbered-list fallback" if region else None

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    if not region:
        write_json({
            "status": "references_section_not_found",
            "located_by": None,
            "count": 0,
            "summary": {"parsed": 0, "partial": 0, "raw": 0},
            "entries": [],
            "warnings": warnings + ["no References heading and no trailing "
                                    "numbered list detected"],
        }, outdir / "references.json")
        print("refs_parse: reference section not found", file=sys.stderr)
        return 3

    raw_entries = split_entries(region)
    entries = []
    for e in raw_entries:
        rec = parse_entry(" ".join(p.strip() for p in e["parts"] if p.strip()))
        rec["page"] = e["page"]
        entries.append(rec)

    summary = {"parsed": 0, "partial": 0, "raw": 0}
    for rec in entries:
        summary[rec["parse_status"]] += 1
    styles = {r["style"] for r in entries}
    style_hint = styles.pop() if len(styles) == 1 else ("mixed" if styles else "unknown")

    write_json({
        "status": "ok",
        "located_by": located_by,
        "style_hint": style_hint,
        "count": len(entries),
        "summary": summary,
        "entries": entries,
        "warnings": warnings,
    }, outdir / "references.json")
    print("refs_parse: entries=%d parsed=%d partial=%d raw=%d (%s)"
          % (len(entries), summary["parsed"], summary["partial"],
             summary["raw"], style_hint))
    return 0


if __name__ == "__main__":
    sys.exit(main())
