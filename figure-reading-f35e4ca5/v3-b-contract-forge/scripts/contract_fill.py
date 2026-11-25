#!/usr/bin/env python3
"""contract_fill.py -- apply a JSON merge fragment onto the skeleton result,
with a logged merge mechanism.

Stdlib only. No network, no pip.

CLI:
  --skeleton PATH   skeleton/result JSON to update (required)
  --fragment PATH   merge fragment JSON (required)
  --work DIR        working directory; change_log.jsonl is appended here and
                    contract_plan.json (if present) is updated (required)
  --out PATH        write updated result here instead of in place (optional)

Fragment conventions:
  * Deep merge: dicts merge recursively; lists merge by index when lengths
    match, otherwise the fragment list replaces wholesale.
  * A top-level "_source" object maps path -> locator string; it is stripped
    before merging. A changed leaf looks up its own path first, then the
    longest matching ancestor path.
  * "case_id" is never changed: a differing value is refused (exit 2).

Exit codes: 0 clean, 2 warnings (e.g. refused case_id change), 1 fatal.
"""
import argparse
import json
import os
import re
import sys
import datetime

META_KEYS = {"case_id", "status", "sources", "uncertainty", "change_records"}
INDEX_RE = re.compile(r"\[\d+\]")


def join(path, key):
    if not path:
        return "/" + str(key)
    return path.rstrip("/") + "/" + str(key)


def lookup_source(srcmap, path):
    if path in srcmap:
        return srcmap[path]
    best = None
    for k in srcmap:
        if k and (path == k or path.startswith(k.rstrip("/") + "/") or
                  path.startswith(k.rstrip("/") + "[")):
            if best is None or len(k) > len(best):
                best = k
    return srcmap.get(best) if best else None


def merge(dst, src, path, changes):
    """Deep-merge src into dst, appending one change record per changed leaf."""
    if isinstance(src, dict) and isinstance(dst, dict):
        for k, v in src.items():
            dst[k] = merge(dst.get(k), v, join(path, k), changes)
        return dst
    if isinstance(src, list) and isinstance(dst, list) and len(src) == len(dst):
        return [merge(d, s, "%s[%d]" % (path or "/", i), changes)
                for i, (d, s) in enumerate(zip(dst, src))]
    # structural replacement: descend to record per-leaf changes
    if isinstance(src, dict):
        base = dst if isinstance(dst, dict) else {}
        out = {}
        for k, v in src.items():
            out[k] = merge(base.get(k), v, join(path, k), changes)
        return out
    if isinstance(src, list):
        out = []
        for i, s in enumerate(src):
            old = dst[i] if isinstance(dst, list) and i < len(dst) else None
            out.append(merge(old, s, "%s[%d]" % (path or "/", i), changes))
        return out
    if dst != src:
        changes.append({"path": path or "/", "old": dst, "new": src})
    return src


def count_fields(node, path="", top=True):
    """Return (total, non_null) leaf counts, excluding top-level meta keys."""
    total = 0
    non_null = 0
    if isinstance(node, dict):
        for k, v in node.items():
            if top and k in META_KEYS:
                continue
            t, n = count_fields(v, join(path, k), top=False)
            total += t
            non_null += n
    elif isinstance(node, list):
        if not node:
            total, non_null = 1, 1  # empty list is an explicit, filled value
        for i, v in enumerate(node):
            t, n = count_fields(v, "%s[%d]" % (path or "/", i), top=False)
            total += t
            non_null += n
    else:
        total = 1
        non_null = 1 if node is not None else 0
    return total, non_null


def update_plan(work, changes, srcmap):
    plan_path = os.path.join(work, "contract_plan.json")
    if not os.path.exists(plan_path):
        return 0
    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            plan_doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        return 0
    fields = plan_doc.get("fields", [])
    by_path = {e.get("path"): e for e in fields}
    updated = 0
    for ch in changes:
        generalized = INDEX_RE.sub("[]", ch["path"])
        entry = by_path.get(generalized)
        if entry is not None and ch["new"] is not None:
            if not entry.get("filled"):
                updated += 1
            entry["filled"] = True
            entry["fill_source"] = lookup_source(srcmap, generalized) or \
                lookup_source(srcmap, ch["path"])
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan_doc, f, ensure_ascii=False, indent=2)
    return updated


def main(argv=None):
    ap = argparse.ArgumentParser(description="Merge a fill fragment into the skeleton result with change logging.")
    ap.add_argument("--skeleton", required=True)
    ap.add_argument("--fragment", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    try:
        with open(args.skeleton, "r", encoding="utf-8") as f:
            skeleton = json.load(f)
        with open(args.fragment, "r", encoding="utf-8") as f:
            fragment = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"error": "cannot load input: %s" % e}))
        return 1
    if not isinstance(skeleton, dict) or not isinstance(fragment, dict):
        print(json.dumps({"error": "skeleton and fragment must be JSON objects"}))
        return 1

    os.makedirs(args.work, exist_ok=True)

    srcmap = fragment.get("_source") or {}
    if not isinstance(srcmap, dict):
        print(json.dumps({"error": "_source must be an object mapping path -> locator"}))
        return 1
    fragment = {k: v for k, v in fragment.items() if k != "_source"}

    refused = []
    if "case_id" in fragment:
        if fragment["case_id"] != skeleton.get("case_id"):
            refused.append("/case_id")
        fragment.pop("case_id")

    changes = []
    skeleton = merge(skeleton, fragment, "", changes)

    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    log_path = os.path.join(args.work, "change_log.jsonl")
    with open(log_path, "a", encoding="utf-8") as f:
        for ch in changes:
            rec = {
                "ts": ts,
                "path": ch["path"],
                "old": ch["old"],
                "new": ch["new"],
                "source": lookup_source(srcmap, ch["path"]),
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    plan_updated = update_plan(args.work, changes, srcmap)

    out_path = args.out or args.skeleton
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(skeleton, f, ensure_ascii=False, indent=2)

    total, non_null = count_fields(skeleton)
    summary = {
        "changed_leaves": len(changes),
        "fields_non_null": non_null,
        "fields_total": total,
        "plan_entries_updated": plan_updated,
        "refused": refused,
        "change_log": log_path,
        "result": out_path,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 2 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
