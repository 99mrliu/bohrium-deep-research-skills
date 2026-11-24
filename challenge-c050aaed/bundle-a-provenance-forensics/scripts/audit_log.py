#!/usr/bin/env python3
"""Append-only, hash-chained JSONL operation audit log.

Each entry is one JSON object per line:
  {"seq": N, "op": "...", "details": {...},
   "prev_sha256": "...", "entry_sha256": "..."}

entry_sha256 = sha256 of the canonical JSON (sorted keys, compact
separators, UTF-8) of the entry WITHOUT the entry_sha256 field.
prev_sha256 links to the previous entry's entry_sha256; the first entry
links to a genesis constant of 64 zeroes.

No wall-clock time is used: ordering is by seq numbers only, so logs are
deterministic and replayable.

Subcommands:
  append --log LOG --op OP [--detail k=v ...]
  verify --log LOG

Exit codes: 0 success, 2 usage error, 3 verification failure (chain break).
Python 3 standard library only.
"""

import argparse
import hashlib
import json
import os
import sys

GENESIS = "0" * 64


def canonical_bytes(obj):
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def entry_hash(entry):
    stripped = {k: v for k, v in entry.items() if k != "entry_sha256"}
    return hashlib.sha256(canonical_bytes(stripped)).hexdigest()


def read_log(path):
    """Return (entries, parse_error). parse_error is None on success."""
    entries = []
    if not os.path.exists(path):
        return entries, None
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                return entries, "line %d: invalid JSON: %s" % (lineno, e)
    return entries, None


def cmd_append(args):
    details = {}
    for kv in args.detail or []:
        if "=" not in kv:
            print("error: --detail must be k=v, got: %r" % kv,
                  file=sys.stderr)
            return 2
        k, v = kv.split("=", 1)
        details[k] = v

    entries, err = read_log(args.log)
    if err is not None:
        print("error: existing log is corrupt; refusing to append: %s" % err,
              file=sys.stderr)
        return 3

    seq = entries[-1]["seq"] + 1 if entries else 1
    prev = entries[-1]["entry_sha256"] if entries else GENESIS
    entry = {
        "seq": seq,
        "op": args.op,
        "details": details,
        "prev_sha256": prev,
    }
    entry["entry_sha256"] = entry_hash(entry)

    log_dir = os.path.dirname(os.path.abspath(args.log))
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    with open(args.log, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(json.dumps(entry, ensure_ascii=False))
    return 0


def cmd_verify(args):
    entries, err = read_log(args.log)
    problems = []
    if err is not None:
        problems.append(err)
    for i, e in enumerate(entries):
        label = "entry %d (line %d)" % (e.get("seq", i + 1), i + 1)
        for field in ("seq", "op", "details", "prev_sha256", "entry_sha256"):
            if field not in e:
                problems.append("%s: missing field %r" % (label, field))
        if "seq" in e and e["seq"] != i + 1:
            problems.append(
                "%s: expected seq %d, got %r" % (label, i + 1, e["seq"]))
        expected_prev = entries[i - 1]["entry_sha256"] if i > 0 else GENESIS
        if e.get("prev_sha256") != expected_prev:
            problems.append(
                "%s: prev_sha256 mismatch (expected %s, got %s)" % (
                    label, expected_prev[:16] + "...",
                    str(e.get("prev_sha256"))[:16] + "..."))
        if "entry_sha256" in e and entry_hash(e) != e["entry_sha256"]:
            problems.append("%s: entry_sha256 re-computation mismatch" % label)

    if problems:
        print("VERIFY FAILED: %d problem(s) in %s" % (len(problems), args.log),
              file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        return 3
    print("VERIFY OK: %d entr%s, chain intact (%s)" % (
        len(entries), "y" if len(entries) == 1 else "ies", args.log))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Append-only hash-chained JSONL audit log "
                    "(deterministic, seq-numbered, no wall-clock time)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_append = sub.add_parser("append", help="Append one operation entry.")
    p_append.add_argument("--log", required=True, help="JSONL log path.")
    p_append.add_argument("--op", required=True,
                          help="Operation name, e.g. inventory, classify, "
                               "recovery, skip.")
    p_append.add_argument("--detail", action="append", default=[],
                          metavar="k=v",
                          help="Detail key=value pair; repeatable.")
    p_append.set_defaults(func=cmd_append)

    p_verify = sub.add_parser("verify",
                              help="Re-check the whole hash chain.")
    p_verify.add_argument("--log", required=True, help="JSONL log path.")
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
