#!/usr/bin/env python3
"""structure_report.py - caption index, caption/mention cross-check, result.json.

Scans per-page text for figure/table caption lines (line STARTS with
'Fig. n' / 'Figure n' / 'Table n'), indexes them, then cross-checks
in-text mentions both ways:
  * captions_without_mentions  (caption exists, never cited in text)
  * mentions_without_captions  (text cites a figure/table with no caption)

Assembles structure_report.json plus a contract-aware result.json:
the case file (--case case.json) provides case_id and output_contract;
every contract field appears in result.json, either with data or
empty-with-explanation.  Status is reported honestly.

Exit codes: 0 ok, 2 usage/IO error, 3 no --case given (result.json still
written with case_id=null and an explanation).
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_pages, write_json, load_json

CAPTION_RE = re.compile(
    r"^(\s*)(Fig(?:ure)?s?\.?\s*\d+[a-z]?|Tables?\s*\d+[a-z]?)\b[\s.:;–—-]*(.*)$",
    re.IGNORECASE)
MENTION_RE = re.compile(
    r"\b(Fig(?:ure)?s?\.?\s*\d+[a-z]?|Tables?\s*\d+[a-z]?)\b", re.IGNORECASE)
MAX_CAPTION_LINES = 3


def norm_label(raw):
    m = re.match(r"(Fig|Table)\w*\.?\s*(\d+[a-z]?)", raw, re.IGNORECASE)
    if not m:
        return raw.strip()
    prefix = "Fig. " if m.group(1).lower().startswith("fig") else "Table "
    return prefix + m.group(2)


def scan_captions(pages):
    """Return (captions, mentions). Mentions exclude the caption's own label."""
    captions, mentions = [], []
    for pg in pages:
        lines = pg["lines"]
        for i, line in enumerate(lines):
            cm = CAPTION_RE.match(line)
            caption_start = None
            if cm:
                label = norm_label(cm.group(2))
                text = cm.group(3).strip()
                j = i + 1
                while (text and not text.endswith(".")
                       and j < len(lines) and j < i + MAX_CAPTION_LINES
                       and lines[j].strip() and not CAPTION_RE.match(lines[j])):
                    text += " " + lines[j].strip()
                    j += 1
                captions.append({"label": label, "page": pg["page"],
                                 "line": i + 1, "text": text})
                caption_start = cm.start(2)
            for mm in MENTION_RE.finditer(line):
                if caption_start is not None and mm.start() == caption_start:
                    continue  # the caption's own label, not an in-text mention
                mentions.append({"label": norm_label(mm.group(1)),
                                 "page": pg["page"], "line": i + 1,
                                 "context": line.strip()[:160]})
    return captions, mentions


def cross_check(captions, mentions):
    cap_labels = {c["label"] for c in captions}
    men_labels = {m["label"] for m in mentions}
    return {
        "captions_without_mentions": [
            {"label": c["label"], "page": c["page"], "text": c["text"]}
            for c in captions if c["label"] not in men_labels],
        "mentions_without_captions": [
            {"label": lbl,
             "mentions": [m for m in mentions if m["label"] == lbl]}
            for lbl in sorted(men_labels - cap_labels)],
    }


