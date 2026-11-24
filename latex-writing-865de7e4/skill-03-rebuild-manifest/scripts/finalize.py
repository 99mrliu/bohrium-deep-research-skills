#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""finalize.py — 装配 /app/output：manifest、重建报告、源码 zip、result.json。

仅使用 Python3 标准库。职责：
  1. 读取 /input/case.json（缺失时遍历 /input 并如实降级，case_id 置 null）；
  2. 归一化解析 output_contract 的多种历史方言：
       a. {字段: {type, required}} 字典；
       b. JSON Schema（properties/required）；
       c. 字段名列表；
       d. 自然语言描述（best-effort 提取 `反引号标识符` 或列表行首标识符，
          并在 uncertainty 中声明为尽力解析）；
     逐字段镜像输出；字段值取自 Agent 写入的 <workdir>/result_fields.json，
     缺材料/未填时给诚实的 null 并在 field_notes 说明，绝不填充编造值；
  3. 复制 /app/work 下的真实产物（manifest、rebuild 报告、源码 zip）到 /app/output；
  4. 生成 result.json：case_id、契约字段镜像、status、sources、uncertainty、
     artifacts（只列真实存在的文件）。

status 据实判定：complete / partial / failed / blocked。

用法：
  python3 finalize.py --input /input --workdir /app/work --outdir /app/output
