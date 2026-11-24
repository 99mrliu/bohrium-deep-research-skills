#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rebuild_index.py — 归档恢复演练：只凭清单与落库文件重建 catalog，并与运行期索引对比。

用法：
  python3 rebuild_index.py --manifest LIBRARY_MANIFEST.jsonl --library library/ \
      --out index/ [--runtime-db index/catalog.db] [--diff-out REBUILD_DIFF.json]

重建产物写到 <out>/rebuild_check/catalog.db（不覆盖运行期索引）。
对比 (rel_path, sha256, size) 条目集合，结果写 REBUILD_DIFF.json：
  status=empty_diff 表示恢复无损；非空差异如实记录，绝不改写为空。
"""
import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indexer  # noqa: E402  （同 bundle 脚本，允许复用）


def entry_set(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT COALESCE(rel_path,''), COALESCE(sha256,''), COALESCE(size,-1),"
        " COALESCE(source_path,'') FROM files")
    rows = sorted(cur.fetchall())
    conn.close()
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="只凭清单与落库文件重建索引并对比")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--library", required=True)
    ap.add_argument("--out", required=True, help="index 目录（重建产物入其子目录）")
    ap.add_argument("--runtime-db", help="运行期 catalog.db（默认 <out>/catalog.db）")
    ap.add_argument("--diff-out", help="REBUILD_DIFF.json（默认 <out>/../REBUILD_DIFF.json）")
    args = ap.parse_args(argv)

    runtime_db = args.runtime_db or os.path.join(args.out, "catalog.db")
    rebuild_dir = os.path.join(args.out, "rebuild_check")
    os.makedirs(rebuild_dir, exist_ok=True)
    rebuilt_db = os.path.join(rebuild_dir, "catalog.db")

    rebuild_stats = indexer.build_catalog(args.manifest, args.library, rebuilt_db)

    runtime_entries = entry_set(runtime_db) if os.path.isfile(runtime_db) else []
    rebuilt_entries = entry_set(rebuilt_db)
    runtime_keys = {(r[0], r[1], r[2]) for r in runtime_entries}
    rebuilt_keys = {(r[0], r[1], r[2]) for r in rebuilt_entries}
    missing = sorted(runtime_keys - rebuilt_keys)
    extra = sorted(rebuilt_keys - runtime_keys)

    diff = {
        "status": "empty_diff" if not missing and not extra else "non_empty_diff",
        "runtime_db": runtime_db,
        "rebuilt_db": rebuilt_db,
        "runtime_entries": len(runtime_entries),
        "rebuilt_entries": len(rebuilt_entries),
        "missing_in_rebuild": [
            {"rel_path": m[0], "sha256": m[1], "size": m[2]} for m in missing],
        "extra_in_rebuild": [
            {"rel_path": m[0], "sha256": m[1], "size": m[2]} for m in extra],
        "rebuild_degraded": rebuild_stats.get("degraded", False),
        "note": "empty_diff=仅凭清单与落库文件即可无损重建索引；非空差异需人工核查",
    }
    diff_out = args.diff_out or os.path.join(
        os.path.dirname(os.path.abspath(args.out.rstrip("/"))) or ".", "REBUILD_DIFF.json")
    if args.diff_out is None:
        # 默认放到 index/ 的上一级（即 /app/output/REBUILD_DIFF.json）
        diff_out = os.path.join(os.path.dirname(os.path.abspath(args.out)),
                                "REBUILD_DIFF.json")
    with open(diff_out, "w", encoding="utf-8") as f:
        json.dump(diff, f, ensure_ascii=False, indent=2)
    print(json.dumps({"status": diff["status"],
                      "runtime_entries": len(runtime_entries),
                      "rebuilt_entries": len(rebuilt_entries),
                      "diff_out": diff_out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
