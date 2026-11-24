#!/usr/bin/env python3
"""finalize.py — 装配 /app/output（事实来源闸门·第 3 步）。

只做确定性装配，不做写作决策：
  * 稿件拷贝（优先 --draft / /app/output 内 Agent 改好的 .tex；否则从输入目录
    拷贝原稿并在 uncertainty 中注明"未经修改的拷贝"）
  * source_map.md（已存在则保留，否则按 coverage 生成待补全骨架）
  * coverage.json / coverage.md 拷贝
  * change_log.md（Agent 已写则保留，否则生成待填模板）
  * result.json：case_id 原样复制 + output_contract 逐字段镜像（四种方言
    归一化，缺材料给诚实 null）+ status/sources/uncertainty/artifacts
    （只列真实存在的文件）

用法:
    python3 finalize.py --case /input/case.json --task /input/task.md \
        --work /app/work --output /app/output [--draft /app/output/main.tex]
"""
import argparse
import glob
import json
import os
import re
import shutil
import sys

FIELD_LINE_RE = re.compile(
    r"^\s*(?:[-*•]|\d+[.)、])?\s*`?([A-Za-z_][A-Za-z0-9_]*)`?\s*[:：,，(（\-—]")

# 契约字段名 -> 已知产物别名组
ALIAS_GROUPS = [
    ({"draft", "revised_draft", "revised_tex", "revised_manuscript",
      "manuscript", "main", "tex", "paper", "latex", "revised_latex"},
     "__DRAFT__"),
    ({"source_map", "sourcemap", "source_mapping", "provenance_map",
      "provenance"}, "source_map.md"),
    ({"coverage", "coverage_report", "coverage_md", "audit",
      "audit_report", "coverage_json"}, "coverage.md"),
    ({"change_log", "changelog", "changes", "revision_log"},
     "change_log.md"),
    ({"materials_index", "material_index", "materials_overview"},
     "__MATERIALS__"),
    ({"facts", "facts_jsonl", "fact_db"}, "__FACTS__"),
]


def norm_name(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def normalize_contract(contract):
    """四方言归一化 -> (dialect, [field_name, ...])。

    方言: typed_dict {字段: {type, required}} / natural_language /
    json_schema / name_list / none。
    """
    if contract is None:
        return "none", []
    if isinstance(contract, dict):
        if isinstance(contract.get("properties"), dict):
            return "json_schema", list(contract["properties"].keys())
        if contract and all(isinstance(v, dict) and "type" in v
                            for v in contract.values()):
            # typed_dict：取字段名，绝不把 {type, required} 当样例值
            return "typed_dict", list(contract.keys())
        return "typed_dict", list(contract.keys())
    if isinstance(contract, list):
        names = []
        for item in contract:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict) and isinstance(item.get("name"), str):
                names.append(item["name"])
        return "name_list", names
    if isinstance(contract, str):
        names = []
        for line in contract.splitlines():
            m = FIELD_LINE_RE.match(line)
            if m:
                names.append(m.group(1))
        return "natural_language", names
    return "none", []


def fill_field(field, file_map):
    """按别名组/文件名干匹配产物；找不到返回 None（诚实空值）。"""
    nf = norm_name(field)
    for aliases, target in ALIAS_GROUPS:
        if nf in aliases and target in file_map:
            return file_map[target]
    for key, rel in file_map.items():
        if key.startswith("__"):
            continue
        if norm_name(os.path.splitext(key)[0]) == nf:
            return rel
    return None


def find_draft(output_dir, input_dir, draft_arg, uncertainty):
    """定位稿件，返回 (源路径, 是否 Agent 修改版) 或 (None, False)。"""
    if draft_arg:
        if os.path.isfile(draft_arg):
            return draft_arg, True
        uncertainty.append("--draft 指定的稿件不存在: %s" % draft_arg)
    outs = sorted(glob.glob(os.path.join(output_dir, "*.tex")),
                  key=os.path.getmtime, reverse=True)
    if outs:
        return outs[0], True
    if os.path.isdir(input_dir):
        cands = []
        for root, _dirs, files in os.walk(input_dir):
            for fn in files:
                if fn.endswith(".tex"):
                    cands.append(os.path.join(root, fn))
        if cands:
            pref = [p for p in cands
                    if re.search(r"main|draft|manuscript|paper",
                                 os.path.basename(p), re.I)]
            chosen = (pref or sorted(cands))[0]
            uncertainty.append(
                "/app/output 中无 Agent 修改稿；已拷贝输入目录原稿 %s "
                "（未经修改的拷贝，仅保证交付完整）" % chosen)
            return chosen, False
    uncertainty.append("未找到任何 .tex 稿件")
    return None, False


