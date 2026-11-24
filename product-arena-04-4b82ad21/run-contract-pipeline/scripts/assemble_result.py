#!/usr/bin/env python3
"""assemble_result.py -- assemble result.json from artefacts that ACTUALLY exist.

Fills the skeleton written by init_run.py (WORK/skeleton_result.json) with
real content only:

  case_id               copied verbatim from the input case.
  target_artifact       real path/format/sections/word_counts computed from
                        the actual draft Markdown file (words counted per
                        heading-delimited section, plus "total").
  facts_and_sources     the claims JSON array if --claims is given and the
                        file exists, else [].
  verification          the verification report JSON if --verification is
                        given and the file exists, else
                        {"checks": [], "summary": "not_run"}.
  version_and_boundary  changes/open_items/material_gaps read from
                        WORK/open_items.json if the agent created it
                        (accepts {"changes": [...], "open_items": [...],
                        "material_gaps": [...]} or a plain list treated as
                        open_items); else empty arrays. Its "status"
                        subfield mirrors the overall status.
  status                "complete" only if the draft exists and is non-empty
                        AND every top-level output_contract field is
                        populated (non-empty); otherwise "partial" with a
                        machine-readable "limits" list naming exactly what
                        is missing; "blocked" if no draft exists at all.

This script NEVER invents content to fill fields: anything not backed by a
real file stays an empty placeholder and is named in "limits".

Exit codes: 0 ok, 2 usage error. Pure Python 3 standard library.
"""

import argparse
import json
import os
import re
import sys

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def word_count(text):
    """Count words: whitespace-separated tokens containing a letter or digit."""
    return sum(1 for tok in text.split() if re.search(r"[A-Za-z0-9]", tok))


def analyse_markdown(path):
    """Return (sections, word_counts) for a Markdown draft.

    sections: list of heading texts in order of appearance.
    word_counts: {heading: words until the next heading, ..., "total": n}.
    Files without headings yield one section named "document".
    """
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    sections = []
    counts = {}
    current = None
    buf = []

    def flush():
        if current is not None:
            counts[current] = counts.get(current, 0) + word_count("\n".join(buf))

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            flush()
            current = m.group(2).strip()
            if current not in sections:
                sections.append(current)
            buf = []
        else:
            buf.append(line)
    flush()
    total = word_count("\n".join(lines))
    if not sections:
        sections = ["document"]
        counts = {"document": total}
    return sections, counts, total


def is_populated(value):
    """A contract field counts as populated if it carries any real content."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return any(is_populated(v) for v in value.values())
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="Assemble result.json from real artefacts.")
    ap.add_argument("--case", required=True, help="path to case.json")
    ap.add_argument("--work", required=True, help="working directory with skeleton_result.json")
    ap.add_argument("--output", required=True, help="output directory for result.json")
    ap.add_argument("--draft", default=None, help="path to the draft manuscript (Markdown)")
    ap.add_argument("--claims", default=None, help="path to claims/facts JSON (array)")
    ap.add_argument("--verification", default=None, help="path to verification report JSON")
    args = ap.parse_args(argv)

    try:
        case = load_json(args.case)
    except (OSError, json.JSONDecodeError) as exc:
        print("ERROR: cannot parse case.json: %s" % exc, file=sys.stderr)
        return 2
    skel_path = os.path.join(args.work, "skeleton_result.json")
    if not os.path.isfile(skel_path):
        print("ERROR: %s not found; run init_run.py first" % skel_path, file=sys.stderr)
        return 2
    skeleton = load_json(skel_path)

    limits = []

    # --- draft / target_artifact -------------------------------------------
    draft_ok = bool(args.draft) and os.path.isfile(args.draft) \
        and os.path.getsize(args.draft) > 0
    target = {"path": "", "format": "", "sections": [], "word_counts": {}}
    if args.draft and not draft_ok:
        limits.append("draft_missing_or_empty:%s" % args.draft)
    if not args.draft:
        limits.append("draft_not_provided")
    if draft_ok:
        sections, counts, _total = analyse_markdown(args.draft)
        target = {
            "path": os.path.abspath(args.draft),
            "format": "markdown",
            "sections": sections,
            "word_counts": dict(counts, **{}),
        }
        target["word_counts"]["total"] = _total

    # --- facts_and_sources --------------------------------------------------
    facts = []
    if args.claims and os.path.isfile(args.claims):
        try:
            facts = load_json(args.claims)
            if not isinstance(facts, list):
                facts = [facts]
        except json.JSONDecodeError as exc:
            limits.append("claims_unparseable:%s" % exc)
    else:
        limits.append("claims_missing")

    # --- verification --------------------------------------------------------
    if args.verification and os.path.isfile(args.verification):
        try:
            verification = load_json(args.verification)
        except json.JSONDecodeError as exc:
            verification = {"checks": [], "summary": "not_run"}
            limits.append("verification_unparseable:%s" % exc)
    else:
        verification = {"checks": [], "summary": "not_run"}

    # --- version_and_boundary -------------------------------------------------
    changes, open_items, gaps = [], [], []
    oi_path = os.path.join(args.work, "open_items.json")
    if os.path.isfile(oi_path):
        try:
            oi = load_json(oi_path)
            if isinstance(oi, list):
                open_items = oi
            elif isinstance(oi, dict):
                changes = oi.get("changes") or []
                open_items = oi.get("open_items") or []
                gaps = oi.get("material_gaps") or []
        except json.JSONDecodeError as exc:
            limits.append("open_items_unparseable:%s" % exc)

    # --- status ----------------------------------------------------------------
    result = dict(skeleton)
    result["case_id"] = case.get("case_id")
    if "target_artifact" in result:
        result["target_artifact"] = target
    if "facts_and_sources" in result:
        result["facts_and_sources"] = facts
    if "verification" in result:
        result["verification"] = verification
    vab = result.get("version_and_boundary")
    if isinstance(vab, dict):
        if "changes" in vab:
            vab["changes"] = changes
        if "open_items" in vab:
            vab["open_items"] = open_items
        if "material_gaps" in vab:
            vab["material_gaps"] = gaps

    contract_fields = list((case.get("output_contract") or {}).keys())
    if not draft_ok:
        status = "blocked"
        limits = ["no_draft"] + limits
    else:
        # Mirror a provisional status into version_and_boundary.status first:
        # it is real assembler-written content, so the boundary block then
        # counts as populated even when all three lists are honestly empty.
        vab = result.get("version_and_boundary")
        if isinstance(vab, dict) and "status" in vab:
            vab["status"] = "assembled"
        empty = [f for f in contract_fields if not is_populated(result.get(f))]
        if empty:
            status = "partial"
            limits = limits + ["field_empty:%s" % f for f in empty]
        else:
            status = "complete"

    if "status" in result:
        result["status"] = status
    vab = result.get("version_and_boundary")
    if isinstance(vab, dict) and "status" in vab:
        vab["status"] = status
    result["limits"] = limits

    os.makedirs(args.output, exist_ok=True)
    out_path = os.path.join(args.output, "result.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print("assemble_result: status=%s limits=%s" % (status, limits if limits else "[]"))
    print("  wrote %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
