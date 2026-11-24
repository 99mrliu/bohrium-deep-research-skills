#!/usr/bin/env python3
"""journal_exec.py — WAL 两段式提交复制引擎（run-ledger-audit 核心，stdlib only）。

每次复制 = 两段式提交：
  1. journal 追加 {"op":"begin", id, src, dst, dst_staging, sha256_src}
  2. 复制到 staging → 重算 staging 哈希 → 与 sha256_src 一致才 os.replace 原子改名到 dst
  3. 重算最终文件哈希 → 追加 {"op":"done", id, sha256_dst}
  任何异常 → 追加 {"op":"failed", id, error}

启动时 reconcile：发现 begin 无对应 done/failed/reconciled → 清理 staging 残留并追加
{"op":"reconciled", id, ...}。journal 每行带单调 seq 与 UTC ISO 时间。

CLI（独立 reconcile）：
  python3 journal_exec.py reconcile --journal operations_journal.jsonl --staging DIR
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone

CHUNK = 65536


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_journal(path):
    """读取 journal，返回记录列表；坏行不丢弃，记为 corrupt_line（绝不静默）。"""
    recs = []
    if not os.path.exists(path):
        return recs
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                recs.append({"op": "corrupt_line", "line_no": i, "raw": line[:200]})
    return recs


class Journal:
    """追加式 WAL。seq 单调递增（= 历史最大 seq + 1 起）。"""

    def __init__(self, path):
        self.path = path
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        self.records = read_journal(path)
        mx = 0
        for r in self.records:
            s = r.get("seq")
            if isinstance(s, int) and s > mx:
                mx = s
        self._seq = mx + 1

    def append(self, rec):
        rec["seq"] = self._seq
        self._seq += 1
        rec["ts"] = utc_now()
        line = json.dumps(rec, ensure_ascii=False, sort_keys=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        self.records.append(rec)
        return rec

    def open_begins(self):
        """返回 {id: begin_record}：有 begin 但没有任何 done/failed/reconciled 闭合。"""
        closed = set()
        for r in self.records:
            if r.get("op") in ("done", "failed", "reconciled") and r.get("id"):
                closed.add(r["id"])
        opens = {}
        for r in self.records:
            if r.get("op") == "begin" and r.get("id") and r["id"] not in closed:
                opens[r["id"]] = r
        return opens

    def done_seq_for(self, dst):
        """某 dst 最近一次 done 的 seq（用于 manifest 回指证据）。"""
        seq = None
        for r in self.records:
            if r.get("op") == "done" and r.get("dst") == dst:
                seq = r.get("seq")
        return seq


def reconcile(journal, staging_dir):
    """清理 begin 未闭合的 staging 残留，每个补一条 reconciled 记录。返回处理数。"""
    n = 0
    for op_id, begin in sorted(journal.open_begins().items()):
        staging = begin.get("dst_staging") or os.path.join(staging_dir, op_id + ".part")
        removed = False
        err = None
        try:
            if os.path.exists(staging):
                os.remove(staging)
                removed = True
        except OSError as e:
            err = str(e)
        journal.append({
            "op": "reconciled", "id": op_id,
            "src": begin.get("src"), "dst": begin.get("dst"),
            "staging_removed": removed, "staging_path": staging,
            "error": err,
            "reason": "begin_without_close_at_startup; staged copy discarded",
        })
        n += 1
    return n


def copy_with_wal(journal, op_id, src_abs, dst_abs, staging_dir, src_rel=None, dst_rel=None):
    """两段式提交复制单个文件。返回 (ok, done_record_or_none)。绝不抛异常给调用方。"""
    os.makedirs(staging_dir, exist_ok=True)
    staging = os.path.join(staging_dir, op_id + ".part")
    src_rel = src_rel if src_rel is not None else src_abs
    dst_rel = dst_rel if dst_rel is not None else dst_abs
    try:
        sha_src = sha256_file(src_abs)
        size = os.path.getsize(src_abs)
    except OSError as e:
        journal.append({"op": "failed", "id": op_id, "src": src_rel, "dst": dst_rel,
                        "phase": "hash_src", "error": str(e)})
        return False, None
    journal.append({"op": "begin", "id": op_id, "src": src_rel, "dst": dst_rel,
                    "dst_staging": staging, "sha256_src": sha_src, "bytes": size})
    try:
        shutil.copy2(src_abs, staging)
        sha_staging = sha256_file(staging)
        if sha_staging != sha_src:
            journal.append({"op": "failed", "id": op_id, "src": src_rel, "dst": dst_rel,
                            "phase": "staging_hash_mismatch",
                            "error": "sha256(staging) != sha256(src): %s != %s" % (sha_staging, sha_src)})
            return False, None
        os.makedirs(os.path.dirname(os.path.abspath(dst_abs)), exist_ok=True)
        os.replace(staging, dst_abs)  # 原子改名，同卷内不留下半截文件
        sha_dst = sha256_file(dst_abs)
        if sha_dst != sha_src:
            journal.append({"op": "failed", "id": op_id, "src": src_rel, "dst": dst_rel,
                            "phase": "final_hash_mismatch",
                            "error": "sha256(dst) != sha256(src): %s != %s" % (sha_dst, sha_src)})
            return False, None
        rec = journal.append({"op": "done", "id": op_id, "src": src_rel, "dst": dst_rel,
                              "sha256_dst": sha_dst, "bytes": size})
        return True, rec
    except OSError as e:
        journal.append({"op": "failed", "id": op_id, "src": src_rel, "dst": dst_rel,
                        "phase": "copy", "error": str(e)})
        return False, None


def main(argv=None):
    ap = argparse.ArgumentParser(description="WAL journal 工具")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("reconcile", help="清理 begin 未闭合的 staging 残留")
    p.add_argument("--journal", required=True)
    p.add_argument("--staging", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "reconcile":
        j = Journal(a.journal)
        n = reconcile(j, a.staging)
        print(json.dumps({"reconciled": n, "journal": a.journal}, ensure_ascii=False))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
