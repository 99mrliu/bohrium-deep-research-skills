#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hash_ledger.py — 建立源快照 SHA-256 内容哈希台账（source_ledger.json）。

对材料目录下每个 .json 文件记录：
  * sha256 内容哈希、字节数；
  * 固化时间（只取自材料自身字段，材料未提供则为 null，绝不编造）及其 locator；
  * 题录条数、解析错误、内容完全重复（同哈希）的其他文件。

用法：
    python3 hash_ledger.py --materials <材料目录> --out <source_ledger.json>
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common


def build_ledger(materials_dir):
    entries = []
    seen_hashes = {}
    for path in common.iter_material_files(materials_dir):
        digest = common.sha256_of_file(path)
        entry = {
            "path": path,
            "locator": path + "#",
            "sha256": digest,
            "bytes": os.path.getsize(path),
            "kind": ("versioned_snapshot"
                     if common.is_versioned_snapshot(path)
                     else "source_snapshot"),
            "source": None,
            "frozen_at": None,
            "frozen_at_locator": None,
            "record_count": None,
            "parse_error": None,
            "content_duplicate_of": None,
        }
        try:
            data = common.load_json(path)
            frozen, frozen_ptr = common.find_frozen_at(data)
            entry["frozen_at"] = frozen
            entry["frozen_at_locator"] = (path + frozen_ptr) if frozen_ptr else None
            if isinstance(data, dict) and isinstance(data.get("source"), str):
                entry["source"] = data["source"]
            records, _base = common.extract_records(data)
            if records is not None:
                entry["record_count"] = len(records)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            entry["parse_error"] = "%s: %s" % (type(exc).__name__, exc)
        if digest in seen_hashes:
            entry["content_duplicate_of"] = seen_hashes[digest]
        else:
            seen_hashes[digest] = path
        entries.append(entry)
    return {
        "generated_by": "hash_ledger.py",
        "materials_dir": materials_dir,
        "algorithm": "sha256",
        "total_files": len(entries),
        "total_bytes": sum(e["bytes"] for e in entries),
        "files": entries,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="建立源快照 SHA-256 内容哈希台账")
    parser.add_argument("--materials", required=True, help="材料目录")
    parser.add_argument("--out", required=True, help="输出 source_ledger.json 路径")
    args = parser.parse_args(argv)
    if not os.path.isdir(args.materials):
        print("ERROR: 材料目录不存在: %s" % args.materials, file=sys.stderr)
        return 2
    ledger = build_ledger(args.materials)
    common.dump_json(ledger, args.out)
    print("hash_ledger: %d 个文件, 共 %d 字节 -> %s"
          % (ledger["total_files"], ledger["total_bytes"], args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
