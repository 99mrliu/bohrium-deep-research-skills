#!/usr/bin/env python3
"""parse_case.py — 材料清点：解析 case.json 与 task.md，盘点材料存在性。

输出 work/parsed_case.json：
  case_id, task_excerpt, materials(存在性/字节数), missing,
  budget, output_contract, status, limitations

退出码：0 正常（含部分缺失）；2 材料不足（case.json 无法读取）；3 校验失败。
仅使用 Python 标准库。支持 --help。
"""
import argparse
import hashlib
import json
import os
import sys

EXIT_OK = 0
EXIT_INSUFFICIENT = 2
EXIT_VALIDATION = 3

DEFAULT_CASE = "/input/case.json"
DEFAULT_TASK = "/task.md"
DEFAULT_WORK = "/app/work"


def sha256_of_file(path, block=65536):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(block), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def collect_material_paths(case_obj):
    """从 case.json 的 materials/files 段收集候选材料路径（容忍多种结构）。"""
    paths = []
    for key in ("materials", "files", "inputs"):
        sect = case_obj.get(key)
        if isinstance(sect, dict):
            for value in sect.values():
                if isinstance(value, str):
                    paths.append(value)
                elif isinstance(value, list):
                    paths.extend(v for v in value if isinstance(v, str))
        elif isinstance(sect, list):
            for item in sect:
                if isinstance(item, str):
                    paths.append(item)
                elif isinstance(item, dict) and isinstance(item.get("path"), str):
                    paths.append(item["path"])
    # 去重且保持顺序
    seen, ordered = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="解析 case.json 与 task.md，盘点本地材料并输出 parsed_case.json。"
    )
    ap.add_argument("--case", default=DEFAULT_CASE, help="case.json 路径（默认 /input/case.json）")
    ap.add_argument("--task", default=DEFAULT_TASK, help="task.md 路径（默认 /task.md，可缺省）")
    ap.add_argument("--work", default=DEFAULT_WORK, help="工作目录（默认 /app/work）")
    args = ap.parse_args(argv)

    os.makedirs(args.work, exist_ok=True)
    limitations = []
    materials, missing = [], []
    status = "ok"

    try:
        with open(args.case, "r", encoding="utf-8") as fh:
            case_obj = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        result = {
            "case_id": None,
            "task_excerpt": "",
            "materials": [],
            "missing": [],
            "budget": {},
            "output_contract": {},
            "status": "error_insufficient",
            "limitations": ["无法读取 case.json：%s" % exc],
        }
        out_path = os.path.join(args.work, "parsed_case.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        print("[parse_case] 材料不足：%s -> %s" % (exc, out_path), file=sys.stderr)
        return EXIT_INSUFFICIENT

    case_id = case_obj.get("case_id") or case_obj.get("id")
    if not case_id:
        status = "partial"
        limitations.append("case.json 缺少 case_id 字段")

    task_excerpt = ""
    if os.path.isfile(args.task):
        try:
            with open(args.task, "r", encoding="utf-8") as fh:
                task_excerpt = fh.read(2000)
        except OSError as exc:
            status = "partial"
            limitations.append("task.md 读取失败：%s" % exc)
    else:
        limitations.append("task.md 不存在：%s" % args.task)
        status = "partial"

    base_dir = os.path.dirname(os.path.abspath(args.case))
    for raw in collect_material_paths(case_obj):
        path = raw if os.path.isabs(raw) else os.path.join(base_dir, raw)
        if os.path.isfile(path):
            materials.append({
                "path": raw,
                "resolved": os.path.abspath(path),
                "exists": True,
                "size_bytes": os.path.getsize(path),
                "sha256": sha256_of_file(path),
            })
        elif os.path.isdir(path):
            count = 0
            for root, _dirs, files in os.walk(path):
                count += len(files)
            materials.append({
                "path": raw,
                "resolved": os.path.abspath(path),
                "exists": True,
                "is_dir": True,
                "file_count": count,
            })
        else:
            missing.append(raw)
    if missing:
        status = "partial"
        limitations.append("材料缺失 %d 项：%s" % (len(missing), ", ".join(missing)))

    result = {
        "case_id": case_id,
        "task_excerpt": task_excerpt,
        "materials": materials,
        "missing": missing,
        "budget": case_obj.get("budget", {}),
        "output_contract": case_obj.get("output_contract", {}),
        "status": status,
        "limitations": limitations,
    }
    out_path = os.path.join(args.work, "parsed_case.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print("[parse_case] status=%s 材料=%d 缺失=%d -> %s" % (status, len(materials), len(missing), out_path))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
