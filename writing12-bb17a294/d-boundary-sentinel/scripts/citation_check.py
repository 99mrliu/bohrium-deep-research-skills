#!/usr/bin/env python3
"""citation_check.py — build a citation ledger from the source (all in-text
markers plus reference-list entries) and verify it against the translation
and its reference section.

Checks:
  1. Every in-text citation marker is preserved: numeric markers verbatim
     (same identifier, e.g. "[12]", "[3-5]"); author-year markers keep the
     author surname and the year ("et al." may be kept or rendered "等" —
     documented allowance; see references/method.md).
     Missing -> ERROR `intext_citation_lost`.
  2. Every reference-list entry of the source is present EXACTLY ONCE in the
     translation's reference section, matched by identifier (numeric label,
     or first-author surname + year). Missing -> ERROR `reference_missing`;
     duplicated -> ERROR `reference_duplicated`.
  3. Entries appear in the ORIGINAL ORDER.
     Otherwise -> ERROR `reference_order_changed`.
  4. No fabricated entries: an entry in the translation with no source
     counterpart -> ERROR `reference_fabricated`.

Reference-entry parsing (heuristic): the reference section starts at a line
"References" / "参考文献" / "参考资料"; entries are split on blank lines, and
additionally at lines starting with a numeric label ("[12]", "3."). For each
entry the identifier is the numeric label, or the leading surname plus the
first 4-digit year. Unparseable entries produce a WARNING (human resolves).

Exit code: 0 = no errors, 1 = at least one error, 2 = usage/IO failure.

Usage:
    python3 citation_check.py SOURCE_TXT TRANSLATION_MD [-o citation_report.json]
"""

import argparse
import json
import re
import sys

from cite_patterns import extract_citations, citation_preserved

_REF_HEADING_RE = re.compile(
    r"^[ \t]*#{0,6}[ \t]*(references|参考文献|参考资料)[^\n]*$", re.I | re.M)
_NUM_LABEL_RE = re.compile(r"^\s*\[(\d+)\]")
_NUM_DOT_RE = re.compile(r"^\s*(\d+)[.)]\s")
_SURNAME_RE = re.compile(r"^\s*([A-Z][A-Za-z'’\-]+)")
_YEAR_RE = re.compile(r"(\d{4})")


def split_reference_section(text):
    """Return (body, reference_block). reference_block may be ''."""
    m = _REF_HEADING_RE.search(text)
    if not m:
        return text, ""
    return text[:m.start()], text[m.end():]


def split_entries(block):
    """Split a reference block into entries: blank-line chunks, further split
    at lines that start a new numbered entry."""
    entries, current = [], []
    for ln in block.splitlines():
        starts_new = bool(_NUM_LABEL_RE.match(ln) or _NUM_DOT_RE.match(ln))
        if not ln.strip():
            if current:
                entries.append(" ".join(current).strip())
                current = []
        elif starts_new and current:
            entries.append(" ".join(current).strip())
            current = [ln.strip()]
        else:
            current.append(ln.strip())
    if current:
        entries.append(" ".join(current).strip())
    return [e for e in entries if e]