def main():
    ap = argparse.ArgumentParser(description="装配 /app/output 交付物")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--task", default="/input/task.md")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--draft", default=None)
    args = ap.parse_args()

    os.makedirs(args.output, exist_ok=True)
    uncertainty, gaps = [], []

    # ---- case.json ----
    case_id, contract, dialect, fields = None, None, "none", []
    if os.path.isfile(args.case):
        try:
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
            case_id = case.get("case_id")
            contract = case.get("output_contract")
            dialect, fields = normalize_contract(contract)
            if case_id is None:
                uncertainty.append("case.json 中无 case_id 字段")
        except (json.JSONDecodeError, OSError) as e:
            gaps.append("case.json 解析失败: %s" % e)
            uncertainty.append("case.json 不可解析，case_id 与契约字段给 null")
    else:
        gaps.append("case.json 不存在: %s" % args.case)
        uncertainty.append("case.json 缺失，case_id 与契约字段给 null")

    if not os.path.isfile(args.task):
        gaps.append("task.md 不存在: %s" % args.task)

    # ---- 取证/审计产物 ----
    facts_dir = os.path.join(args.work, "facts")
    audit_dir = os.path.join(args.work, "audit")
    extraction = {}
    er_path = os.path.join(facts_dir, "extraction_report.json")
    if os.path.isfile(er_path):
        try:
            with open(er_path, "r", encoding="utf-8") as f:
                extraction = json.load(f)
        except (json.JSONDecodeError, OSError):
            uncertainty.append("extraction_report.json 不可解析")
    else:
        uncertainty.append("未找到 matscan 产物（%s），sources 信息不全"
                           % er_path)
    for g in extraction.get("gaps", []):
        gaps.append("matscan: " + g)

    coverage = None
    cov_path = os.path.join(audit_dir, "coverage.json")
    if os.path.isfile(cov_path):
        try:
            with open(cov_path, "r", encoding="utf-8") as f:
                coverage = json.load(f)
            shutil.copyfile(cov_path, os.path.join(args.output,
                                                   "coverage.json"))
            md = os.path.join(audit_dir, "coverage.md")
            if os.path.isfile(md):
                shutil.copyfile(md, os.path.join(args.output, "coverage.md"))
        except (json.JSONDecodeError, OSError) as e:
            uncertainty.append("coverage.json 拷贝失败: %s" % e)
    else:
        uncertainty.append("未找到 texaudit 产物，coverage 报告缺失")

    # ---- 稿件拷贝 ----
    draft_rel = None
    draft_src, agent_edited = find_draft(args.output, args.input,
                                         args.draft, uncertainty)
    if draft_src:
        base = os.path.basename(draft_src)
        dest = os.path.join(args.output, base)
        if os.path.abspath(draft_src) != os.path.abspath(dest):
            shutil.copyfile(draft_src, dest)
        draft_rel = base
    else:
        gaps.append("无稿件可交付")

    # ---- change_log.md：Agent 写的保留，否则生成模板 ----
    cl_path = os.path.join(args.output, "change_log.md")
    if not os.path.isfile(cl_path):
        with open(cl_path, "w", encoding="utf-8") as f:
            f.write("# 修改记录（change_log）\n\n"
                    "> 本文件为 finalize.py 生成的待填模板。请 Agent 逐条记录"
                    "事实性修改：位置、原文、改为、依据（材料 file:line）、"
                    "处置类别（matched 采用 / unmatched 标注或删除 / "
                    "conflict 裁定口径）。\n\n"
                    "| # | 稿件位置 | 原文 | 改为 | 依据（材料 file:line） | 类别 |\n"
                    "| --- | --- | --- | --- | --- | --- |\n"
                    "| （待填） | | | | | |\n")
        uncertainty.append("change_log.md 为模板，Agent 尚未填写修改记录")

    # ---- source_map.md：Agent 写的保留，否则按 coverage 生成骨架 ----
    sm_path = os.path.join(args.output, "source_map.md")
    if not os.path.isfile(sm_path):
        lines = ["# 事实 ↔ 来源映射（source_map）", "",
                 "> 骨架由 finalize.py 依据 coverage 生成；「Agent 确认」列"
                 "由 Agent 在改稿后逐条补全（采用 / 标注材料外 / 裁定口径 / 删除）。",
                 "",
                 "| 稿件位置 | 类型 | 稿件值 | 判定 | 材料锚点 | Agent 确认 |",
                 "| --- | --- | --- | --- | --- | --- |"]
        if coverage:
            for e in coverage.get("entries", []):
                anchors = "; ".join(e.get("material_anchors", [])) or "—"
                unit = e.get("unit", "")
                v = str(e["value"]) + (unit if unit in ("", "%")
                                       else " " + unit)
                lines.append("| %s | %s | %s | %s | %s | （待确认） |" % (
                    e["draft_anchor"], e["type"], v, e["verdict"],
                    anchors.replace("|", "\\|")))
        else:
            lines.append("| （coverage 缺失，无法生成条目） | | | | | |")
        lines.append("")
        with open(sm_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        uncertainty.append("source_map.md 为骨架，Agent 尚未补全确认列")

    # ---- 契约字段镜像 ----
    file_map = {}
    if draft_rel:
        file_map["__DRAFT__"] = draft_rel
        file_map[draft_rel] = draft_rel
    for fn in ("source_map.md", "coverage.md", "change_log.md"):
        if os.path.isfile(os.path.join(args.output, fn)):
            file_map[fn] = fn
    if os.path.isfile(os.path.join(facts_dir, "materials_index.md")):
        file_map["__MATERIALS__"] = os.path.join("..", "work", "facts",
                                                 "materials_index.md")
    if os.path.isfile(os.path.join(facts_dir, "facts.jsonl")):
        file_map["__FACTS__"] = os.path.join("..", "work", "facts",
                                             "facts.jsonl")

    contract_values, null_fields = {}, []
    for field in fields:
        v = fill_field(field, file_map)
        if v is None:
            null_fields.append(field)
        contract_values[field] = v
    if null_fields:
        uncertainty.append(
            "以下契约字段无对应真实产物，按诚实空值给 null: %s"
            % ", ".join(null_fields))

    # ---- sources ----
    sources = []
    for m in extraction.get("materials_scanned", []):
        if m.get("status") == "ok":
            sources.append({"file": m["file"], "facts": m.get("facts", 0)})
    if draft_src:
        sources.append({"file": os.path.basename(draft_src),
                        "role": "draft",
                        "agent_edited": agent_edited})

    # ---- status ----
    blocking = [g for g in gaps]
    if draft_rel and coverage is not None and case_id is not None \
            and not blocking and not null_fields:
        status = "complete"
    elif draft_rel or coverage is not None:
        status = "partial"
    else:
        status = "failed"

    # ---- artifacts：只列真实存在的文件 ----
    artifacts = sorted(
        fn for fn in os.listdir(args.output)
        if os.path.isfile(os.path.join(args.output, fn)))
    if "result.json" not in artifacts:
        artifacts.append("result.json")

    result = {
        "case_id": case_id,
        "status": status,
        "contract_dialect": dialect,
        "sources": sources,
        "uncertainty": uncertainty,
        "gaps": gaps,
        "artifacts": artifacts,
    }
    # output_contract 逐字段镜像为顶层键；无契约时显式说明
    for k, v in contract_values.items():
        result[k] = v
    if not fields:
        result["output_contract_fields"] = []

    with open(os.path.join(args.output, "result.json"), "w",
              encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("finalize: status=%s 契约字段=%d（null=%d）artifacts=%d -> %s"
          % (status, len(fields), len(null_fields), len(artifacts),
             args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
