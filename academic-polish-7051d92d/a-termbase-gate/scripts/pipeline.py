#!/usr/bin/env python3
"""pipeline.py - freeze a source text into anchored sentence units, apply
reviewed edit batches, and export the polished deliverables.

Subcommands
-----------
prepare      Freeze the source into sentence/heading units u0001... with
             absolute offsets, section labels and per-unit protected tokens
             (number+unit pairs, citations, Fig./Eq./Table references,
             URLs/DOIs, bare numbers).
apply-edits  Apply an edit batch JSON. Every edit must carry
             review.decision == "approve" and a non-empty review.reason;
             unreviewed edits are reverted. Protected tokens of the original
             unit are compared token-by-token against the new text; any loss
             reverts the edit. Nothing is silently dropped.
export       Rebuild polished.md from the frozen units plus applied edits,
             and write changes.json, audit.json and terminology-report.md.

Python 3 standard library only. No network. Deterministic output: no random
values and no timestamps are written into artifacts.
"""
import argparse
import hashlib
import json
import re
import sys

HEAD_RE = re.compile(r"^(#{1,6}\s|\\(?:sub)*section\*?\{)")
SENT_END_RE = re.compile(r"[.!?](?=\s|$)")
TAIL_WORD_RE = re.compile(r"([A-Za-z.]+)$")
NO_SPLIT_WORDS = {
    "fig", "eq", "eqs", "al", "e.g", "i.e", "vs", "cf", "dr", "prof",
    "no", "approx", "ca", "et",
}

PROTECTED_RES = [
    ("number_unit", re.compile(
        r"\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\s?"
        r"(?:wt%|at%|vol%|mol%|mAh\s?(?:g-1|cm-2)?|Wh|mA|mV|mHz|kHz|MHz|GHz|Hz|"
        r"cm2\s?s-1|cm|mm|nm|µm|um|kPa|MPa|GPa|Pa|rpm|min|mg|kg|g|h|s|A|V|K|C|"
        r"°C|M|mM|%)\b")),
    ("citation", re.compile(r"\[[0-9][0-9,\-\s]*\]")),
    ("fig_eq", re.compile(
        r"\b(?:Fig|Figure|Eq|Eqs|Table|Scheme|Sec)s?\.?\s?\d+[a-z]?"
        r"(?:\s?[–\-]\s?\d+)?")),
    ("url", re.compile(r"https?://[^\s)\]]+")),
    ("doi", re.compile(r"\b10\.\d{4,9}/[^\s)\]]+")),
    ("number", re.compile(r"\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b")),
]


def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def protected_tokens(text):
    toks = []
    for cls, rx in PROTECTED_RES:
        for m in rx.finditer(text):
            toks.append("%s:%s" % (cls, m.group(0)))
    return sorted(toks)


def split_line_sentences(line, base):
    """Sentence spans (absolute offsets) inside one physical line."""
    spans = []
    start = 0
    for m in SENT_END_RE.finditer(line):
        w = TAIL_WORD_RE.search(line[:m.start()])
        word = w.group(1).rstrip(".").lower() if w else ""
        if word in NO_SPLIT_WORDS:
            continue
        end = m.start() + 1
        if line[start:end].strip():
            spans.append((base + start, base + end))
        start = end
        while start < len(line) and line[start] == " ":
            start += 1
    if start < len(line) and line[start:].strip():
        spans.append((base + start, base + len(line)))
    return spans


def cmd_prepare(args):
    text = open(args.source, "r", encoding="utf-8").read()
    units = []
    offset = 0
    section = "(prelude)"
    for raw_line in text.split("\n"):
        line = raw_line
        if HEAD_RE.match(line):
            section = line.strip().lstrip("#").strip()
            units.append({"start": offset, "end": offset + len(line),
                          "kind": "heading", "section": section,
                          "text": line})
        elif line.strip():
            for s, e in split_line_sentences(line, offset):
                units.append({"start": s, "end": e, "kind": "sentence",
                              "section": section, "text": text[s:e]})
        offset += len(line) + 1  # + the newline consumed by split
    for i, u in enumerate(units, 1):
        u2 = {"unit_id": "u%04d" % i}
        u2.update(u)
        u2["protected"] = protected_tokens(u["text"])
        units[i - 1] = u2
    out = {
        "tool": "pipeline.py prepare",
        "source": args.source,
        "source_sha256": sha256_text(text),
        "source_text": text,
        "units": units,
        "summary": {"unit_count": len(units)},
    }
    write_json(args.out, out)
    print("prepare: %d units -> %s" % (len(units), args.out))
    return 0


