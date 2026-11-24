#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""material_check.py — 材料盘点: 在任何内容工作之前发现缺失/不可读/空材料。

输出:
  material_inventory.json  机器可读盘点 (含 size/sha256/flag)
  material_inventory.md    人读摘要
stdout 末尾打印可直接粘贴进 result.json limits 的 JSON 行 (缺失被引用材料时)。

退出码: 0=无问题; 1=存在问题(缺失被引用材料/目录为空等), 但盘点文件已正常写出;
       2=用法或目录本身不可访问。
仅依赖标准库 (>=3.9)。
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

KNOWN_EXT = {".md", ".txt", ".csv", ".tsv", ".json", ".png", ".jpg", ".jpeg",
             ".gif", ".pdf", ".tif", ".tiff", ".xlsx", ".xls", ".py", ".r",
             ".ipynb", ".docx", ".pptx", ".html", ".xml", ".yaml", ".yml",
             ".bib", ".tex", ".zip"}
REF_FIELDS = ("materials", "figures", "files", "inputs", "attachments",
              "data", "datasets", "references_files")


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_refs(case):
    """从 case.json 常见字段中收集被引用的材料路径 (字符串或含 path/file 键的对象)。"""
    refs = []
    for field in REF_FIELDS:
        v = case.get(field)
        if isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    refs.append((field, item))
                elif isinstance(item, dict):
                    for k in ("path", "file", "filename", "name"):
                        if isinstance(item.get(k), str):
                            refs.append((field, item[k]))
                            break
        elif isinstance(v, str):
            refs.append((field, v))
    return refs


def cmd_check(args):
    root = args.dir
    if not os.path.isdir(root):
        print("ERROR: 材料目录不可访问: %s" % root, file=sys.stderr)
        return 2

    entries = []
    problems = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            e = {"path": rel, "flags": []}
            try:
                e["size"] = os.path.getsize(full)
                e["sha256"] = sha256_of(full)
            except OSError:
                e["size"] = None
                e["sha256"] = None
                e["flags"].append("unreadable")
                problems.append("不可读: %s" % rel)
                entries.append(e)
                continue
            if e["size"] == 0:
                e["flags"].append("empty")
                problems.append("空文件: %s" % rel)
            ext = os.path.splitext(fn)[1].lower()
            if ext not in KNOWN_EXT:
                e["flags"].append("unknown_extension")
                problems.append("未知扩展名 (%s): %s" % (ext or "无", rel))
            entries.append(e)

    if not entries:
        problems.append("材料目录为空: %s" % root)

    # 交叉核对 case.json 引用
    missing_refs = []
    if args.case:
        try:
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
            present = {e["path"] for e in entries}
            present_basenames = {os.path.basename(p) for p in present}
            for field, ref in collect_refs(case):
                ref_rel = ref.lstrip("/")
                # 兼容绝对路径 (/input/...)、相对路径与裸文件名三种写法
                tail = ref_rel.split("materials/")[-1] if "materials/" in ref_rel else ref_rel
                if (ref_rel in present or tail in present
                        or os.path.basename(ref_rel) in present_basenames
                        or os.path.isfile(os.path.join(root, ref_rel))
                        or os.path.isfile(os.path.join(root, tail))):
                    continue
                missing_refs.append((field, ref))
                problems.append("case.json 引用缺失: [%s] %s" % (field, ref))
        except (OSError, ValueError) as e:
            problems.append("case.json 无法解析, 交叉核对跳过: %s" % e)

    inventory = {
        "generated_at": now_iso(),
        "root": os.path.abspath(root),
        "case": os.path.abspath(args.case) if args.case else None,
        "file_count": len(entries),
        "files": entries,
        "missing_referenced": [{"field": f, "ref": r} for f, r in missing_refs],
        "problems": problems,
    }
    os.makedirs(args.out_dir, exist_ok=True)
    jpath = os.path.join(args.out_dir, "material_inventory.json")
    mpath = os.path.join(args.out_dir, "material_inventory.md")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(inventory, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("# 材料盘点\n\n")
        f.write("- 目录: `%s`\n- 文件数: %d\n- 生成时间: %s\n\n"
                % (inventory["root"], len(entries), inventory["generated_at"]))
        f.write("| 文件 | 大小(B) | sha256(前12) | 标记 |\n|---|---|---|---|\n")
        for e in entries:
            f.write("| %s | %s | %s | %s |\n" % (
                e["path"], e["size"],
                (e["sha256"] or "—")[:12], ", ".join(e["flags"]) or "ok"))
        f.write("\n## 问题\n\n")
        if problems:
            for p_ in problems:
                f.write("- %s\n" % p_)
        else:
            f.write("- 无\n")
    print("INVENTORY: %s (%d 文件)" % (jpath, len(entries)))
    print("SUMMARY  : %s" % mpath)
    if problems:
        print("PROBLEMS (%d):" % len(problems))
        for p_ in problems:
            print("  - %s" % p_)
    else:
        print("PROBLEMS: 无")

    if missing_refs or not entries:
        print("\n请将以下行粘贴进 result.json 的 limits (JSON 数组元素):")
        if not entries:
            print('  "材料目录为空或不存在: 无任何可用输入材料, 内容工作无法进行。"')
        for field, ref in missing_refs:
            print('  "缺失材料: %s (case.json 字段 %s 引用, 但材料目录中不存在)。"'
                  % (ref, field))
        return 1
    return 0


def main():
    p = argparse.ArgumentParser(description="材料盘点: 缺失/不可读/空材料的前置识别。")
    p.add_argument("--dir", required=True, help="材料目录, 如 /input 或 /input/materials")
    p.add_argument("--case", help="case.json 路径 (用于交叉核对引用)")
    p.add_argument("--out-dir", required=True, help="盘点输出目录, 如 /app/work")
    args = p.parse_args()
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
