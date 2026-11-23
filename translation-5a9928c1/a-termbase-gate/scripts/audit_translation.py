#!/usr/bin/env python3
"""audit_translation.py -- machine-audit bilingual segments against a locked termbase.

Usage:
    python3 audit_translation.py --termbase termbase.locked.json --pairs pairs.jsonl \
        --out audit_report.json [--md audit_report.md]

pairs.jsonl: one JSON object per line: {"seg_id","section","source","target"}.

Matching rule (source occurrence): case-insensitive substring of source_term after
normalizing whitespace; '-' and space are equivalent; optional trailing 's' (plural)
on the final word is allowed. For kind=="acronym" entries the acronym itself also
counts as a source occurrence, and the acronym in the target also counts as PASS.

Exit 1 if any violation, else 0. Stdlib only.
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict


def normalize(text):
    """Lowercase, unify hyphen/space, collapse whitespace."""
    t = text.lower().replace("-", " ").replace("\u2010", " ").replace("\u2011", " ")
    return re.sub(r"\s+", " ", t).strip()


def term_pattern(term):
    """Regex for a source occurrence of term: hyphen/space equivalence, optional plural s."""
    parts = normalize(term).split(" ")
    body = r"[ \-]".join(re.escape(p) for p in parts)
    # optional trailing plural 's' on the last token (only if it doesn't already end in 's')
    if parts and not parts[-1].endswith("s"):
        body += r"s?"
    return re.compile(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])", re.IGNORECASE)


def source_contains(source, entry):
    if term_pattern(entry["source_term"]).search(source):
        return True
    if entry.get("kind") == "acronym" and entry.get("acronym"):
        if re.search(r"\b" + re.escape(entry["acronym"]) + r"\b", source):
            return True
    return False


def target_ok(target, entry):
    if entry.get("target") and entry["target"] in target:
        return True
    if entry.get("kind") == "acronym" and entry.get("acronym"):
        if re.search(r"\b" + re.escape(entry["acronym"]) + r"\b", target):
            return True
    return False


def snippet(text, width=80):
    t = re.sub(r"\s+", " ", text).strip()
    return t if len(t) <= width else t[: width - 1] + "…"


def main():
    ap = argparse.ArgumentParser(description="Audit bilingual pairs against a locked termbase.")
    ap.add_argument("--termbase", required=True)
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--md", default=None, help="optional markdown report path")
    args = ap.parse_args()

    with open(args.termbase, "r", encoding="utf-8") as f:
        termbase = json.load(f)
    entries = [e for e in termbase.get("entries", []) if e.get("target") and not e.get("dropped")]

    pairs = []
    with open(args.pairs, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                p = json.loads(line)
            except json.JSONDecodeError as ex:
                sys.exit(f"ERROR: pairs.jsonl line {lineno}: invalid JSON: {ex}")
            for field in ("seg_id", "section", "source", "target"):
                if field not in p:
                    sys.exit(f"ERROR: pairs.jsonl line {lineno}: missing field {field!r}")
            pairs.append(p)

    violations = []
    checks = 0
    coverage = {}
    by_section = defaultdict(lambda: {"checks": 0, "violations": 0})

    for e in entries:
        cov_sections = {}
        for p in pairs:
            if not source_contains(p["source"], e):
                continue
            checks += 1
            sec = p["section"]
            by_section[sec]["checks"] += 1
            ok = target_ok(p["target"], e)
            if sec not in cov_sections:
                cov_sections[sec] = True
            cov_sections[sec] = cov_sections[sec] and ok
            if not ok:
                violations.append({
                    "type": "term-drift",
                    "severity": "blocker",
                    "entry_id": e["id"],
                    "seg_id": p["seg_id"],
                    "section": sec,
                    "source_term": e["source_term"],
                    "expected_target": e["target"],
                    "target_snippet": snippet(p["target"]),
                })
                by_section[sec]["violations"] += 1
            # forbidden variants
            for fv in e.get("forbidden_variants", []):
                if fv and fv in p["target"]:
                    violations.append({
                        "type": "forbidden-variant",
                        "severity": "blocker",
                        "entry_id": e["id"],
                        "seg_id": p["seg_id"],
                        "section": sec,
                        "source_term": e["source_term"],
                        "expected_target": e["target"],
                        "forbidden_variant": fv,
                        "target_snippet": snippet(p["target"]),
                    })
                    by_section[sec]["violations"] += 1
        coverage[e["id"]] = {
            "source_term": e["source_term"],
            "sections": sorted(cov_sections.keys()),
            "ok": all(cov_sections.values()) if cov_sections else True,
            "occurrences": sum(1 for p in pairs if source_contains(p["source"], e)),
        }

    # uncovered-entry warnings: locked entries never checked at all
    warnings = []
    for e in entries:
        if coverage[e["id"]]["occurrences"] == 0:
            warnings.append({
                "type": "uncovered-entry",
                "severity": "warning",
                "entry_id": e["id"],
                "source_term": e["source_term"],
                "detail": "term never occurs in any audited source segment",
            })

    report = {
        "summary": {
            "entries": len(entries),
            "segments": len(pairs),
            "checks": checks,
            "violations": len(violations),
            "warnings": len(warnings),
            "by_section": {k: dict(v) for k, v in sorted(by_section.items())},
        },
        "violations": violations,
        "warnings": warnings,
        "coverage": coverage,
        "termbase_sha256": termbase.get("termbase_sha256"),
    }
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    if args.md:
        lines = ["# Translation audit report", ""]
        s = report["summary"]
        lines.append(f"- entries: {s['entries']}  segments: {s['segments']}  "
                     f"checks: {s['checks']}  **violations: {s['violations']}**  warnings: {s['warnings']}")
        lines.append("")
        lines.append("| section | checks | violations |")
        lines.append("|---|---|---|")
        for sec, v in s["by_section"].items():
            lines.append(f"| {sec} | {v['checks']} | {v['violations']} |")
        lines.append("")
        if violations:
            lines.append("| # | type | seg_id | section | source_term | expected | actual snippet |")
            lines.append("|---|---|---|---|---|---|---|")
            for i, v in enumerate(violations, 1):
                extra = v.get("forbidden_variant", "")
                exp = v["expected_target"] + (f" (forbidden: {extra})" if extra else "")
                lines.append(f"| {i} | {v['type']} | {v['seg_id']} | {v['section']} | "
                             f"{v['source_term']} | {exp} | {v['target_snippet']} |")
            lines.append("")
        lines.append("| entry | term | sections | ok |")
        lines.append("|---|---|---|---|")
        for eid, c in coverage.items():
            lines.append(f"| {eid} | {c['source_term']} | {', '.join(c['sections']) or '—'} | "
                         f"{'✅' if c['ok'] else '❌'} |")
        with open(args.md, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    s = report["summary"]
    print(f"audit_translation: {s['entries']} entries x {s['segments']} segments -> "
          f"{s['checks']} checks, {s['violations']} violation(s), {s['warnings']} warning(s)")
    for v in violations:
        print(f"  VIOLATION [{v['type']}] {v['seg_id']} ({v['section']}): "
              f"{v['source_term']!r} expected {v['expected_target']!r} :: {v['target_snippet']}")
    for w in warnings:
        print(f"  WARNING [{w['type']}] {w['entry_id']} {w['source_term']!r}: {w['detail']}")
    print(f"wrote {args.out}" + (f" and {args.md}" if args.md else ""))
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