def build_result(case, case_given, toc_data, headings_data, refs_data,
                 captions, gaps, inconsistencies, uncertainty, sources):
    contract = case.get("output_contract", {}) if case else {}
    producers = {
        "toc": lambda: toc_data,
        "headings": lambda: headings_data,
        "references": lambda: refs_data,
        "captions": lambda: {"captions": captions, "gaps": gaps},
        "structure_issues": lambda: {
            "heading_inconsistencies": inconsistencies,
            "caption_gaps": gaps},
        "uncertainty": lambda: uncertainty,
    }
    outputs = {}
    for field in contract:
        data = producers[field]() if field in producers else None
        if data is None:
            outputs[field] = {
                "status": "empty",
                "explanation": ("no producer implemented for contract field "
                                "'%s'" % field)
                             if field in producers else
                             ("unknown contract field '%s'; not produced"
                              % field),
                "data": None}
        else:
            outputs[field] = {"status": "ok", "data": data}

    if not case_given:
        status = "partial"
    elif not (toc_data or headings_data) and not refs_data:
        status = "failed"
    elif any(o["status"] == "empty" for o in outputs.values()):
        status = "partial"
    else:
        status = "success"

    raw_refs = 0
    if refs_data:
        raw_refs = refs_data.get("summary", {}).get("raw", 0)
    return {
        "case_id": case.get("case_id") if case else None,
        "status": status,
        "output_contract": contract,
        "outputs": outputs,
        "findings": {
            "heading_inconsistencies": len(inconsistencies),
            "captions_without_mentions": len(gaps["captions_without_mentions"]),
            "mentions_without_captions": len(gaps["mentions_without_captions"]),
            "references_raw": raw_refs,
        },
        "sources": sources,
        "uncertainty": uncertainty,
        "change_record": [
            {"step": 1, "tool": "heading_tree.py",
             "artifact": "headings.json / toc.json",
             "status": "consumed" if (headings_data or toc_data) else "missing"},
            {"step": 2, "tool": "refs_parse.py",
             "artifact": "references.json",
             "status": "consumed" if refs_data else "missing"},
            {"step": 3, "tool": "structure_report.py",
             "artifact": "structure_report.json / result.json",
             "status": "produced"},
        ],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Caption index + cross-checks + contract-aware result.json.")
    ap.add_argument("--pages", required=True, help="per-page text file")
    ap.add_argument("--headings", default=None, help="headings.json (optional)")
    ap.add_argument("--toc", default=None, help="toc.json (optional)")
    ap.add_argument("--refs", default=None, help="references.json (optional)")
    ap.add_argument("--case", default=None,
                    help="case.json with case_id and output_contract")
    ap.add_argument("--out", required=True, help="output directory")
    args = ap.parse_args(argv)

    try:
        pages, warnings = read_pages(args.pages)
    except OSError as exc:
        print("error: cannot read pages file: %s" % exc, file=sys.stderr)
        return 2

    headings_data = toc_data = refs_data = None
    for attr, var in (("headings", "headings_data"), ("toc", "toc_data"),
                      ("refs", "refs_data")):
        path = getattr(args, attr)
        if path:
            try:
                if var == "headings_data":
                    headings_data = load_json(path)
                elif var == "toc_data":
                    toc_data = load_json(path)
                else:
                    refs_data = load_json(path)
            except OSError as exc:
                print("error: cannot read %s: %s" % (path, exc), file=sys.stderr)
                return 2

    case, case_given = None, False
    if args.case:
        try:
            case = load_json(args.case)
            case_given = True
        except OSError as exc:
            print("error: cannot read case file: %s" % exc, file=sys.stderr)
            return 2

    captions, mentions = scan_captions(pages)
    gaps = cross_check(captions, mentions)
    inconsistencies = (headings_data or {}).get("inconsistencies", [])

    uncertainty = list(warnings)
    if refs_data:
        n_raw = refs_data.get("summary", {}).get("raw", 0)
        if n_raw:
            uncertainty.append(
                "%d reference(s) kept verbatim with parse_status=raw; "
                "missing fields were left null, never invented" % n_raw)
    uncertainty.append(
        "unnumbered headings are leveled by typography heuristics and may be "
        "mis-leveled without font-size hints")
    uncertainty.append(
        "in-text mentions are string matches; a wrapped line starting with "
        "'Fig. n' can be misread as a caption")
    if gaps["captions_without_mentions"] or gaps["mentions_without_captions"]:
        uncertainty.append("caption/mention gaps detected; see structure_issues")

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "ok",
        "counts": {
            "pages": len(pages),
            "headings": len((headings_data or {}).get("flat", [])),
            "heading_inconsistencies": len(inconsistencies),
            "captions": len(captions),
            "mention_instances": len(mentions),
            "distinct_mentioned_labels": len({m["label"] for m in mentions}),
            "references": (refs_data or {}).get("count", 0),
            "reference_parse": (refs_data or {}).get(
                "summary", {"parsed": 0, "partial": 0, "raw": 0}),
        },
        "captions": captions,
        "mentions": mentions,
        "gaps": gaps,
        "heading_inconsistencies": inconsistencies,
    }
    write_json(report, outdir / "structure_report.json")

    sources = [Path(args.pages).name]
    for p in (args.headings, args.toc, args.refs, args.case):
        if p:
            sources.append(Path(p).name)
    result = build_result(case, case_given, toc_data, headings_data, refs_data,
                          captions, gaps, inconsistencies, uncertainty, sources)
    write_json(result, outdir / "result.json")

    print("structure_report: captions=%d mentions=%d gaps=%d+%d status=%s"
          % (len(captions), len(mentions),
             len(gaps["captions_without_mentions"]),
             len(gaps["mentions_without_captions"]), result["status"]))
    return 0 if case_given else 3


if __name__ == "__main__":
    sys.exit(main())
