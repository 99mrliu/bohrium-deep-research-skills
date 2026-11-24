#!/usr/bin/env python3
"""check_consistency.py — enforce the locked glossary on a translation.

Part of the termbase-forge skill bundle (术语资产工程).

Given glossary.json, a source text, and a translation text, verify:
  (a) section lock: for every glossary entry whose source term appears in
      the source, the locked target appears at least once in every
      translation section that corresponds to a source section containing
      the term (sections: markdown headings, else blank-line blocks);
  (b) forbidden variants: any occurrence of a forbidden_variant anywhere in
      the translation is an error (with line numbers);
  (c) untranslated_leak: source term present in the source but the locked
      target occurs zero times anywhere in the translation;
  (d) first_mention: if the entry defines a first_mention form
      (e.g. 中文全称（English full name, ABBR）), warn if that exact form
      never appears in the translation.

Writes glossary_check.json and exits 0 (no errors) or 1 (errors found).

Usage:
    python3 check_consistency.py glossary.json source.txt translation.md \
        [-o glossary_check.json]
"""
import argparse
import json
import re
import sys


def split_sections(text):
    """Same sectioning rule as extract_terms.py: markdown headings if any,
    else blank-line blocks. Returns [{name, start, text}]."""
    lines = text.splitlines()
    has_headings = any(l.lstrip().startswith("#") for l in lines)
    raw = []
    if has_headings:
        cur = {"name": "(preamble)", "start": 1, "lines": []}
        for i, line in enumerate(lines, 1):
            if line.lstrip().startswith("#"):
                if cur["lines"]:
                    raw.append(cur)
                name = line.strip().lstrip("#").strip() or ("heading@%d" % i)
                cur = {"name": name, "start": i, "lines": [line]}
            else:
                cur["lines"].append(line)
        if cur["lines"]:
            raw.append(cur)
    else:
        cur = {"name": "block-1", "start": 1, "lines": []}
        n = 1
        for i, line in enumerate(lines, 1):
            if line.strip() == "":
                if cur["lines"]:
                    raw.append(cur)
                    n += 1
                    cur = {"name": "block-%d" % n, "start": i + 1, "lines": []}
                else:
                    cur["start"] = i + 1
            else:
                cur["lines"].append(line)
        if cur["lines"]:
            raw.append(cur)
    return [{"name": s["name"], "start": s["start"], "text": "\n".join(s["lines"])}
            for s in raw]


def find_occurrences(text, needle):
    """Word-boundary, case-insensitive matching for ASCII needles; plain
    case-insensitive substring matching for needles containing CJK etc."""
    if not needle:
        return []
    if all(ord(c) < 128 for c in needle):
        pat = re.compile(r"\b" + re.escape(needle) + r"\b", re.IGNORECASE)
    else:
        pat = re.compile(re.escape(needle), re.IGNORECASE)
    return list(pat.finditer(text))


def lines_of(text, matches):
    return [text.count("\n", 0, m.start()) + 1 for m in matches]


