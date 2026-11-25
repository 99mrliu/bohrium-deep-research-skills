#!/usr/bin/env python3
"""apply_repairs.py — apply the model's targeted repairs to the draft (stage 3).

The model reads repair_queue.json and writes a small repairs file containing
patches ONLY for queued item ids:

    {"repairs": [
        {"id": "n007", "patch": {"evidence": {"source_id": "...", "paragraph_id": "...", "quote": "..."}}},
        {"id": "e012", "drop": true, "drop_reason": "cannot ground this edge in the text"}
    ]}

Patch semantics: top-level fields of "patch" replace the item's fields
(replace "evidence" wholesale when fixing quotes/addresses). "drop": true
withdraws the item (it will not be re-audited nor enter the graph; the
withdrawal is recorded). Repair ids NOT present in repair_queue.json are
refused (the loop is targeted: accepted items must not be touched).

Usage:
    python3 apply_repairs.py --work /app/work \
        --base /app/work/extraction.draft.json \
        --repairs /app/work/repairs.json \
        --out /app/work/extraction.repaired.json

Python 3.9+, standard library only. Deterministic output.
"""
import argparse
import json
import os
import sys


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def main():
    ap = argparse.ArgumentParser(description="Apply targeted repair patches to an extraction draft")
    ap.add_argument("--work", required=True)
    ap.add_argument("--base", required=True, help="draft the repairs apply to (e.g. extraction.draft.json)")
    ap.add_argument("--repairs", required=True, help="repairs JSON written by the model (or simulator)")
    ap.add_argument("--out", required=True, help="output repaired draft path")
    args = ap.parse_args()

    base = load_json(args.base)
    repairs_doc = load_json(args.repairs)
    repairs = repairs_doc.get("repairs") if isinstance(repairs_doc, dict) else None
    if not isinstance(repairs, list):
        print("ERROR: repairs file has no 'repairs' list", file=sys.stderr)
        return 2

    queue_path = os.path.join(args.work, "repair_queue.json")
    queue_ids = set()
    if os.path.isfile(queue_path):
        queue = load_json(queue_path)
        queue_ids = {str(q.get("id")) for q in queue.get("items") or []}

    items = base.get("items") or []
    by_id = {str(it.get("id")): it for it in items if isinstance(it, dict) and it.get("id")}

    applied, dropped, refused, unknown = [], [], [], []
    for rep in repairs:
        if not isinstance(rep, dict):
            continue
        rid = str(rep.get("id") or "")
        if queue_ids and rid not in queue_ids:
            refused.append(rid)
            continue
        if rid not in by_id:
            unknown.append(rid)
            continue
        if rep.get("drop"):
            by_id[rid]["_dropped"] = True
            by_id[rid]["_drop_reason"] = str(rep.get("drop_reason") or "withdrawn during repair")
            dropped.append(rid)
            continue
        patch = rep.get("patch")
        if not isinstance(patch, dict):
            refused.append(rid)
            continue
        for key in sorted(patch.keys()):
            by_id[rid][key] = patch[key]
        applied.append(rid)

    remaining = [it for it in items if not (isinstance(it, dict) and it.get("_dropped"))]
    out_doc = dict(base)
    out_doc["items"] = remaining
    out_doc["repair_log"] = {
        "base_file": os.path.basename(args.base),
        "applied": sorted(applied),
        "dropped": sorted(dropped),
        "refused_not_in_queue": sorted(refused),
        "unknown_ids": sorted(unknown),
    }
    # keep a readable record of drop reasons
    out_doc["drop_log"] = sorted(
        [{"id": rid, "reason": by_id[rid].get("_drop_reason")} for rid in dropped],
        key=lambda r: r["id"])

    dump_json(out_doc, args.out)
    print("apply_repairs: applied=%d dropped=%d refused=%d unknown=%d -> %s" %
          (len(applied), len(dropped), len(refused), len(unknown), args.out))
    if refused:
        print("apply_repairs WARNING: refused ids not in repair_queue: %s" % ", ".join(sorted(refused)))
    if unknown:
        print("apply_repairs WARNING: unknown ids: %s" % ", ".join(sorted(unknown)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
