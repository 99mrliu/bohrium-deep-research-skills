#!/usr/bin/env python3
"""extract_sources.py -- build the evidence store for grounded introduction writing.

Reads the case descriptor and the declared material files and produces one JSON
evidence store. Every later check in this skill binds claims to THIS store, so
the store is the single point where the agent confirms what the sources
actually say. Read actual files; never rely on directory labels.

Usage:
  python3 extract_sources.py --case /input/case.json --out-dir /app/work/evidence

Exit codes: 0 ok, 2 usage/IO error.
"""
import argparse
import json
import re
import sys
from pathlib import Path


def norm(text):
    """Whitespace-normalize for verbatim comparison. Case is preserved."""
    return re.sub(r"\s+", " ", (text or "")).strip()


def load_case(path):
    case = json.loads(Path(path).read_text(encoding="utf-8"))
    base = Path(path).resolve().parent
    return case, base


def resolve(base, rel):
    p = Path(rel)
    return p if p.is_absolute() else (base / p)


def parse_bibliography(case, base):
    """Return {key: record} and a list of material-gap notes."""
    refs, gaps = {}, []
    mat = case.get("material", {})
    bib_json = mat.get("bibliography")
    bib_md = mat.get("bibliography_readable")
    data = None
    if bib_json and resolve(base, bib_json).is_file():
        data = json.loads(resolve(base, bib_json).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        entries = data.get("references") or data.get("entries") or []
    elif isinstance(data, list):
        entries = data
    else:
        entries = []
        if bib_json:
            gaps.append("bibliography file missing or unreadable: %s" % bib_json)
    for i, e in enumerate(entries):
        key = str(e.get("key") or e.get("id") or "ref%02d" % (i + 1))
        abstract = (e.get("abstract") or "").strip()
        title = (e.get("title") or "").strip()
        level = "abstract" if abstract else ("title-only" if title else "metadata-only")
        if level != "abstract":
            gaps.append("reference %s has no abstract (evidence level: %s); "
                        "attribute no findings to it" % (key, level))
        text_parts = [p for p in [title, abstract] if p]
        refs[key] = {
            "key": key,
            "authors": e.get("authors", []),
            "year": e.get("year"),
            "title": title,
            "journal": e.get("journal"),
            "doi": e.get("doi"),
            "evidence_level": level,
            "text": "\n".join(text_parts),
            "norm_text": norm("\n".join(text_parts)),
        }
    md_keys = []
    if bib_md and resolve(base, bib_md).is_file():
        md_text = resolve(base, bib_md).read_text(encoding="utf-8")
        md_keys = re.findall(r"^\s*\d+\.\s+(.+?)\(", md_text, flags=re.M)
    return refs, gaps, len(md_keys)


def parse_facts(case, base):
    mat = case.get("material", {})
    rel = mat.get("manuscript_facts")
    facts, lines = [], []
    if rel and resolve(base, rel).is_file():
        lines = resolve(base, rel).read_text(encoding="utf-8").splitlines()
    else:
        return facts, ["manuscript fact base missing or unreadable: %s" % rel]
    for n, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith("- ") and len(s) > 4:
            facts.append({"line": n, "text": s[2:].strip()})
    return facts, []


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    try:
        case, base = load_case(args.case)
    except Exception as exc:
        print("error: cannot read case: %s" % exc, file=sys.stderr)
        return 2
    refs, gaps, md_count = parse_bibliography(case, base)
    facts, fact_gaps = parse_facts(case, base)
    gaps += fact_gaps
    anchors = case.get("constraints", {}).get("available_anchors", [])
    store = {
        "case_id": case.get("case_id"),
        "constraints": case.get("constraints", {}),
        "anchors": anchors,
        "refs": refs,
        "facts": facts,
        "facts_norm": norm("\n".join(f["text"] for f in facts)),
        "material_gaps": gaps,
    }
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "evidence_store.json").write_text(
        json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    idx = ["# Evidence store index", "",
           "case_id: %s" % store["case_id"],
           "references: %d (md-listed entries: %d)" % (len(refs), md_count),
           "facts: %d bullet lines" % len(facts),
           "anchors: %s" % ", ".join(anchors), "", "## Evidence levels", ""]
    for k, r in refs.items():
        idx.append("- %s [%s] %s (%s)" % (k, r["evidence_level"], r["title"], r["year"]))
    if gaps:
        idx += ["", "## Material gaps", ""] + ["- " + g for g in gaps]
    (out / "index.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
    print("evidence store: %d refs, %d facts, %d material-gap notes -> %s"
          % (len(refs), len(facts), len(gaps), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
