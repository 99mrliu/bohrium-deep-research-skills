#!/usr/bin/env python3
"""anchor_map.py — validate blocks.jsonl schema and assign stable anchor ids.

Input  : blocks.jsonl — one JSON object per line:
           id (str, required, unique)
           page (int >= 1, required)
           column (int >= 0, optional; tolerated missing -> 0)
           bbox ([x0, y0, x1, y1] floats in PDF points, required but may be null)
           kind (heading|body|caption|equation|reference|header|footer|unresolved)
           text (str or null; null only allowed for kind=unresolved)
           reason (optional str; expected for kind=unresolved)
Output : anchor_map.json — for every block a stable anchor id p{page}-b{seq}
         (seq is per-page in input order) plus page/bbox/kind/column/char_len.
         schema_errors are listed; any schema error -> exit 3.

Deterministic: no timestamps, no randomness. Python 3 stdlib only.
"""
import argparse
import json
import os
import sys

VALID_KINDS = [
    "heading", "body", "caption", "equation",
    "reference", "header", "footer", "unresolved",
]


def validate_block(obj, lineno):
    """Return list of error strings for one parsed block object."""
    errs = []
    if not isinstance(obj, dict):
        return ["line %d: not a JSON object" % lineno]
    bid = obj.get("id")
    if not isinstance(bid, str) or not bid.strip():
        errs.append("line %d: missing or empty 'id' (string required)" % lineno)
    page = obj.get("page")
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        errs.append("line %d: 'page' must be an integer >= 1 (got %r)"
                    % (lineno, page))
    col = obj.get("column", 0)
    if not isinstance(col, int) or isinstance(col, bool) or col < 0:
        errs.append("line %d: 'column' must be an integer >= 0 (got %r)"
                    % (lineno, col))
    bbox = obj.get("bbox", None)
    if bbox is not None:
        ok = (isinstance(bbox, list) and len(bbox) == 4
              and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                      for v in bbox))
        if not ok:
            errs.append("line %d: 'bbox' must be null or [x0,y0,x1,y1] numbers"
                        % lineno)
        elif not (bbox[0] <= bbox[2] and bbox[1] <= bbox[3]):
            errs.append("line %d: 'bbox' corners out of order %r"
                        % (lineno, bbox))
    else:
        if "bbox" not in obj:
            errs.append("line %d: missing 'bbox' key (use null if unknown)"
                        % lineno)
    kind = obj.get("kind")
    if kind not in VALID_KINDS:
        errs.append("line %d: 'kind' must be one of %s (got %r)"
                    % (lineno, "/".join(VALID_KINDS), kind))
    text = obj.get("text", None)
    if "text" not in obj:
        errs.append("line %d: missing 'text' key (use null if unparseable)"
                    % lineno)
    elif text is not None and not isinstance(text, str):
        errs.append("line %d: 'text' must be a string or null" % lineno)
    if kind == "unresolved" and text is None and not obj.get("reason"):
        errs.append("line %d: unresolved block with null text should give "
                    "a 'reason'" % lineno)
    if kind != "unresolved" and text is None:
        errs.append("line %d: kind=%r with null text is only allowed for "
                    "kind=unresolved" % (lineno, kind))
    return errs


def main():
    ap = argparse.ArgumentParser(
        description="Validate blocks.jsonl and emit anchor_map.json")
    ap.add_argument("--blocks", required=True, help="path to blocks.jsonl")
    ap.add_argument("--out", required=True, help="path for anchor_map.json")
    args = ap.parse_args()

    if not os.path.isfile(args.blocks):
        sys.stderr.write("error: blocks file not found: %s\n" % args.blocks)
        return 2
    raw = open(args.blocks, "rb").read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        sys.stderr.write("error: blocks.jsonl is not valid UTF-8: %s\n" % e)
        return 3

    blocks = []
    errors = []
    seen_ids = set()
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError as e:
            errors.append("line %d: invalid JSON: %s" % (i, e))
            continue
        errors.extend(validate_block(obj, i))
        bid = obj.get("id") if isinstance(obj, dict) else None
        if isinstance(bid, str) and bid in seen_ids:
            errors.append("line %d: duplicate block id %r" % (i, bid))
        if isinstance(bid, str):
            seen_ids.add(bid)
        blocks.append(obj)

    # Assign per-page sequence numbers in input order (stable anchors).
    seq_by_page = {}
    entries = []
    order = []
    for obj in blocks:
        page = obj.get("page")
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            continue  # anchor only well-paged blocks; error already recorded
        seq_by_page[page] = seq_by_page.get(page, 0) + 1
        anchor = "p%d-b%d" % (page, seq_by_page[page])
        t = obj.get("text")
        entries.append({
            "anchor": anchor,
            "block_id": obj.get("id"),
            "page": page,
            "column": obj.get("column", 0),
            "bbox": obj.get("bbox"),
            "kind": obj.get("kind"),
            "char_len": len(t) if isinstance(t, str) else 0,
            "text_null": t is None,
        })
        order.append(anchor)

    report = {
        "source_blocks": os.path.basename(args.blocks),
        "block_count": len(blocks),
        "anchor_count": len(entries),
        "schema_valid": not errors,
        "schema_errors": errors,
        "anchor_order": order,
        "anchors": entries,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")

    if errors:
        sys.stderr.write("schema INVALID: %d error(s)\n" % len(errors))
        for e in errors:
            sys.stderr.write("  - %s\n" % e)
        return 3
    sys.stdout.write("ok: %d blocks -> %d anchors -> %s\n"
                     % (len(blocks), len(entries), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
