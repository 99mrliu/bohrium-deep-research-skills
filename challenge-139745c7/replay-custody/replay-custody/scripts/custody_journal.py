#!/usr/bin/env python3
"""Append-only hash-chained operation journal.

Subcommands:
  init  WORK_DIR                      create journal with genesis record
  log   WORK_DIR OP DETAIL [FILE]     append a record (FILE -> sha256 stored)
  seal  WORK_DIR OUT_REPLAY_MD        verify chain, write REPLAY.md

Every record: {seq, ts, op, detail, artifact_sha256, prev_hash, hash} where
hash = sha256(canonical JSON of the record without the hash field). Tampering
with any earlier record breaks the chain and `seal` reports it.
"""
import hashlib
import json
import os
import sys
import time

JOURNAL = "journal.jsonl"


def record_hash(rec):
    body = {k: v for k, v in rec.items() if k != "hash"}
    blob = json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def read_chain(path):
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def append(work, op, detail, artifact=None):
    path = os.path.join(work, JOURNAL)
    chain = read_chain(path)
    prev = chain[-1]["hash"] if chain else "GENESIS"
    rec = {"seq": len(chain), "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "op": op, "detail": detail, "artifact_sha256": None,
           "prev_hash": prev}
    if artifact and os.path.isfile(artifact):
        h = hashlib.sha256()
        with open(artifact, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        rec["artifact_sha256"] = h.hexdigest()
    rec["hash"] = record_hash(rec)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def verify(chain):
    prev = "GENESIS"
    for rec in chain:
        if rec["prev_hash"] != prev:
            return False, "chain broken at seq %d (prev_hash)" % rec["seq"]
        if rec["hash"] != record_hash(rec):
            return False, "record %d tampered (hash mismatch)" % rec["seq"]
        prev = rec["hash"]
    return True, "%d records verified" % len(chain)


def main():
    cmd = sys.argv[1]
    work = sys.argv[2]
    if cmd == "init":
        os.makedirs(work, exist_ok=True)
        path = os.path.join(work, JOURNAL)
        if os.path.exists(path):
            print(json.dumps({"error": "journal exists; refusing to reset"}))
            sys.exit(1)
        append(work, "init", "custody chain created")
        print(json.dumps({"journal": path}))
    elif cmd == "log":
        op, detail = sys.argv[3], sys.argv[4]
        artifact = sys.argv[5] if len(sys.argv) > 5 else None
        rec = append(work, op, detail, artifact)
        print(json.dumps({"seq": rec["seq"], "hash": rec["hash"][:16]}))
    elif cmd == "seal":
        chain = read_chain(os.path.join(work, JOURNAL))
        ok, msg = verify(chain)
        rec = append(work, "seal", "chain sealed: " + msg)
        out_p = sys.argv[3]
        lines = ["# REPLAY：第三方复核说明（replay-custody）", "",
                 "保管链校验：%s（seal hash %s）" % (msg, rec["hash"][:16]), "",
                 "## 重放步骤", "",
                 "1. 取得同一文档库与 `/input/case.json`。",
                 "2. 依序执行保管链中记录的命令（下表）。",
                 "3. 对任一结论：按证据卡 `file` + `char_start`/`char_end` 定位"
                 "原文，逐字比对 `quote`；或重跑 "
                 "`python3 scripts/custody_gate.py <work> out.json` 自动核验。",
                 "4. 用 `python3 scripts/custody_journal.py seal <work> out.md`"
                 " 复验保管链完整性。", "",
                 "## 操作记录", "",
                 "| seq | 操作 | 详情 | 产物sha256(前16) |", "|---|---|---|---|"]
        for r in chain:
            lines.append("| %d | %s | %s | %s |" % (
                r["seq"], r["op"], str(r["detail"])[:80].replace("|", "/"),
                (r.get("artifact_sha256") or "-")[:16]))
        os.makedirs(os.path.dirname(out_p) or ".", exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(json.dumps({"chain_ok": ok, "msg": msg}))
        sys.exit(0 if ok else 2)
    else:
        print("unknown subcommand", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