def main():
    ap = argparse.ArgumentParser(description="Enforce a locked glossary on a translation.")
    ap.add_argument("glossary")
    ap.add_argument("source")
    ap.add_argument("translation")
    ap.add_argument("-o", "--output", default="glossary_check.json")
    args = ap.parse_args()

    try:
        with open(args.glossary, encoding="utf-8") as f:
            entries = json.load(f)
        with open(args.source, encoding="utf-8") as f:
            src_text = f.read()
        with open(args.translation, encoding="utf-8") as f:
            tgt_text = f.read()
    except (OSError, json.JSONDecodeError) as exc:
        print("check_consistency: cannot read input: %s" % exc, file=sys.stderr)
        return 1
    if not isinstance(entries, list):
        print("check_consistency: glossary must be a list", file=sys.stderr)
        return 1

    src_secs = split_sections(src_text)
    tgt_secs = split_sections(tgt_text)
    notes = []
    if len(src_secs) != len(tgt_secs):
        notes.append("section count differs: source=%d translation=%d; sections "
                     "paired by index" % (len(src_secs), len(tgt_secs)))

    results = []
    n_errors = n_warnings = 0
    for e in entries:
        if not isinstance(e, dict):
            continue
        src = (e.get("source") or "").strip()
        tgt = (e.get("target") or "").strip()
        if not src:
            continue
        issues = []
        src_matches = find_occurrences(src_text, src)
        tgt_matches = find_occurrences(tgt_text, tgt) if tgt else []
        src_count = len(src_matches)
        tgt_count = len(tgt_matches)

        if src_count == 0:
            results.append({"source": src, "target": tgt, "source_count": 0,
                            "target_count": tgt_count, "verdict": "source_absent",
                            "issues": []})
            continue

        # (c) untranslated leak
        if tgt_count == 0:
            issues.append({"type": "untranslated_leak", "severity": "error",
                           "message": "source term appears %d time(s) but locked "
                                      "target %r never appears in the translation"
                                      % (src_count, tgt),
                           "source_lines": lines_of(src_text, src_matches)})

        # (a) section lock
        section_detail = []
        for idx, ssec in enumerate(src_secs):
            s_in = len(find_occurrences(ssec["text"], src))
            if s_in == 0:
                continue
            if idx < len(tgt_secs):
                t_in = len(find_occurrences(tgt_secs[idx]["text"], tgt)) if tgt else 0
                t_name = tgt_secs[idx]["name"]
            else:
                t_in, t_name = 0, "(no corresponding translation section)"
            section_detail.append({"section": ssec["name"], "source_hits": s_in,
                                   "translation_section": t_name, "target_hits": t_in})
            if t_in == 0:
                issues.append({"type": "section_lock_violation", "severity": "error",
                               "message": "source term appears in section %r but "
                                          "locked target %r is absent from the "
                                          "corresponding translation section %r"
                                          % (ssec["name"], tgt, t_name),
                               "section": ssec["name"]})

        # (b) forbidden variants
        for variant in (e.get("forbidden_variants") or []):
            vm = find_occurrences(tgt_text, variant)
            if vm:
                issues.append({"type": "forbidden_variant", "severity": "error",
                               "message": "forbidden variant %r of %r appears %d "
                                          "time(s)" % (variant, src, len(vm)),
                               "lines": lines_of(tgt_text, vm)})

        # (d) first-mention form
        fm = (e.get("first_mention") or "").strip()
        if fm and fm not in tgt_text:
            issues.append({"type": "first_mention_missing", "severity": "warning",
                           "message": "first-mention form %r never appears "
                                      "verbatim" % fm})

        errs = [i for i in issues if i["severity"] == "error"]
        warns = [i for i in issues if i["severity"] == "warning"]
        n_errors += len(errs)
        n_warnings += len(warns)
        verdict = "locked_ok" if not issues else (
            "error" if errs else "ok_with_warnings")
        results.append({"source": src, "target": tgt,
                        "discipline": e.get("discipline", ""),
                        "source_count": src_count, "target_count": tgt_count,
                        "source_lines": lines_of(src_text, src_matches),
                        "target_lines": lines_of(tgt_text, tgt_matches),
                        "sections": section_detail,
                        "verdict": verdict, "issues": issues})

    ok = n_errors == 0
    report = {
        "glossary": args.glossary, "source": args.source,
        "translation": args.translation,
        "summary": {"terms_checked": len(results), "errors": n_errors,
                    "warnings": n_warnings, "ok": ok},
        "notes": notes,
        "terms": results,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("check_consistency: %d terms, %d errors, %d warnings -> %s"
          % (len(results), n_errors, n_warnings, args.output))
    for r in results:
        print("  %-32s -> %-20s src x%-3d tgt x%-3d %s"
              % (r["source"][:32], r["target"][:20], r.get("source_count", 0),
                 r.get("target_count", 0), r["verdict"]))
        for i in r["issues"]:
            loc = (" lines " + str(i.get("lines"))) if i.get("lines") else ""
            print("      %s [%s]%s %s" % (i["severity"].upper(), i["type"], loc,
                                          i["message"]))
    print("verdict: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
