#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_boot.py — 运行契约引导脚本（仅使用 Python 3.10+ 标准库，无网络）。

职责：
  1. 读取 case.json（容忍多种结构）与 task.md；
  2. 清点材料文件（存在性、可读性、字节数、sha256），缺失材料只登记不崩溃；
  3. 尽早写出一份诚实的 partial 状态 result.json（契约字段占位）；
  4. 写出 work_plan.md 与 intake_manifest.json。

退出码：0 = 正常完成；2 = case.json 缺失或不可解析（仍写出 result.json）。
输出确定性：不使用时钟、不使用随机数。
"""

import argparse
import hashlib
import json
import os
import sys

PLACEHOLDER = "__pending__"

# 契约以“字段名列表”形式给出时，按名称启发式判定列表型字段
LIST_TYPED_NAMES = {
    "sources", "uncertainty", "uncertainties", "artifacts", "references",
    "tags", "keywords", "items", "records", "changes", "change_records",
    "citations", "evidence", "evidence_list", "materials", "nodes", "edges",
}

# 保留键：与 result.json 固定字段同名的契约字段不放置占位符
RESERVED_KEYS = {"status", "sources", "uncertainty"}


def eprint(*args):
    print(*args, file=sys.stderr)


def is_cjk(text):
    for ch in text:
        if "一" <= ch <= "鿿":
            return True
    return False


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def sha256_of(path, block=65536):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(block)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def parse_case(case_path):
    """返回 (case_dict, error_message)。容忍顶层 case_id/id 等结构。"""
    if not os.path.isfile(case_path):
        return None, "case.json 不存在: %s" % case_path
    try:
        with open(case_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return None, "case.json 无法解析: %s (%s)" % (case_path, exc)
    if not isinstance(data, dict):
        return None, "case.json 顶层不是对象: %s" % case_path
    return data, None


def extract_case_id(case):
    for key in ("case_id", "id", "caseId"):
        val = case.get(key)
        if isinstance(val, str) and val.strip():
            return val
        if val is not None and not isinstance(val, (dict, list)):
            return str(val)
    return "unknown"


def extract_contract_fields(case):
    """返回 (field_names, list_typed_set)。容忍列表或字典两种契约形态。"""
    raw = case.get("output_contract")
    names = []
    list_typed = set()
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, dict):
                name = item.get("name") or item.get("field")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
                    if str(item.get("type", "")).lower() in ("list", "array"):
                        list_typed.add(name.strip())
    elif isinstance(raw, dict):
        for name, spec in raw.items():
            if not isinstance(name, str) or not name.strip():
                continue
            names.append(name.strip())
            if isinstance(spec, dict):
                if str(spec.get("type", "")).lower() in ("list", "array"):
                    list_typed.add(name.strip())
            elif isinstance(spec, str) and spec.lower() in ("list", "array"):
                list_typed.add(name.strip())
    # 去重并保持顺序
    seen = set()
    ordered = []
    for n in names:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    for n in ordered:
        if n in LIST_TYPED_NAMES:
            list_typed.add(n)
    return ordered, list_typed


def extract_materials(case):
    """容忍 materials/material_files，元素为路径字符串或含 path 键的字典。"""
    raw = case.get("materials")
    if raw is None:
        raw = case.get("material_files")
    paths = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                paths.append(item.strip())
            elif isinstance(item, dict):
                p = item.get("path") or item.get("file") or item.get("filename")
                if isinstance(p, str) and p.strip():
                    paths.append(p.strip())
    elif isinstance(raw, str) and raw.strip():
        paths.append(raw.strip())
    return paths


def resolve_material(path, case_path):
    """相对路径的材料：先按当前目录、再按 case.json 所在目录解析。返回实际路径。"""
    if os.path.isabs(path):
        return path
    case_dir = os.path.dirname(os.path.abspath(case_path))
    for cand in (path, os.path.join(case_dir, path)):
        if os.path.exists(cand):
            return cand
    return os.path.join(case_dir, path)


def placeholder_for(field, list_typed):
    if field in list_typed:
        return []
    return PLACEHOLDER


def main(argv=None):
    parser = argparse.ArgumentParser(description="运行契约引导：清点输入并写出首个 partial result.json")
    parser.add_argument("--case", required=True, help="case.json 路径，如 /input/case.json")
    parser.add_argument("--task", required=True, help="task.md 路径，如 /input/task.md")
    parser.add_argument("--out", required=True, help="输出目录，如 /app/output")
    parser.add_argument("--work", required=True, help="工作目录，如 /app/work")
    args = parser.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.work, exist_ok=True)
    result_path = os.path.join(args.out, "result.json")

    task_text = read_text(args.task)
    zh = is_cjk(task_text) or not task_text.strip()

    case, err = parse_case(args.case)
    if case is None:
        # case.json 缺失/不可解析：仍写出 result.json，诚实标记，退出码 2
        note = ("case.json 缺失或无法解析，无法确定契约与材料: %s" % args.case) if zh else (
            "case.json missing or unparseable; contract and materials undetermined: %s" % args.case)
        result = {
            "case_id": "unknown",
            "status": "unable_to_determine",
            "sources": [],
            "uncertainty": [note],
            "contract_fields": [],
            "partial_reason": ("boot: %s" % note) if zh else ("boot: %s" % note),
            "artifacts": [],
        }
        with open(result_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        manifest = {"materials": [], "material_count": 0, "missing_count": 0,
                    "note": note}
        with open(os.path.join(args.work, "intake_manifest.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        eprint("[contract_boot] ERROR: %s" % err)
        eprint("[contract_boot] 已写出 unable_to_determine 状态的 result.json: %s" % result_path)
        return 2

    case_id = extract_case_id(case)
    contract_fields, list_typed = extract_contract_fields(case)
    material_paths = extract_materials(case)

    # ---- 材料清点：缺失只登记，不崩溃 ----
    manifest_entries = []
    seeded_uncertainty = []
    for path in material_paths:
        actual = resolve_material(path, args.case)
        exists = os.path.isfile(actual)
        readable = False
        size = None
        digest = None
        note = "ok"
        if exists:
            try:
                size = os.path.getsize(actual)
                digest = sha256_of(actual)
                readable = os.access(actual, os.R_OK)
                if not readable:
                    note = "存在但不可读"
            except OSError as exc:
                note = "读取失败: %s" % exc
        else:
            note = "材料路径不存在或不是常规文件"
            msg = ("材料缺失或不可读: %s（boot 清点时未发现，需人工确认或寻找替代来源）" % path) if zh else (
                "material missing or unreadable: %s (not found at boot intake; needs human confirmation or a substitute source)" % path)
            seeded_uncertainty.append(msg)
            eprint("[contract_boot] WARNING: %s: %s" % (note, path))
        manifest_entries.append({
            "path": path,
            "exists": exists,
            "size": size,
            "sha256": digest,
            "readable": readable,
            "note": note,
        })

    missing_count = sum(1 for e in manifest_entries if not e["exists"])
    manifest = {
        "materials": manifest_entries,
        "material_count": len(manifest_entries),
        "missing_count": missing_count,
        "note": ("清点完成：共 %d 项，缺失 %d 项" % (len(manifest_entries), missing_count)) if zh else (
            "intake complete: %d item(s), %d missing" % (len(manifest_entries), missing_count)),
    }
    manifest_path = os.path.join(args.work, "intake_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    # ---- 首个 partial result.json：契约字段占位 ----
    result = {"case_id": case_id}
    for field in contract_fields:
        result[field] = placeholder_for(field, list_typed)
    result["status"] = "partial"  # 覆盖可能的同名契约占位
    result["sources"] = []
    result["uncertainty"] = list(seeded_uncertainty)
    result["contract_fields"] = contract_fields
    result["partial_reason"] = ("boot: 材料清点完成，产物未生成" if zh
                                else "boot: material intake complete; artifacts not yet generated")
    result["artifacts"] = []

    with open(result_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    # ---- 工作计划清单 ----
    plan_lines = [
        "# 工作计划（work plan）" if zh else "# Work plan",
        "",
        "- [ ] 1. intake：清点 case.json 与材料，生成 intake_manifest.json 与首个 partial result.json",
        "- [ ] 2. extract：从材料中提取要点、数据与证据，登记 sources",
        "- [ ] 3. design：设计思维导图层级与分支结构",
        "- [ ] 4. build：生成导图及契约要求的各产物，并用 checkpoint 登记 artifact",
        "- [ ] 5. verify：填写全部契约字段，消解或如实保留 uncertainty，运行 final_audit 对账",
        "- [ ] 6. deliver：确认 result.json 状态诚实、change_record 完整后交付",
        "",
    ]
    with open(os.path.join(args.work, "work_plan.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(plan_lines))

    print("[contract_boot] case_id=%s contract_fields=%d materials=%d missing=%d" % (
        case_id, len(contract_fields), len(manifest_entries), missing_count))
    print("[contract_boot] partial result.json -> %s" % result_path)
    print("[contract_boot] intake_manifest -> %s" % manifest_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
