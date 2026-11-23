#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""init_run.py — process-qc-guard 运行预检与预算安全网。

职责：
  1. 清点输入目录（每文件 sha256 + 字节数 + mtime），探测可选工具（pdftotext/pdfinfo）；
  2. 解析 case.json，宽容提取 case_id 与 output_contract 字段名；
  3. 写 run_manifest.json（输入清单、工具探测、预算台账、阶段清单）；
  4. 立即写 result.json 合法部分骨架（status=部分完成，预算安全网），幂等：
     重复运行不覆盖已有正式结果与人工/模型工作文件，只刷新预检字段。

仅使用 Python 标准库（3.8+）；产物确定性（不含 wall-clock 时间戳，输入 mtime 仅作记录）；
绝不因畸形输入崩溃，原子写（tmp + os.replace）。
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

SCHEMA = "process-qc-guard/init_run@1"

BUDGET_TOTAL = {"seconds": 900, "requests": 64, "response_tokens": 16384}
BUDGET_PLAN = [
    {"phase": "preflight", "name": "预检与清单", "seconds": 60, "requests": 2},
    {"phase": "draft", "name": "读材料与起草", "seconds": 540, "requests": 38},
    {"phase": "verify", "name": "核验与失败探针", "seconds": 180, "requests": 14},
    {"phase": "gate", "name": "一致性复跑与交付门禁", "seconds": 120, "requests": 10},
]
STAGES = ["init", "draft", "verify", "consistency", "export"]


def sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def read_json_tolerant(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as exc:  # 宽容：任何解析失败都降级为 warning
        return None, "%s: %s" % (type(exc).__name__, exc)


def extract_contract(case_obj):
    """从 case.json 提取 (case_id, contract_fields, warnings)，尽量宽容。"""
    warnings = []
    if not isinstance(case_obj, dict):
        return "unknown-case", [], ["case.json 缺失或不是合法 JSON 对象"]
    case_id = case_obj.get("case_id") or "unknown-case"
    contract = case_obj.get("output_contract")
    fields = []
    if isinstance(contract, dict):
        for key in ("required_fields", "fields", "properties"):
            val = contract.get(key)
            if isinstance(val, list):
                fields = [str(x) for x in val]
                break
            if isinstance(val, dict):
                fields = sorted(str(k) for k in val)
                break
        if not fields:
            warnings.append("output_contract 为对象但未识别出字段清单")
    elif isinstance(contract, list):
        fields = [str(x) for x in contract]
    elif contract is None:
        warnings.append("case.json 缺少 output_contract 字段")
    else:
        warnings.append("output_contract 类型无法识别：%s" % type(contract).__name__)
    return str(case_id), fields, warnings


def probe_tools():
    tools = {}
    for name in ("pdftotext", "pdfinfo"):
        path = shutil.which(name)
        tools[name] = {
            "available": path is not None,
            "path": path,
            "fallback": "缺失时优雅降级：改用纯文本材料或人工摘录，不阻塞流程",
        }
    return tools


def scan_inputs(input_dir):
    entries, warnings = [], []
    if not os.path.isdir(input_dir):
        return entries, ["输入目录不存在：%s" % input_dir]
    for root, dirs, files in os.walk(input_dir):
        dirs.sort()
        for fn in sorted(files):
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, input_dir)
            try:
                st = os.stat(full)
                entries.append({
                    "path": rel,
                    "bytes": st.st_size,
                    "sha256": sha256_file(full),
                    "mtime_epoch": int(st.st_mtime),
                })
            except OSError as exc:
                entries.append({"path": rel, "bytes": None, "sha256": None,
                                "mtime_epoch": None, "error": str(exc)})
                warnings.append("无法读取输入文件：%s" % rel)
    return entries, warnings


def ensure_result_skeleton(output_dir, case_id, fields):
    """写 result.json 合法部分骨架；幂等，不覆盖已有正式结果。"""
    path = os.path.join(output_dir, "result.json")
    existing = None
    if os.path.exists(path):
        existing, _err = read_json_tolerant(path)
        if isinstance(existing, dict) and not existing.get("skeleton"):
            return "kept-existing（已存在正式结果，未覆盖）"
    doc = {
        "case_id": case_id,
        "status": "部分完成",
        "status_reason": "初始化：预检完成，作答尚未开始；本骨架为预算安全网，任何时刻中断均可提交。",
        "sources": [],
        "uncertainty": ["全部契约字段尚未作答"],
        "change_records": [{"seq": 0, "stage": "init",
                            "note": "init_run 生成预算安全网骨架"}],
        "skeleton": True,
    }
    for f in fields:
        doc.setdefault(f, None)
    if isinstance(existing, dict):  # 幂等刷新：保留骨架阶段已人工填入的字段
        for f in fields:
            if existing.get(f) not in (None, ""):
                doc[f] = existing[f]
    atomic_write_json(path, doc)
    return "written（安全网骨架已就位）"


def build_manifest(args, case_id, fields, inputs, tools, warnings):
    return {
        "schema": SCHEMA,
        "case_id": case_id,
        "contract_fields": fields,
        "paths": {"input_dir": os.path.abspath(args.input_dir),
                  "work_dir": os.path.abspath(args.work_dir),
                  "output_dir": os.path.abspath(args.output_dir)},
        "inputs": inputs,
        "tools": tools,
        "budget": {
            "total": BUDGET_TOTAL,
            "plan": BUDGET_PLAN,
            "notes": [
                "900 秒分配建议：预检 ≤1 分钟；读材料与起草 ≤60%；核验与探针 ≥20%；门禁与交付 ≥10%。",
                "合法部分 result.json 已由本脚本先行写入（预算安全网），随后增量完善。",
            ],
        },
        "stages": STAGES,
        "warnings": warnings,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="process-qc-guard 预检：清点输入、探测工具、写 manifest 与 result.json 安全网骨架。")
    ap.add_argument("--input-dir", default="/input", help="输入目录（默认 /input）")
    ap.add_argument("--work-dir", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--output-dir", default="/app/output", help="交付目录（默认 /app/output）")
    args = ap.parse_args(argv)

    try:
        os.makedirs(args.work_dir, exist_ok=True)
        os.makedirs(args.output_dir, exist_ok=True)
    except OSError as exc:
        print(json.dumps({"ok": False, "fatal": "无法创建目录：%s" % exc},
                         ensure_ascii=False))
        return 1

    warnings = []
    case_obj, err = read_json_tolerant(os.path.join(args.input_dir, "case.json"))
    if err:
        warnings.append("case.json 解析失败：%s" % err)
    case_id, fields, w = extract_contract(case_obj)
    warnings.extend(w)

    inputs, w = scan_inputs(args.input_dir)
    warnings.extend(w)
    tools = probe_tools()

    manifest = build_manifest(args, case_id, fields, inputs, tools, warnings)
    try:
        atomic_write_json(os.path.join(args.work_dir, "run_manifest.json"), manifest)
    except OSError as exc:
        print(json.dumps({"ok": False, "fatal": "manifest 写入失败：%s" % exc},
                         ensure_ascii=False))
        return 1

    try:
        skeleton = ensure_result_skeleton(args.output_dir, case_id, fields)
    except OSError as exc:
        skeleton = "failed（%s）" % exc

    summary = {
        "ok": True,
        "case_id": case_id,
        "contract_fields": fields,
        "input_files": len(inputs),
        "tools": {k: v["available"] for k, v in tools.items()},
        "result_skeleton": skeleton,
        "warnings": warnings,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
