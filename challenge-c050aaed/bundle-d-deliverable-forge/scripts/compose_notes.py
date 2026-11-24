#!/usr/bin/env python3
"""compose_notes.py -- validate typed note drafts and compose normalized notes.

Reads the agent's note drafts (drafts.jsonl) plus the extracted annotations
(annotations.jsonl), validates every draft against the rules documented in
references/note_schema.json, resolves each evidence item to a concrete source
locator (file, page, quote, annotation_id), computes the note<->annotation
correspondence both ways, and writes normalized notes to notes.jsonl.

Exit codes:
  0  all drafts valid; notes.jsonl written
  2  usage / IO error (missing files, malformed JSON, bad arguments)
  3  at least one invalid draft; offenders listed; notes.jsonl NOT written
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

TOOL_VERSION = "deliverable-forge 1.0.0"
NOTE_TYPES = ["problem", "method", "result", "reusable_point", "doubt"]
MIN_QUOTE_LEN = 8


def die(msg, code=2):
    print(f"compose_notes: ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def normalize_text(s):
    """Unicode NFKC + whitespace collapse (same rule as verify_claims.py)."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def load_jsonl(path, what):
    p = Path(path)
    if not p.is_file():
        die(f"{what} not found: {path}")
    records = []
    with p.open(encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                die(f"{what}:{lineno}: invalid JSON: {e}")
    return records


def load_annotations(path):
    anns = {}
    for rec in load_jsonl(path, "annotations file"):
        aid = rec.get("annotation_id")
        if not isinstance(aid, str) or not aid:
            die("annotations file: record without a non-empty 'annotation_id'")
        if aid in anns:
            die(f"annotations file: duplicate annotation_id '{aid}'")
        anns[aid] = rec
    return anns


def resolve_evidence(item, annotations, idx):
    """Return (locator_dict, error_or_None)."""
    if not isinstance(item, dict):
        return None, f"evidence[{idx}] is not an object"
    aid = item.get("annotation_id")
    if aid:
        ann = annotations.get(aid)
        if ann is None:
            return None, (f"evidence[{idx}]: annotation_id '{aid}' not found "
                          f"in annotations file")
        quote = ann.get("anchored_text") or ""
        if len(normalize_text(quote)) < MIN_QUOTE_LEN:
            return None, (f"evidence[{idx}]: annotation '{aid}' has no "
                          f"anchored_text of >= {MIN_QUOTE_LEN} chars")
        try:
            page = int(ann["page"])
        except (KeyError, TypeError, ValueError):
            return None, f"evidence[{idx}]: annotation '{aid}' has no valid page"
        if not ann.get("file"):
            return None, f"evidence[{idx}]: annotation '{aid}' has no file"
        return {"file": ann["file"], "page": page, "quote": quote,
                "annotation_id": aid}, None
    missing = [k for k in ("file", "page", "quote") if k not in item]
    if missing:
        return None, (f"evidence[{idx}]: direct locator missing "
                      f"{', '.join(missing)} (or provide annotation_id)")
    if not isinstance(item.get("file"), str) or not item["file"]:
        return None, f"evidence[{idx}]: 'file' must be a non-empty string"
    try:
        page = int(item["page"])
    except (TypeError, ValueError):
        return None, f"evidence[{idx}]: 'page' is not an integer"
    quote = item.get("quote")
    if not isinstance(quote, str) or len(normalize_text(quote)) < MIN_QUOTE_LEN:
        return None, (f"evidence[{idx}]: 'quote' shorter than {MIN_QUOTE_LEN} "
                      f"chars after normalization")
    return {"file": item["file"], "page": page, "quote": quote,
            "annotation_id": None}, None


def validate_draft(draft, idx, annotations, seen_ids, sources_dir):
    """Return (errors, warnings, normalized_evidence, tags)."""
    errs, warns = [], []
    label = draft.get("note_id") if isinstance(draft, dict) else None
    if not isinstance(draft, dict):
        return [f"draft#{idx}: not a JSON object"], [], [], []
    if not isinstance(label, str) or not label.strip():
        errs.append("note_id missing or empty")
        label = f"draft#{idx}"
    elif label in seen_ids:
        errs.append(f"duplicate note_id '{label}'")
    ntype = draft.get("note_type")
    if ntype not in NOTE_TYPES:
        errs.append(f"note_type '{ntype}' not in {NOTE_TYPES}")
    claim = draft.get("claim")
    if not isinstance(claim, str) or not claim.strip():
        errs.append("claim missing or empty")
    tags = draft.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        errs.append("tags must be a list of strings")
        tags = []
    evidence = draft.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errs.append("evidence must be a non-empty list")
        evidence = []
    locators = []
    for i, item in enumerate(evidence):
        loc, err = resolve_evidence(item, annotations, i)
        if err:
            errs.append(err)
        else:
            locators.append(loc)
    # excerpt_only: claim identical to a quote -> the note is a pure excerpt
    if isinstance(claim, str):
        nc = normalize_text(claim)
        for loc in locators:
            if nc and nc == normalize_text(loc["quote"]):
                warns.append("excerpt_only: claim is identical to its quote; "
                             "rewrite the claim in your own words")
                break
    # soft check against sources dir (hard check happens in verify_claims.py)
    if sources_dir is not None:
        for loc in locators:
            if not (Path(sources_dir) / loc["file"]).is_dir():
                warns.append(f"source_dir_missing: no sources/{loc['file']}/ "
                             f"directory yet")
    return errs, warns, locators, tags, label


def main():
    ap = argparse.ArgumentParser(
        description="Validate typed note drafts and compose normalized notes.")
    ap.add_argument("--annotations", required=True,
                    help="annotations.jsonl from any extractor")
    ap.add_argument("--sources-dir", required=True,
                    help="directory with sources/<filekey>/page-NNN.txt")
    ap.add_argument("--drafts", required=True,
                    help="agent-authored typed note drafts (JSONL)")
    ap.add_argument("--out", required=True, help="output notes.jsonl path")
    args = ap.parse_args()

    annotations = load_annotations(args.annotations)
    drafts = load_jsonl(args.drafts, "drafts file")
    if not Path(args.sources_dir).is_dir():
        die(f"sources dir not found: {args.sources_dir}")

    valid, invalid, seen_ids = [], [], set()
    for idx, draft in enumerate(drafts, 1):
        errs, warns, locators, tags, label = validate_draft(
            draft, idx, annotations, seen_ids, args.sources_dir)
        if errs:
            invalid.append((label, errs))
            continue
        seen_ids.add(label)
        valid.append({
            "note_id": label,
            "note_type": draft["note_type"],
            "claim": draft["claim"].strip(),
            "tags": tags,
            "evidence": locators,
            "annotation_ids": sorted({l["annotation_id"] for l in locators
                                      if l["annotation_id"]}),
            "warnings": sorted(set(warns)),
            "tool": TOOL_VERSION,
        })

    counts = {t: 0 for t in NOTE_TYPES}
    for n in valid:
        counts[n["note_type"]] += 1
    print(f"compose_notes {TOOL_VERSION}")
    print(f"drafts: {len(drafts)}  valid: {len(valid)}  "
          f"invalid: {len(invalid)}")
    print("notes per type: " + " ".join(f"{t}={counts[t]}"
                                        for t in NOTE_TYPES))
    if invalid:
        for label, errs in invalid:
            for e in errs:
                print(f"INVALID {label}: {e}", file=sys.stderr)
        print("notes.jsonl NOT written: fix the invalid drafts above.")
        sys.exit(3)

    n_ev = sum(len(n["evidence"]) for n in valid)
    n_direct = sum(1 for n in valid for l in n["evidence"]
                   if not l["annotation_id"])
    referenced = {a for n in valid for a in n["annotation_ids"]}
    print(f"evidence items: {n_ev} (annotation-linked: {n_ev - n_direct}, "
          f"direct: {n_direct})")
    print(f"annotations referenced: {len(referenced)} / {len(annotations)}")
    # correspondence the other way: annotation -> notes
    ann_to_notes = {}
    for n in valid:
        for a in n["annotation_ids"]:
            ann_to_notes.setdefault(a, []).append(n["note_id"])
    print("annotation -> notes:")
    for a in sorted(ann_to_notes):
        print(f"  {a} -> {', '.join(ann_to_notes[a])}")
    for a in sorted(set(annotations) - referenced):
        print(f"  {a} -> (unreferenced)")
    all_warns = [(n["note_id"], w) for n in valid for w in n["warnings"]]
    print(f"warnings: {len(all_warns)}")
    for nid, w in all_warns:
        print(f"  WARNING {nid}: {w}")

    out = Path(args.out)
    with out.open("w", encoding="utf-8") as f:
        for n in valid:
            f.write(json.dumps(n, ensure_ascii=False, sort_keys=False) + "\n")
    print(f"wrote: {out} ({len(valid)} notes)")
    sys.exit(0)


if __name__ == "__main__":
    main()
