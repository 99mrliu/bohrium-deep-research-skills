#!/usr/bin/env python3
"""Replay check: re-run the forensic inventory on a directory and diff it
against a previously saved manifest.

Reports:
  added            - paths present now but not in the manifest
  removed          - paths in the manifest but missing now
  changed          - same path, different sha256
  renamed_suspect  - removed path whose sha256 reappears at an added path

This is the "others can re-run and verify" (他人可复跑核对) mechanism:
any silent modification of the input materials shows up here.

Exit codes: 0 no difference, 2 usage error, 3 differences found or
verification failure. Python 3 standard library only.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import forensic_inventory  # noqa: E402

TOOL_VERSION = "1.0.0"
GENERATED_BY = "provenance-forensics/scripts/replay_check.py"


def load_manifest(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "files" not in data:
        raise ValueError("manifest missing 'files' list")
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Re-run the forensic inventory on a directory and diff "
                    "against a saved manifest; exit 3 on any difference."
    )
    parser.add_argument("--manifest", required=True,
                        help="Previously saved inventory manifest (JSON).")
    parser.add_argument("--dir", required=True,
                        help="Materials directory to re-inventory.")
    parser.add_argument("--out", required=True,
                        help="Path to write the JSON diff report.")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.dir):
        print("error: not a directory: %s" % args.dir, file=sys.stderr)
        return 2
    try:
        saved = load_manifest(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print("error: cannot load manifest %s: %s" % (args.manifest, e),
              file=sys.stderr)
        return 3

    fresh = forensic_inventory.build_inventory(args.dir, out_path=args.out)

    old = {f["relpath"]: f["sha256"] for f in saved["files"]}
    new = {f["relpath"]: f["sha256"] for f in fresh["files"]}

    added = sorted(p for p in new if p not in old)
    removed = sorted(p for p in old if p not in new)
    changed = sorted(
        p for p in old if p in new and old[p] != new[p]
    )

    added_by_hash = {}
    for p in added:
        added_by_hash.setdefault(new[p], []).append(p)
    renamed_suspects = []
    for p in removed:
        h = old[p]
        if h in added_by_hash:
            for np_ in sorted(added_by_hash[h]):
                renamed_suspects.append({
                    "from": p, "to": np_, "sha256": h,
                })
    renamed_suspects.sort(key=lambda r: (r["from"], r["to"]))

    clean = not (added or removed or changed or renamed_suspects)
    report = {
        "generated_by": GENERATED_BY,
        "tool_version": TOOL_VERSION,
        "manifest": os.path.abspath(args.manifest),
        "dir": os.path.abspath(args.dir),
        "clean": clean,
        "added": added,
        "removed": removed,
        "changed": changed,
        "renamed_suspects": renamed_suspects,
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "renamed_suspects": len(renamed_suspects),
        },
    }

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    s = report["summary"]
    status = "CLEAN" if clean else "DIFFERENCES FOUND"
    print("replay_check: %s (added=%d removed=%d changed=%d "
          "renamed_suspects=%d) report=%s" % (
              status, s["added"], s["removed"], s["changed"],
              s["renamed_suspects"], args.out))
    return 0 if clean else 3


if __name__ == "__main__":
    sys.exit(main())
