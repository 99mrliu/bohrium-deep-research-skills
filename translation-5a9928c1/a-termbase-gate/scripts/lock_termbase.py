#!/usr/bin/env python3
"""lock_termbase.py -- merge human/agent translations into a draft termbase and lock it.

Usage:
    python3 lock_termbase.py --draft termbase_draft.json --translations translations.json \
        --out termbase.locked.json [--allow-partial]

translations.json maps source_term -> {"target": "...", "forbidden_variants": [...]}
or a bare string ("..."), plus an optional top-level "_drop" list:
    {"_drop": [{"source_term": "...", "reason": "..."}], "Term A": "译法A", ...}

Exit 1 if any draft entry is uncovered (no target, not dropped), unless --allow-partial.
Stdlib only.
"""
import argparse
import hashlib
import json
import os
import sys


def canonical_sha(entries):
    blob = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="Lock a termbase draft with translations.")
    ap.add_argument("--draft", required=True)
    ap.add_argument("--translations", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--allow-partial", action="store_true",
                    help="exit 0 even with uncovered entries; mark status=partial")
    args = ap.parse_args()

    draft = load_json(args.draft)
    trans = load_json(args.translations)
    if not isinstance(trans, dict):
        sys.exit("ERROR: translations.json must be a JSON object mapping source_term -> target")

    dropped_spec = trans.get("_drop", [])
    dropped = []
    drop_keys = set()
    for d in dropped_spec:
        if isinstance(d, dict) and "source_term" in d:
            drop_keys.add(d["source_term"].lower())
            dropped.append({"source_term": d["source_term"], "reason": d.get("reason", "")})
        elif isinstance(d, str):
            drop_keys.add(d.lower())
            dropped.append({"source_term": d, "reason": ""})

    entries = []
    uncovered = []
    warnings = []
    seen_targets = {}

    for e in draft.get("entries", []):
        term = e["source_term"]
        key = term.lower()
        ent = dict(e)
        if key in drop_keys:
            ent["dropped"] = True
            entries.append(ent)
            continue
        spec = trans.get(term)
        if spec is None:
            # case-insensitive fallback lookup
            for k, v in trans.items():
                if k != "_drop" and k.lower() == key:
                    spec = v
                    break
        if spec is None:
            ent["target"] = None
            uncovered.append(term)
            entries.append(ent)
            continue
        if isinstance(spec, str):
            target, forbidden = spec, []
        elif isinstance(spec, dict):
            target = spec.get("target", "")
            forbidden = spec.get("forbidden_variants", []) or []
        else:
            sys.exit(f"ERROR: invalid translation spec for {term!r}: must be string or object")
        if not isinstance(target, str) or not target.strip():
            ent["target"] = None
            uncovered.append(term)
            entries.append(ent)
            continue
        target = target.strip()
        if target in (f.strip() for f in forbidden):
            sys.exit(f"ERROR: forbidden_variants of {term!r} must not equal its target {target!r}")
        ent["target"] = target
        ent["forbidden_variants"] = [f.strip() for f in forbidden if f.strip()]
        ent.pop("dropped", None)
        if target in seen_targets:
            warnings.append(f"duplicate target {target!r} for entries "
                            f"{seen_targets[target]!r} and {term!r} (allowed, but check)")
        else:
            seen_targets[target] = term
        entries.append(ent)

    locked = {
        "locked": True,
        "status": "partial" if uncovered else "locked",
        "source_files": draft.get("source_files", []),
        "entries": entries,
        "dropped": dropped,
        "uncovered": uncovered,
        "warnings": warnings,
        "termbase_sha256": canonical_sha(entries),
    }
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(locked, f, ensure_ascii=False, indent=2)
        f.write("\n")

    n_covered = sum(1 for e in entries if e.get("target"))
    print(f"lock_termbase: {len(entries)} entries, {n_covered} covered, "
          f"{len(dropped)} dropped, {len(uncovered)} uncovered")
    for w in warnings:
        print(f"  WARNING: {w}")
    for u in uncovered:
        print(f"  UNCOVERED: {u}")
    print(f"  termbase_sha256={locked['termbase_sha256'][:16]}...")
    print(f"wrote {args.out}")

    if uncovered and not args.allow_partial:
        print("ERROR: uncovered entries present (use --allow-partial to override)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