def cmd_apply_edits(args):
    doc = json.load(open(args.units, "r", encoding="utf-8"))
    edits = json.load(open(args.edits, "r", encoding="utf-8")).get("edits", [])
    unit_by_id = {u["unit_id"]: u for u in doc["units"]}
    current = {u["unit_id"]: u["text"] for u in doc["units"]}
    records = []

    for i, edit in enumerate(edits, 1):
        eid = edit.get("edit_id") or "e%04d" % i
        uid = edit.get("unit")
        rec = {
            "edit_id": eid,
            "unit": uid,
            "type": edit.get("type"),
            "reason": edit.get("reason"),
            "review": edit.get("review"),
            "status": None,
            "guard": None,
            "original": None,
            "new_text": edit.get("new_text"),
        }
        unit = unit_by_id.get(uid)
        review = edit.get("review") or {}
        if unit is None:
            rec["status"] = "reverted"
            rec["guard"] = "unknown_unit"
        elif review.get("decision") != "approve" or not (review.get("reason") or "").strip():
            rec["status"] = "reverted"
            rec["guard"] = "missing_or_negative_review"
            rec["original"] = current[uid]
        elif not (edit.get("reason") or "").strip():
            rec["status"] = "reverted"
            rec["guard"] = "missing_reason"
            rec["original"] = current[uid]
        elif not (edit.get("new_text") or "").strip():
            rec["status"] = "reverted"
            rec["guard"] = "empty_new_text"
            rec["original"] = current[uid]
        else:
            rec["original"] = current[uid]
            orig_counts = count_tokens(protected_tokens(current[uid]))
            new_counts = count_tokens(protected_tokens(edit["new_text"]))
            missing = sorted(t for t, n in orig_counts.items()
                             if new_counts.get(t, 0) < n)
            if missing:
                rec["status"] = "reverted"
                rec["guard"] = "protected_token_lost"
                rec["lost_tokens"] = missing
            elif edit["new_text"] == current[uid]:
                rec["status"] = "noop"
                rec["guard"] = "identical_text"
            else:
                current[uid] = edit["new_text"]
                rec["status"] = "applied"
                rec["guard"] = "passed"
        records.append(rec)

    summary = {
        "edits_submitted": len(records),
        "applied": sum(1 for r in records if r["status"] == "applied"),
        "reverted": sum(1 for r in records if r["status"] == "reverted"),
        "noop": sum(1 for r in records if r["status"] == "noop"),
    }
    out = {
        "tool": "pipeline.py apply-edits",
        "units_file": args.units,
        "edits_file": args.edits,
        "edits": records,
        "unit_texts": current,
        "summary": summary,
    }
    write_json(args.out, out)
    print("apply-edits: %d applied, %d reverted, %d noop -> %s"
          % (summary["applied"], summary["reverted"], summary["noop"], args.out))
    return 0


def count_tokens(tokens):
    d = {}
    for t in tokens:
        d[t] = d.get(t, 0) + 1
    return d


def reconstruct(source, units, unit_texts):
    out = []
    pos = 0
    for u in units:
        out.append(source[pos:u["start"]])
        out.append(unit_texts.get(u["unit_id"], u["text"]))
        pos = u["end"]
    out.append(source[pos:])
    return "".join(out)


def cmd_export(args):
    doc = json.load(open(args.units, "r", encoding="utf-8"))
    applied = json.load(open(args.applied, "r", encoding="utf-8"))
    label = args.label
    polished = reconstruct(doc["source_text"], doc["units"],
                           applied["unit_texts"])

    changes = {
        "tool": "pipeline.py export",
        "label": label,
        "changes": applied["edits"],
        "summary": applied["summary"],
    }
    n_protected = sum(len(u["protected"]) for u in doc["units"])
    audit = {
        "tool": "pipeline.py export",
        "label": label,
        "source_sha256": doc["source_sha256"],
        "polished_sha256": sha256_text(polished),
        "units_total": len(doc["units"]),
        "units_modified": sum(1 for u in doc["units"]
                              if applied["unit_texts"].get(u["unit_id"], u["text"]) != u["text"]),
        "edits_submitted": applied["summary"]["edits_submitted"],
        "edits_applied": applied["summary"]["applied"],
        "edits_reverted": applied["summary"]["reverted"],
        "reverted_missing_review": sum(
            1 for e in applied["edits"]
            if e["guard"] == "missing_or_negative_review"),
        "reverted_protected_token_lost": sum(
            1 for e in applied["edits"] if e["guard"] == "protected_token_lost"),
        "protected_tokens_checked": n_protected,
        "review_coverage": "edits without an approve+reason review record are "
                           "always reverted; see changes.json",
    }

    write_text(args.outdir + "/polished.md", polished)
    write_json(args.outdir + "/changes.json", changes)
    write_json(args.outdir + "/audit.json", audit)

    report = render_terminology_report(args, audit)
    if report is not None:
        write_text(args.outdir + "/terminology-report.md", report)
        print("export: polished.md, changes.json, audit.json, "
              "terminology-report.md -> %s" % args.outdir)
    else:
        print("export: polished.md, changes.json, audit.json -> %s "
              "(pass --lint/--termbase to also render terminology-report.md)"
              % args.outdir)
    return 0


