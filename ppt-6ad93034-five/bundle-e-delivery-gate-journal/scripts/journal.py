#!/usr/bin/env python3
"""journal.py — append-only, hash-chained run journal (work/journal.jsonl).

Every entry carries sha256(canonical_json(entry_without_hash)) and links to the
previous entry's hash, so edits, deletions or re-ordering of history are
detectable with `journal.py verify`. Pure stdlib. No network.

Usage:
  journal.py init
  journal.py log --kind KIND [--cmd "..."] [--inputs f1 f2 ...] \
                 [--outputs o1 o2 ...] [--note "..."]
  journal.py verify

Directories come from env vars CASE_INPUT_DIR / CASE_WORK_DIR /
CASE_OUTPUT_DIR (defaults /input, /app/work, /app/output).
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys

INPUT_DIR = os.environ.get("CASE_INPUT_DIR", "/input")
WORK_DIR = os.environ.get("CASE_WORK_DIR", "/app/work")
JOURNAL_PATH = os.path.join(WORK_DIR, "journal.jsonl")


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def entry_hash(entry):
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def read_entries():
    entries = []
    if not os.path.exists(JOURNAL_PATH):
        return entries
    with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def append_entry(entry):
    os.makedirs(WORK_DIR, exist_ok=True)
    entry["hash"] = entry_hash(entry)
    with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
        f.write(canonical(entry) + "\n")
    return entry


def tool_version(name):
    """Version string for an external tool, or None if unavailable."""
    if name == "python3":
        return "python " + sys.version.split()[0]
    exe = shutil.which(name)
    if not exe:
        return None
    candidates = []
    for flag in ("-v", "--version"):
        try:
            p = subprocess.run([exe, flag], capture_output=True, text=True, timeout=15)
            for line in (p.stdout + "\n" + p.stderr).strip().splitlines():
                if line.strip():
                    candidates.append(line.strip())
        except Exception:
            continue
    for line in candidates:
        low = line.lower()
        if "error" in low or "couldn't open" in low or "usage" in low:
            continue
        if "version" in low or any(ch.isdigit() for ch in line):
            return line
    return "present (version unknown)"


def hash_files(paths, base=None, warn=True):
    """Hash each listed file's CURRENT bytes. Missing file -> None (+ warning)."""
    result = {}
    for p in paths or []:
        full = p if os.path.isabs(p) else os.path.join(base or os.getcwd(), p)
        if os.path.isfile(full):
            result[p] = sha256_file(full)
        else:
            result[p] = None
            if warn:
                print(f"journal: WARNING missing file recorded as null: {p}", file=sys.stderr)
    return result


def cmd_init(_args):
    if os.path.exists(JOURNAL_PATH):
        print(f"journal: ERROR journal already exists at {JOURNAL_PATH} (append-only; refusing to re-init)", file=sys.stderr)
        return 1
    inputs = {}
    if os.path.isdir(INPUT_DIR):
        for root, _dirs, files in os.walk(INPUT_DIR):
            for name in sorted(files):
                full = os.path.join(root, name)
                rel = os.path.relpath(full, INPUT_DIR)
                inputs[rel] = sha256_file(full)
    tools = {t: tool_version(t) for t in ("pdftotext", "pdftoppm", "soffice", "python3")}
    entry = {
        "seq": 0,
        "kind": "init",
        "ts_utc": utc_now(),
        "inputs": inputs,
        "tools": tools,
        "prev_hash": None,
    }
    append_entry(entry)
    print(f"journal: init entry 0 written ({len(inputs)} input files hashed, tools recorded)")
    return 0


def cmd_log(args):
    entries = read_entries()
    if not entries:
        print("journal: ERROR no journal found; run `journal.py init` first", file=sys.stderr)
        return 1
    prev = entries[-1]
    entry = {
        "seq": prev["seq"] + 1,
        "kind": args.kind,
        "ts_utc": utc_now(),
        "prev_hash": prev["hash"],
    }
    if args.cmd:
        entry["cmd"] = args.cmd
    if args.note:
        entry["note"] = args.note
    entry["inputs"] = hash_files(args.inputs)
    entry["outputs"] = hash_files(args.outputs)
    append_entry(entry)
    print(f"journal: entry {entry['seq']} ({args.kind}) appended, hash {entry['hash'][:12]}...")
    return 0


def cmd_verify(_args):
    entries = read_entries()
    if not entries:
        print("journal: ERROR journal is empty or missing", file=sys.stderr)
        return 1
    any_tampered = False
    prev_hash = None
    for e in entries:
        seq = e.get("seq")
        problems = []
        # 1) recompute entry hash
        if entry_hash(e) != e.get("hash"):
            problems.append("entry-hash-mismatch")
        # 2) chain linkage
        if e.get("prev_hash") != prev_hash:
            problems.append("prev_hash-link-broken")
        # 3) re-hash files where they still exist
        file_status = "ok"
        for group in ("inputs", "outputs"):
            for path, recorded in (e.get(group) or {}).items():
                if recorded is None:
                    continue  # was already missing at log time
                if e.get("kind") == "init":
                    full = os.path.join(INPUT_DIR, path)
                else:
                    full = path if os.path.isabs(path) else os.path.join(os.getcwd(), path)
                if not os.path.isfile(full):
                    file_status = "missing"
                    problems.append(f"file-missing:{path}")
                elif sha256_file(full) != recorded:
                    file_status = "tampered"
                    problems.append(f"file-tampered:{path}")
        if "entry-hash-mismatch" in problems or "prev_hash-link-broken" in problems:
            file_status = "tampered"
        if file_status == "tampered":
            any_tampered = True
        status = "ok" if not problems else file_status
        print(f"entry seq={seq} kind={e.get('kind')}: {status}"
              + ("" if not problems else " :: " + "; ".join(problems)))
        prev_hash = e.get("hash")
    if any_tampered:
        print("journal: VERIFY FAILED — tampering detected", file=sys.stderr)
        return 1
    print(f"journal: VERIFY OK — {len(entries)} entries, chain intact")
    return 0


def main():
    ap = argparse.ArgumentParser(description="append-only hash-chained run journal")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create journal with entry 0 (input hashes + tool versions)")
    lp = sub.add_parser("log", help="append an entry")
    lp.add_argument("--kind", required=True, help="entry kind, e.g. command, gate, note")
    lp.add_argument("--cmd", default=None)
    lp.add_argument("--inputs", nargs="*", default=[])
    lp.add_argument("--outputs", nargs="*", default=[])
    lp.add_argument("--note", default=None)
    sub.add_parser("verify", help="re-walk the chain and re-hash files")
    args = ap.parse_args()
    return {"init": cmd_init, "log": cmd_log, "verify": cmd_verify}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
