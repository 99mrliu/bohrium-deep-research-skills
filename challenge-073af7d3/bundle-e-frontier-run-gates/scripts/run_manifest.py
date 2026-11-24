#!/usr/bin/env python3
"""run_manifest.py — deterministic run manifest for frontier-run-gates.

Maintains <work>/manifest.json:
  - inputs:   registered input files with sha256 + size (sorted by path)
  - stages:   named stages with status and artifact sha256s (ordered by seq)
  - commands: command log
  - case / pipeline: recorded by mini_pipeline for gate_check / replay_diff

Determinism rules: no wall-clock timestamps anywhere; a monotonically
increasing integer `seq` is used instead. All JSON written with sort_keys.

Usage:
  run_manifest.py --work DIR init [--input-dir DIR]
  run_manifest.py --work DIR add-input FILE
  run_manifest.py --work DIR stage NAME --status ok|fail|skipped|snapshot [--artifact FILE]...

Stdlib only. No network.
"""
import argparse
import hashlib
import json
import os
import sys

MANIFEST_NAME = "manifest.json"
STATUSES = ("ok", "fail", "skipped", "snapshot")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_path(work):
    return os.path.join(work, MANIFEST_NAME)


def load(work):
    p = manifest_path(work)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def save(work, manifest):
    os.makedirs(work, exist_ok=True)
    # keep stages deterministically ordered
    manifest["stages"].sort(key=lambda s: (s.get("seq", 0), s.get("name", "")))
    manifest["inputs"].sort(key=lambda e: e.get("path", ""))
    tmp = manifest_path(work) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, manifest_path(work))


def new_manifest():
    return {
        "version": 1,
        "seq": 0,
        "inputs": [],
        "stages": [],
        "commands": [],
        "case": None,
        "pipeline": None,
        "notes": [],
    }


def next_seq(manifest):
    manifest["seq"] = int(manifest.get("seq", 0)) + 1
    return manifest["seq"]


def log_command(manifest, argv):
    manifest["commands"].append({
        "seq": next_seq(manifest),
        "tool": os.path.basename(argv[0]) if argv else "unknown",
        "args": list(argv[1:]),
    })


def file_entry(path):
    ap = os.path.abspath(path)
    return {"path": ap, "sha256": sha256_file(ap), "size": os.path.getsize(ap)}


def add_input(manifest, path):
    entry = file_entry(path)
    for i, e in enumerate(manifest["inputs"]):
        if e["path"] == entry["path"]:
            manifest["inputs"][i] = entry
            break
    else:
        manifest["inputs"].append(entry)
    manifest["inputs"].sort(key=lambda e: e["path"])
    return entry


def set_stage(manifest, name, status, artifacts=None):
    arts = sorted(
        (file_entry(a) for a in (artifacts or []) if os.path.isfile(a)),
        key=lambda e: e["path"],
    )
    for i, s in enumerate(manifest["stages"]):
        if s["name"] == name:
            manifest["stages"][i] = {
                "name": name, "status": status,
                "seq": s.get("seq", 0), "artifacts": arts,
            }
            manifest["stages"].sort(key=lambda x: (x.get("seq", 0), x.get("name", "")))
            return
    manifest["stages"].append({
        "name": name, "status": status,
        "seq": next_seq(manifest), "artifacts": arts,
    })
    manifest["stages"].sort(key=lambda x: (x.get("seq", 0), x.get("name", "")))


def scan_dir(input_dir):
    files = []
    for root, dirs, names in os.walk(input_dir):
        dirs.sort()
        for n in sorted(names):
            p = os.path.join(root, n)
            if os.path.isfile(p) and not os.path.islink(p):
                files.append(p)
    return sorted(files)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic run manifest maintainer.")
    ap.add_argument("--work", required=True, help="work directory holding manifest.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="create a fresh manifest (optionally scanning an input dir)")
    p_init.add_argument("--input-dir", default=None)

    p_add = sub.add_parser("add-input", help="register one input file (sha256 + size)")
    p_add.add_argument("file")

    p_stage = sub.add_parser("stage", help="record a stage status and its artifact hashes")
    p_stage.add_argument("name")
    p_stage.add_argument("--status", required=True, choices=STATUSES)
    p_stage.add_argument("--artifact", action="append", default=[])

    args = ap.parse_args(argv)

    if args.cmd == "init":
        manifest = new_manifest()
        log_command(manifest, sys.argv)
        added = []
        if args.input_dir:
            if not os.path.isdir(args.input_dir):
                print(json.dumps({"error": "input_dir_not_found",
                                  "path": args.input_dir}, ensure_ascii=False))
                return 1
            for f in scan_dir(args.input_dir):
                add_input(manifest, f)
                added.append(os.path.abspath(f))
        save(args.work, manifest)
        print(json.dumps({"action": "init", "manifest": manifest_path(args.work),
                          "inputs_registered": len(added)},
                         ensure_ascii=False, sort_keys=True))
        return 0

    manifest = load(args.work)
    if manifest is None:
        print(json.dumps({"error": "manifest_missing",
                          "hint": "run `run_manifest.py --work DIR init` first"},
                         ensure_ascii=False))
        return 1

    log_command(manifest, sys.argv)

    if args.cmd == "add-input":
        if not os.path.isfile(args.file):
            print(json.dumps({"error": "input_file_not_found", "path": args.file},
                             ensure_ascii=False))
            return 1
        entry = add_input(manifest, args.file)
        save(args.work, manifest)
        print(json.dumps({"action": "add-input", "input": entry},
                         ensure_ascii=False, sort_keys=True))
        return 0

    if args.cmd == "stage":
        set_stage(manifest, args.name, args.status, args.artifact)
        save(args.work, manifest)
        print(json.dumps({"action": "stage", "name": args.name,
                          "status": args.status,
                          "artifacts": len([a for a in args.artifact if os.path.isfile(a)])},
                         ensure_ascii=False, sort_keys=True))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