def entry_identifier(entry):
    """Return (kind, identifier) or (None, None) if unparseable.
    kind: 'num' -> identifier is the numeric label; 'ay' -> 'Surname Year'."""
    m = _NUM_LABEL_RE.match(entry) or _NUM_DOT_RE.match(entry)
    if m:
        return "num", m.group(1)
    sm = _SURNAME_RE.match(entry)
    ym = _YEAR_RE.search(entry)
    if sm and ym:
        return "ay", "%s %s" % (sm.group(1), ym.group(1))
    return None, None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", help="source text (UTF-8) incl. reference list")
    ap.add_argument("translation", help="translation (UTF-8) incl. reference list")
    ap.add_argument("-o", "--output", default="citation_report.json")
    args = ap.parse_args(argv)

    try:
        with open(args.source, "r", encoding="utf-8") as f:
            src_text = f.read()
        with open(args.translation, "r", encoding="utf-8") as f:
            zh_text = f.read()
    except OSError as e:
        print("citation_check failed: %s" % e, file=sys.stderr)
        return 2

    src_body, src_refs = split_reference_section(src_text)
    zh_body, zh_refs = split_reference_section(zh_text)

    findings = []

    def add(kind, severity, verdict, action, extra=None):
        f = {"kind": kind, "severity": severity,
             "verdict": verdict, "suggested_action": action}
        if extra:
            f.update(extra)
        findings.append(f)

    # --- 1. in-text markers -------------------------------------------------
    intext = []
    for cit in extract_citations(src_body):
        ok = citation_preserved(cit, zh_body)
        intext.append({"marker": cit, "status": "preserved" if ok else "lost"})
        if not ok:
            add("intext_citation_lost", "error",
                "in-text citation %s (%s) missing from translation body"
                % (cit["raw"], cit["kind"]),
                "Restore the marker (numeric verbatim; author-year keeps "
                "author + year, et al. -> 等 allowed).")

    # --- 2-4. reference entries --------------------------------------------
    src_entries = split_entries(src_refs)
    zh_entries = split_entries(zh_refs)
    src_ids, zh_ids = [], []
    ref_status = []

    for e in src_entries:
        kind, ident = entry_identifier(e)
        src_ids.append((kind, ident))
        if kind is None:
            add("source_entry_unparsed", "warning",
                "could not parse identifier for source entry: %s" % e[:80],
                "Parse this entry manually and verify it by hand.")
    for e in zh_entries:
        kind, ident = entry_identifier(e)
        zh_ids.append((kind, ident))
        if kind is None:
            add("translation_entry_unparsed", "warning",
                "could not parse identifier for translation entry: %s" % e[:80],
                "Parse this entry manually and verify it by hand.")

    for i, (e, (kind, ident)) in enumerate(zip(src_entries, src_ids)):
        if kind is None:
            ref_status.append({"source_entry": e[:120], "status": "unparsed"})
            continue
        count = zh_ids.count((kind, ident))
        status = "ok" if count == 1 else ("missing" if count == 0 else "duplicated")
        ref_status.append({"source_entry": e[:120], "identifier": ident,
                           "count_in_translation": count, "status": status})
        if count == 0:
            add("reference_missing", "error",
                "reference entry '%s' absent from translation reference list"
                % ident,
                "Add the entry (translated title allowed; keep identifier, "
                "authors, year, venue).")
        elif count > 1:
            add("reference_duplicated", "error",
                "reference entry '%s' appears %d times in translation" % (ident, count),
                "Keep exactly one copy, in the original position.")

    src_order = [x for x in src_ids if x[0] is not None]
    zh_order = [x for x in zh_ids if x[0] is not None and x in src_order]
    order_ok = (zh_order == src_order)
    if src_order and not order_ok:
        add("reference_order_changed", "error",
            "translation reference order %s does not match source order %s"
            % ([i for _, i in zh_order], [i for _, i in src_order]),
            "Reorder the translated reference list to the original order.")

    for e, (kind, ident) in zip(zh_entries, zh_ids):
        if kind is not None and (kind, ident) not in src_ids:
            add("reference_fabricated", "error",
                "translation reference entry '%s' has no source counterpart: "
                "%s" % (ident, e[:80]),
                "Delete the fabricated entry or trace it to the source; "
                "never invent references.")

    errors = sum(1 for f in findings if f["severity"] == "error")
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    report = {
        "summary": {
            "intext_markers": len(intext),
            "intext_lost": sum(1 for x in intext if x["status"] == "lost"),
            "source_entries": len(src_entries),
            "translation_entries": len(zh_entries),
            "order_ok": order_ok,
            "errors": errors,
            "warnings": warnings,
            "status": "pass" if errors == 0 else "fail",
        },
        "in_text": intext,
        "references": ref_status,
        "findings": findings,
        "note": "Heuristic, recall-oriented check; human resolves findings. "
                "et al. may be kept or rendered 等 (documented allowance).",
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    s = report["summary"]
    print("intext=%d lost=%d src_entries=%d zh_entries=%d order_ok=%s "
          "errors=%d warnings=%d status=%s -> %s"
          % (s["intext_markers"], s["intext_lost"], s["source_entries"],
             s["translation_entries"], s["order_ok"], s["errors"],
             s["warnings"], s["status"], args.output))
    for f in findings:
        print("  [%s] %s: %s" % (f["severity"], f["kind"], f["verdict"]))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
