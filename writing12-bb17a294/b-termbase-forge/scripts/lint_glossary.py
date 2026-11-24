#!/usr/bin/env python3
"""lint_glossary.py — validate a curated bilingual glossary.

Part of the termbase-forge skill bundle (术语资产工程).

Expected schema: glossary.json is a JSON list of entries:
  {
    "source": "perovskite solar cell",        # required, non-empty
    "target": "钙钛矿太阳能电池",              # required, non-empty
    "note": "locked 2026-11-24",              # required (may be "")
    "discipline": "photovoltaics",            # required, non-empty
    "first_mention": "钙钛矿太阳能电池（perovskite solar cell, PSC）",  # optional
    "forbidden_variants": ["钙钛矿电池"]       # optional list of strings
  }

Checks (errors unless noted):
  - top level is a list of objects
  - required fields present and of correct type
  - empty source/target/discipline
  - duplicate sources with conflicting targets (same target = warning only)
  - target containing the untranslated source term (skipped for acronyms /
    very short sources)
  - self-inconsistent forbidden_variants (variant == locked target or
    variant == source)

Exit code 0 = no errors, 1 = errors found (or unreadable input).
Use --json to emit the report as JSON to stdout.
"""
import argparse
import json
import re
import sys

REQUIRED_STR = ["source", "target", "note", "discipline"]
NONEMPTY = ["source", "target", "discipline"]


def is_acronymish(s):
    return bool(re.fullmatch(r"[A-Z][A-Z0-9]{0,9}", s)) or len(s) < 4


def lint(entries):
    errors, warnings = [], []
    seen_sources = {}  # casefolded source -> (index, target)

    def err(msg):
        errors.append(msg)

    def warn(msg):
        warnings.append(msg)

    for i, e in enumerate(entries):
        tag = "entry[%d]" % i
        if not isinstance(e, dict):
            err("%s: not an object" % tag)
            continue
        src = e.get("source")
        if isinstance(src, str) and src.strip():
            tag = "entry[%d] %r" % (i, src)
        for f in REQUIRED_STR:
            if f not in e:
                err("%s: missing required field %r" % (tag, f))
            elif not isinstance(e[f], str):
                err("%s: field %r must be a string" % (tag, f))
        for f in NONEMPTY:
            if isinstance(e.get(f), str) and not e[f].strip():
                err("%s: field %r must not be empty" % (tag, f))
        src = e.get("source") if isinstance(e.get("source"), str) else None
        tgt = e.get("target") if isinstance(e.get("target"), str) else None

        # duplicate sources
        if src and src.strip():
            key = src.strip().casefold()
            if key in seen_sources:
                j, prev_tgt = seen_sources[key]
                if tgt is not None and prev_tgt != tgt:
                    err("%s: duplicate source also at entry[%d] with CONFLICTING "
                        "target %r vs %r" % (tag, j, tgt, prev_tgt))
                else:
                    warn("%s: duplicate source of entry[%d] (same target); "
                         "redundant" % (tag, j))
            else:
                seen_sources[key] = (i, tgt)

        # untranslated source word inside target
        if src and tgt and src.strip() and tgt.strip() and not is_acronymish(src.strip()):
            if src.strip().casefold() in tgt.strip().casefold():
                err("%s: target contains the untranslated source term; "
                    "translate it or use first_mention" % tag)

        # forbidden_variants sanity
        fv = e.get("forbidden_variants")
        if fv is not None:
            if not isinstance(fv, list) or any(not isinstance(v, str) for v in fv):
                err("%s: forbidden_variants must be a list of strings" % tag)
            else:
                for v in fv:
                    if tgt is not None and v.strip() == tgt.strip():
                        err("%s: forbidden_variant %r equals the locked target "
                            "(self-inconsistent)" % (tag, v))
                    if src is not None and v.strip().casefold() == src.strip().casefold():
                        err("%s: forbidden_variant %r equals the source term "
                            "(self-inconsistent)" % (tag, v))
                if len({v.strip() for v in fv}) != len(fv):
                    warn("%s: duplicate entries inside forbidden_variants" % tag)

        fm = e.get("first_mention")
        if fm is not None and not isinstance(fm, str):
            err("%s: first_mention must be a string" % tag)

    return errors, warnings


def main():
    ap = argparse.ArgumentParser(description="Lint a curated glossary.json.")
    ap.add_argument("glossary", help="path to glossary.json")
    ap.add_argument("--json", action="store_true",
                    help="print the lint report as JSON to stdout")
    args = ap.parse_args()

    try:
        with open(args.glossary, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        report = {"file": args.glossary, "ok": False,
                  "errors": ["cannot read/parse glossary: %s" % exc],
                  "warnings": [], "entry_count": 0}
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json
              else "LINT ERROR: " + report["errors"][0])
        return 1

    if not isinstance(data, list):
        errors = ["top level must be a JSON list of entries"]
        warnings = []
        n = 0
    else:
        errors, warnings = lint(data)
        n = len(data)

    ok = not errors
    report = {"file": args.glossary, "ok": ok, "entry_count": n,
              "errors": errors, "warnings": warnings}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("glossary lint: %s" % args.glossary)
        print("entries: %d   errors: %d   warnings: %d" % (n, len(errors), len(warnings)))
        for m in errors:
            print("  ERROR   " + m)
        for m in warnings:
            print("  WARNING " + m)
        print("verdict: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
