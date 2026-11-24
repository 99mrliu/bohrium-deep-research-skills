#!/usr/bin/env python3
"""oplog.py — 过程质量控制：哈希链操作日志（append-only，确定性，stdlib-only）。

用法：
  oplog.py init   --work W                        初始化日志
  oplog.py append --work W --op OP [--detail JSON] [--file PATH ...]
      追加一条操作记录；自动携带序号、UTC 时间戳、前一条记录哈希（链式），
      --file 参数的文件会被计算 SHA-256 一并记录（操作对象的版本坐标）。
  oplog.py seal   --work W                        封口：写入总结记录，之后仍可
      追加但 seal 之后追加会在审计时标记为 post_seal。

操作类型建议：scan / read / search / skip / decide / verify / write / error。
日志是"换一个评审能否重走一遍"的证据底座；只允许追加，不提供修改命令。
退出码恒 0（append 在日志损坏时返回 2 并拒绝写入）。
"""
import argparse
import hashlib
import json
import os
import sys
import time

JOURNAL = "journal.jsonl"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_journal(work):
    p = os.path.join(work, JOURNAL)
    entries = []
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    return entries


def chain_ok(entries):
    prev = "GENESIS"
    for e in entries:
        if e.get("prev") != prev:
            return False
        prev = hashlib.sha256(json.dumps(
            e, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["init", "append", "seal"])
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--op", default=None)
    ap.add_argument("--detail", default="{}")
    ap.add_argument("--file", action="append", default=[])
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    entries = read_journal(a.work)

    if a.cmd == "init":
        if entries:
            print(json.dumps({"status": "exists", "entries": len(entries)}))
            return 0
        genesis = {"seq": 1, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "op": "init", "detail": {}, "files": [], "prev": "GENESIS"}
        with open(os.path.join(a.work, JOURNAL), "a", encoding="utf-8") as f:
            f.write(json.dumps(genesis, ensure_ascii=False) + "\n")
        print(json.dumps({"status": "initialized", "genesis_seq": 1}))
        return 0
    elif not entries:
        print(json.dumps({"error": "journal not initialized; run init first"}))
        return 2

    if a.cmd in ("append", "seal"):
        if not chain_ok(entries):
            print(json.dumps({"error": "journal hash chain broken; refusing to append"}))
            return 2
        prev = "GENESIS"
        if entries:
            prev = hashlib.sha256(json.dumps(
                entries[-1], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
        detail = {}
        if a.cmd == "append":
            try:
                detail = json.loads(a.detail)
            except json.JSONDecodeError:
                detail = {"raw": a.detail[:500]}
        files = []
        for fp in a.file:
            try:
                files.append({"path": fp, "sha256": sha256_of(fp)})
            except OSError as e:
                files.append({"path": fp, "error": str(e)[:120]})
        entry = {"seq": len(entries) + 1,
                 "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "op": "seal" if a.cmd == "seal" else (a.op or "note"),
                 "detail": detail, "files": files, "prev": prev}
        with open(os.path.join(a.work, JOURNAL), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(json.dumps({"appended": entry["seq"], "op": entry["op"]}, ensure_ascii=False))
    else:
        print(json.dumps({"status": "initialized"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