def render_terminology_report(args, audit):
    if not args.lint or not args.termbase:
        return None
    lint = json.load(open(args.lint, "r", encoding="utf-8"))
    tb = json.load(open(args.termbase, "r", encoding="utf-8"))
    lines = []
    lines.append("# Terminology Governance Report")
    lines.append("")
    if args.label:
        lines.append("> %s" % args.label)
        lines.append("")
    s = lint["summary"]
    lines.append("- Source SHA-256: `%s`" % audit["source_sha256"])
    lines.append("- Polished SHA-256: `%s`" % audit["polished_sha256"])
    lines.append("- Termbase entries: %d | Conflicts: %d"
                 % (len(tb.get("entries", [])), len(tb.get("conflicts", []))))
    lines.append("- Full-text lint: **%d errors, %d warnings — gate %s**"
                 % (s["errors"], s["warnings"], s["gate"]))
    lines.append("")
    lines.append("## Locked termbase")
    lines.append("")
    lines.append("| id | canonical | abbrev | variants | banned | first-use policy | origin |")
    lines.append("|---|---|---|---|---|---|---|")
    for e in tb.get("entries", []):
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            e.get("id", ""), e.get("canonical", ""), e.get("abbrev") or "—",
            ", ".join(e.get("variants", [])) or "—",
            ", ".join(e.get("banned", [])) or "—",
            e.get("first_use_policy", ""), e.get("origin", "")))
    lines.append("")
    lines.append("## Conflicts")
    lines.append("")
    if tb.get("conflicts"):
        for c in tb["conflicts"]:
            lines.append("- **%s**: %s" % (c.get("type", "?"), c.get("detail", "")))
    else:
        lines.append("None. The locked termbase is internally consistent.")
    lines.append("")
    lines.append("## Full-text lint findings")
    lines.append("")
    if lint.get("findings"):
        lines.append("| id | severity | type | term | surface | location | message |")
        lines.append("|---|---|---|---|---|---|---|")
        for f in lint["findings"]:
            loc = f["locations"][0]
            lines.append("| %s | %s | %s | %s | %s | %s L%d | %s |" % (
                f["id"], f["severity"], f["type"], f["term_id"],
                f.get("surface") or "—",
                loc.get("section", "?"), loc.get("line", 0),
                f["message"].replace("|", "\\|")))
    else:
        lines.append("No findings. Every locked term is used in its registered "
                     "form, every abbreviation is defined at first use, and no "
                     "cross-section drift remains.")
    lines.append("")
    lines.append("## Notes and boundaries")
    lines.append("")
    lines.append("- The gate is mechanical: it proves the absence of *registered* "
                 "defects, not the absence of all terminology problems. Terms "
                 "absent from the termbase are not checked.")
    lines.append("- Candidate extraction and matching are heuristic (see "
                 "references/glossary-governance.md); borderline matches need "
                 "human confirmation.")
    lines.append("- Findings above are byte-position deterministic; re-running "
                 "on identical input reproduces them exactly.")
    lines.append("")
    return "\n".join(lines)


def write_text(path, s):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(s)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="pipeline.py",
        description="Freeze-apply-export pipeline for reviewed sentence edits.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="freeze source into sentence units")
    p.add_argument("--source", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_prepare)

    p = sub.add_parser("apply-edits", help="apply a reviewed edit batch")
    p.add_argument("--units", required=True)
    p.add_argument("--edits", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_apply_edits)

    p = sub.add_parser("export", help="rebuild polished text and deliverables")
    p.add_argument("--units", required=True)
    p.add_argument("--applied", required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--lint", default=None, help="term-lint JSON (optional)")
    p.add_argument("--termbase", default=None, help="locked termbase JSON (optional)")
    p.add_argument("--label", default="", help="label embedded into artifacts "
                   "(e.g. synthetic example marker)")
    p.set_defaults(fn=cmd_export)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