"""
import argparse
import json
import os
import re
import shutil
import sys
import time


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_contract(raw):
    """归一化 output_contract。返回 (fields, notes)。

    fields: [{"name":..., "type":...|None, "required":...|None}]
    关键：{字段:{type,required}} 方言只取“字段名”，绝不把 {type,required}
    当作样例值输出成 {}。
    """
    fields, notes = [], []
    if raw is None:
        notes.append("case.json 未提供 output_contract，契约字段为空")
        return fields, notes

    if isinstance(raw, list):
        notes.append("output_contract 按字段名列表方言解析")
        for item in raw:
            if isinstance(item, str):
                fields.append({"name": item, "type": None, "required": None})
            elif isinstance(item, dict) and "name" in item:
                fields.append({"name": item["name"],
                               "type": item.get("type"),
                               "required": item.get("required")})
            else:
                notes.append("列表元素无法识别为字段名：%r（已跳过）" % (item,))
        return fields, notes

    if isinstance(raw, dict):
        props = raw.get("properties")
        if isinstance(props, dict):  # JSON Schema 方言
            notes.append("output_contract 按 JSON Schema 方言解析")
            req = raw.get("required")
            req = set(req) if isinstance(req, list) else set()
            for name, spec in props.items():
                fields.append({"name": name,
                               "type": (spec or {}).get("type") if isinstance(spec, dict) else None,
                               "required": name in req})
            return fields, notes
        notes.append("output_contract 按 {字段: {type, required}} 方言解析")
        for name, spec in raw.items():
            if isinstance(spec, dict):
                fields.append({"name": name,
                               "type": spec.get("type"),
                               "required": spec.get("required")})
            else:
                fields.append({"name": name, "type": None, "required": None})
                notes.append("字段 %s 的声明不是 {type, required} 结构，按字段名收录" % name)
        return fields, notes

    if isinstance(raw, str):
        notes.append("output_contract 按自然语言方言尽力解析（best-effort，"
                     "可能遗漏或误收，见 uncertainty）")
        names = re.findall(r"`([A-Za-z_][\w.\-]*)`", raw)
        if not names:
            for line in raw.splitlines():
                m = re.match(r"\s*(?:[-*•]|\d+[.、)])\s*([A-Za-z_][\w.\-]*)", line)
                if m:
                    names.append(m.group(1))
        for n in dict.fromkeys(names):
            fields.append({"name": n, "type": None, "required": None})
        if not fields:
            notes.append("自然语言契约中未能提取任何字段名")
        return fields, notes

    notes.append("output_contract 类型无法识别：%s" % type(raw).__name__)
    return fields, notes


def copy_if_exists(src, dst_dir, artifacts, notes, label):
    if src and os.path.isfile(src):
        dst = os.path.join(dst_dir, os.path.basename(src))
        shutil.copy2(src, dst)
        artifacts.append({"path": os.path.relpath(dst, dst_dir).replace(os.sep, "/")
                          if False else os.path.basename(dst),
                          "label": label,
                          "bytes": os.path.getsize(dst)})
        return dst
    notes.append("%s 不存在，未复制：%s" % (label, src))
    return None


def main():
    ap = argparse.ArgumentParser(description="装配 /app/output 并生成 result.json")
    ap.add_argument("--input", default="/input", help="输入目录（case.json、task.md）")
    ap.add_argument("--workdir", default="/app/work", help="工作目录")
    ap.add_argument("--outdir", default="/app/output", help="交付目录")
    args = ap.parse_args()

    input_dir = os.path.abspath(args.input)
    workdir = os.path.abspath(args.workdir)
    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)

    uncertainty = []
    sources = []
    artifacts = []

    # ---- case.json / task.md ----
    case = {}
    case_path = os.path.join(input_dir, "case.json")
    if os.path.isfile(case_path):
        try:
            case = load_json(case_path)
            sources.append(case_path)
        except Exception as exc:
            uncertainty.append("case.json 解析失败：%s" % exc)
    else:
        uncertainty.append("case.json 缺失：已遍历 /input 如实降级，case_id 置 null")
        if os.path.isdir(input_dir):
            for fn in sorted(os.listdir(input_dir)):
                sources.append(os.path.join(input_dir, fn))
    task_path = os.path.join(input_dir, "task.md")
    if os.path.isfile(task_path):
        sources.append(task_path)
    else:
        uncertainty.append("task.md 缺失")

    case_id = case.get("case_id") if isinstance(case, dict) else None

    # ---- 契约归一化 + 字段镜像（值由 Agent 写入 result_fields.json）----
    raw_contract = case.get("output_contract") if isinstance(case, dict) else None
    fields, notes = normalize_contract(raw_contract)
    uncertainty.extend(notes)

    agent_fields = {}
    af_path = os.path.join(workdir, "result_fields.json")
    if os.path.isfile(af_path):
        try:
            agent_fields = load_json(af_path)
            sources.append(af_path)
        except Exception as exc:
            uncertainty.append("result_fields.json 解析失败：%s（契约字段按 null 处理）" % exc)
    else:
        if fields:
            uncertainty.append("未找到 %s（Agent 尚未填写契约字段值），"
                               "契约字段镜像为 null" % af_path)

    output_fields = {}
    field_notes = {}
    for fd in fields:
        name = fd["name"]
        if name in agent_fields:
            output_fields[name] = agent_fields[name]
        else:
            output_fields[name] = None
            field_notes[name] = "缺材料或 Agent 未填写，按诚实空值输出"

    # ---- 复制真实产物 ----
    manifest_json = os.path.join(workdir, "manifest", "manifest.json")
    manifest_md = os.path.join(workdir, "manifest", "manifest.md")
    rebuild_json = os.path.join(workdir, "rebuild", "rebuild_report.json")
    rebuild_md = os.path.join(workdir, "rebuild", "rebuild_report.md")
    src_zip = os.path.join(workdir, "rebuild", "source_snapshot.zip")

    copy_if_exists(manifest_json, outdir, artifacts, uncertainty, "manifest.json")
    copy_if_exists(manifest_md, outdir, artifacts, uncertainty, "manifest.md")
    copy_if_exists(rebuild_json, outdir, artifacts, uncertainty, "rebuild_report.json")
    copy_if_exists(rebuild_md, outdir, artifacts, uncertainty, "rebuild_report.md")
    # 评测运行时允许二进制产物：源码 zip 如实交付
    copy_if_exists(src_zip, outdir, artifacts, uncertainty, "source_snapshot.zip")

    # ---- status 据实判定 ----
    verdict = None
    compile_ok = None
    if os.path.isfile(manifest_json):
        try:
            man = load_json(manifest_json)
            compile_ok = man.get("build", {}).get("compile_ok")
            sources.append(manifest_json)
        except Exception:
            pass
    if os.path.isfile(rebuild_json):
        try:
            rep = load_json(rebuild_json)
            verdict = rep.get("verdict")
            sources.append(rebuild_json)
        except Exception:
            pass

    if not os.path.isfile(case_path) and not fields:
        status = "blocked"
        uncertainty.append("无 case.json 且无契约可镜像，仅能交付已生成的产物")
    elif not os.path.isfile(manifest_json):
        status = "failed"
        uncertainty.append("manifest 未生成（capture 未运行或失败）")
    elif compile_ok is False:
        status = "partial"
        uncertainty.append("基线编译未通过，manifest 为部分结果")
    elif verdict is None:
        status = "partial"
        uncertainty.append("重建比对未执行（rebuild 未运行），仅有基线 manifest")
    elif verdict == "inconclusive":
        status = "partial"
        uncertainty.append("重建判定为 inconclusive（工具缺失或文本不可比）")
    else:
        status = "complete"

    result = {
        "case_id": case_id,
        "status": status,
        "output_fields": output_fields,
        "field_notes": field_notes,
        "contract_normalization": {
            "fields": fields,
            "notes": notes,
        },
        "rebuild_verdict": verdict,
        "sources": sources,
        "uncertainty": uncertainty,
        "artifacts": artifacts,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generator": "finalize.py (latex-rebuild-manifest skill)",
    }
    with open(os.path.join(outdir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("[finalize] status=%s verdict=%s artifacts=%d -> %s"
          % (status, verdict, len(artifacts), outdir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
