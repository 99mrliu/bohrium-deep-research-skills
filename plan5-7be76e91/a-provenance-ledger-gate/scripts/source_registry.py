#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""source_registry.py — 来源登记与指纹（provenance-ledger-gate 步骤 1）

递归登记一个目录下的全部来源材料文件，为每个文件记录：
  - rel_path（相对 --input-dir 的 POSIX 风格相对路径）
  - bytes（字节数）
  - sha256（内容指纹）
  - 文本抽取：.txt/.md/.json 直读 UTF-8 文本并内联到输出的 "text" 字段；
    其他后缀（如 .pdf/.docx）只记录指纹并标记 needs_extraction=true。

输出 registry.json：键排序、无 wall-clock 时间戳（如需登记日期用 --asof 显式给定），
同一输入双跑产物逐字节一致。仅用 Python 3 标准库。

用法：
  python3 source_registry.py --input-dir /input --out /app/work/registry.json
  python3 source_registry.py --input-dir examples/sources --out registry.json \
      --asof 2026-01-01 --note "合成示例 / SYNTHETIC EXAMPLE，非正式案例结果"

退出码：0=成功；2=输入/用法错误。
"""

import argparse
import hashlib
import json
import os
import sys

TEXT_SUFFIXES = {".txt", ".md", ".json"}
TOOL_VERSION = "1.0"


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_registry(input_dir: str, asof, note):
    root = os.path.abspath(input_dir)
    if not os.path.isdir(root):
        raise NotADirectoryError("input-dir 不存在或不是目录: %s" % input_dir)
    entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            if os.path.islink(full):
                # 符号链接不跟随，标记为不可核验来源
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                entries.append({
                    "rel_path": rel,
                    "bytes": 0,
                    "sha256": None,
                    "text_extracted": False,
                    "needs_extraction": True,
                    "text": None,
                    "warning": "符号链接，未跟随",
                })
                continue
            with open(full, "rb") as fh:
                data = fh.read()
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            suffix = os.path.splitext(fn)[1].lower()
            entry = {
                "rel_path": rel,
                "bytes": len(data),
                "sha256": sha256_of(data),
            }
            if suffix in TEXT_SUFFIXES:
                try:
                    entry["text"] = data.decode("utf-8")
                    entry["text_extracted"] = True
                    entry["needs_extraction"] = False
                except UnicodeDecodeError:
                    entry["text"] = None
                    entry["text_extracted"] = False
                    entry["needs_extraction"] = True
                    entry["warning"] = "UTF-8 解码失败，需人工抽取文本"
            else:
                entry["text"] = None
                entry["text_extracted"] = False
                entry["needs_extraction"] = True
            entries.append(entry)
    registry = {
        "tool": "source_registry.py",
        "tool_version": TOOL_VERSION,
        "input_dir": input_dir,
        "file_count": len(entries),
        "files": entries,
    }
    if asof is not None:
        registry["asof"] = asof
    if note is not None:
        registry["note"] = note
    return registry


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="递归登记来源材料文件（SHA-256/字节数/文本抽取），输出确定性 registry.json。")
    parser.add_argument("--input-dir", required=True,
                        help="来源材料根目录（递归扫描）")
    parser.add_argument("--out", required=True,
                        help="registry.json 输出路径")
    parser.add_argument("--asof", default=None,
                        help="固定登记日期（如 2026-01-01）；不指定则输出不含任何时间字段")
    parser.add_argument("--note", default=None,
                        help="写入输出的备注（示例数据必须写：合成示例 / SYNTHETIC EXAMPLE）")
    args = parser.parse_args(argv)

    try:
        registry = build_registry(args.input_dir, args.asof, args.note)
    except (NotADirectoryError, OSError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    payload = json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(payload)
    n_extract = sum(1 for e in registry["files"] if e["needs_extraction"])
    print("OK registry: %d 个文件已登记 (%d 个需人工抽取文本) -> %s"
          % (registry["file_count"], n_extract, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
