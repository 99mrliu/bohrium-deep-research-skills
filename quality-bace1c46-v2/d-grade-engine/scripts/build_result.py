#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装最终交付 result.json 与 grade_report.md。

用法:
    python3 build_result.py --workdir /app/work --output-dir /app/output --case /input/case.json

行为契约:
    - case_id: 在 case.json 中递归防御性查找 "case_id" (退而求其次 "id")。
    - output_contract 镜像: 在 case.json 中递归防御性查找
      output_contract / contract / output_fields / required_fields,
      全部镜像进 result.json; 契约声明但本技能无法填充的字段以 null 占位
      并写入 uncertainties (绝不伪造)。
    - status 规则:
        success — 期望文献全部完成等级推导;
        partial — 部分文献缺判定 (列出是哪些), 或零判定 (附解释);
        failed  — 组装过程发生未预期错误 (兜底, 仍尽量写出骨架结果)。
    - 读取 workdir/grades.json (必需) 与 workdir/reliability.json (可选),
      workdir/change_records.jsonl (可选), 并追加本次组装记录。
    - 输出: output-dir/result.json, output-dir/grade_report.md。

退出码: 0 = 正常完成 (含 partial 状态); 1 = 运行期错误; 2 = 用法/输入文件错误。
仅依赖 Python 3 标准库。
"""

import argparse
import json
import os
import sys
import datetime

EXIT_OK, EXIT_ERROR, EXIT_USAGE = 0, 1, 2

CONTRACT_KEYS = ("output_contract", "contract", "output_fields", "required_fields")
DOC_LIST_KEYS = ("documents", "docs", "papers", "items", "studies")
DOC_ID_KEYS = ("doc_id", "id", "document_id")


def log(msg):
    sys.stderr.write("[build_result] %s\n" % msg)


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def deep_find(obj, keys):
    """递归收集 obj 中所有名为 keys 之一的值 (list of (path, value))。"""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys:
                found.append((k, v))
            found.extend(deep_find(v, keys))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(deep_find(item, keys))
    return found


def extract_case_id(case):
    for _, v in deep_find(case, ("case_id",)):
        if isinstance(v, str) and v:
            return v
    for _, v in deep_find(case, ("id",)):
        if isinstance(v, str) and v:
            return v
    return "unknown_case"


def extract_expected_docs(case):
    """从 case.json 中递归查找文献列表; 返回 doc_id 列表 (可能为空)。"""
    for _, v in deep_find(case, DOC_LIST_KEYS):
        if isinstance(v, list):
            ids = []
            for item in v:
                if isinstance(item, dict):
                    for dk in DOC_ID_KEYS:
                        if isinstance(item.get(dk), str) and item[dk]:
                            ids.append(item[dk])
                            break
                elif isinstance(item, str) and item:
                    ids.append(item)
            if ids:
                return ids
    return []


def collect_contract(case):
    """镜像 output_contract 及其声明字段名集合。"""
    mirror, declared = {}, set()
    for path, value in deep_find(case, CONTRACT_KEYS):
        mirror.setdefault(path, []).append(value)
        # 从找到的契约结构中再挖 required/output 字段名
        for _, names in deep_find(value, ("required_fields", "output_fields")):
            if isinstance(names, list):
                for n in names:
                    if isinstance(n, str):
                        declared.add(n)
                    elif isinstance(n, dict):
                        for nk in ("name", "field", "id"):
                            if isinstance(n.get(nk), str):
                                declared.add(n[nk])
        if isinstance(value, dict):
            rf = value.get("required_fields") or value.get("output_fields")
            if isinstance(rf, list):
                for n in rf:
                    if isinstance(n, str):
                        declared.add(n)
                    elif isinstance(n, dict):
                        for nk in ("name", "field", "id"):
                            if isinstance(n.get(nk), str):
                                declared.add(n[nk])
    return mirror, sorted(declared)


def load_json_file(path, required=True):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        if required:
            log("必需文件不存在: %s" % path)
            sys.exit(EXIT_USAGE)
        return None
    except (OSError, json.JSONDecodeError) as e:
        if required:
            log("文件读取/解析失败: %s: %s" % (path, e))
            sys.exit(EXIT_USAGE)
        log("可选文件读取失败 (忽略): %s: %s" % (path, e))
        return None


def read_change_records(workdir):
    path = os.path.join(workdir, "change_records.jsonl")
    recs = []
    if not os.path.exists(path):
        return recs
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        recs.append(json.loads(line))
                    except json.JSONDecodeError:
                        recs.append({"raw": line, "note": "unparseable_change_record"})
    except OSError as e:
        log("change_records 读取失败 (忽略): %s" % e)
    return recs


def render_grade_report(result):
    lines = ["# 质量分级报告 (grade report)", "",
             "- case_id: `%s`" % result["case_id"],
             "- status: **%s**" % result["status"],
             "- scale_version: `%s`" % result["grades"].get("scale_version", "N/A"),
             "- 生成时间: %s" % result["generated_at"], ""]
    for doc in result["grades"]["docs"]:
        if doc.get("overall_grade") is None:
            lines.append("## %s — 推导失败: %s" % (doc["doc_id"], doc.get("error", "unknown")))
            continue
        lines.append("## %s → 总评: **%s**" % (doc["doc_id"], doc["overall_grade"]))
        for v in doc.get("dimension_verdicts", []):
            lines.append("  - `%s` = %s" % (v["dimension"], v["level"]))
        for did, dg in doc.get("domain_grades", {}).items():
            lines.append("  - 域 `%s` = **%s** (规则 %s)" % (
                did, dg.get("grade"), dg.get("derivation", {}).get("rule_id")))
        ov = [e for e in doc.get("derivation_chain", []) if e.get("stage") == "overall"]
        if ov:
            lines.append("  - 总评推导: 规则 `%s` — %s" % (ov[0]["rule_id"], ov[0].get("description_zh")))
        if doc.get("missing_dimensions"):
            lines.append("  - ⚠ 缺失维度判定: %s" % ", ".join(doc["missing_dimensions"]))
        lines.append("")
    rel = result.get("reliability")
    if rel:
        lines += ["## 双人评定一致性", "",
                  "- 一致率: %.1f%%" % rel["agreement_pct"],
                  "- Cohen's kappa: %s (%s)" % (rel["kappa_display"], rel["kappa_interpretation"]),
                  "- 分歧条目: %d; 未配对判定: %d" % (rel["disagreement_count"], rel["unpaired_count"]), ""]
    if result["uncertainties"]:
        lines.append("## 不确定性")
        for u in result["uncertainties"]:
            lines.append("- %s" % u)
        lines.append("")
    return "\n".join(lines)


def assemble(workdir, output_dir, case_path):
    case = load_json_file(case_path, required=True)
    case_id = extract_case_id(case)
    contract_mirror, declared_fields = collect_contract(case)
    expected_docs = extract_expected_docs(case)

    uncertainties = []
    grades_path = os.path.join(workdir, "grades.json")
    grades_data = load_json_file(grades_path, required=True)
    docs = grades_data.get("docs", [])
    graded_ids = {d["doc_id"] for d in docs if d.get("overall_grade") is not None}
    any_verdicts = any(d.get("dimension_verdicts") for d in docs)

    if not expected_docs:
        expected_docs = sorted(graded_ids)
        uncertainties.append("case.json 中未找到文献列表; 期望文献集回退为 grades.json 实际推导的文献。")

    missing_docs = [d for d in expected_docs if d not in graded_ids]
    for d in docs:
        if d.get("missing_dimensions"):
            uncertainties.append("%s 缺少维度判定: %s (相关规则按兜底/弃权逻辑处理)"
                                 % (d["doc_id"], ", ".join(d["missing_dimensions"])))
    rej_path = os.path.join(workdir, "rejected_verdicts.jsonl")
    rejected = []
    if os.path.exists(rej_path):
        with open(rej_path, "r", encoding="utf-8") as f:
            rejected = [json.loads(x) for x in f if x.strip()]
    if rejected:
        uncertainties.append("有 %d 条判定行被拒绝 (未知维度/等级或重复), 详见 rejected_verdicts.jsonl。"
                             % len(rejected))

    # status 规则
    if not any_verdicts:
        status = "partial"
        status_reason = "零有效判定: verdicts 文件为空或全部行被拒绝, 无法派生任何等级。"
    elif missing_docs:
        status = "partial"
        status_reason = "以下文献缺少判定、未能派生等级: %s" % ", ".join(missing_docs)
    else:
        status = "success"
        status_reason = "全部期望文献均已派生等级。"

    reliability = None
    rel_data = load_json_file(os.path.join(workdir, "reliability.json"), required=False)
    if rel_data:
        ov = rel_data.get("overall", {})
        kappa = ov.get("kappa")
        reliability = {
            "paired": rel_data.get("paired", 0),
            "agreement_pct": ov.get("agreement_pct", 0.0),
            "kappa": kappa,
            "kappa_display": ("%.4f" % kappa) if kappa is not None else "N/A",
            "kappa_interpretation": ov.get("kappa_interpretation", ""),
            "disagreement_count": len(rel_data.get("disagreements", [])),
            "unpaired_count": len(rel_data.get("unpaired", [])),
        }
        if rel_data.get("unpaired"):
            uncertainties.append("双人比对存在 %d 条未配对判定 (仅一方给出), 见 reliability.json。"
                                 % len(rel_data["unpaired"]))

    change_records = read_change_records(workdir)
    change_records.append({"ts": now_iso(), "actor": "d-grade-engine/scripts/build_result.py",
                           "action": "assemble_result",
                           "detail": "status=%s; docs_graded=%d/%d"
                                     % (status, len(graded_ids), len(expected_docs))})

    result = {
        "case_id": case_id,
        "skill": "d-grade-engine",
        "scale_version": grades_data.get("scale_version"),
        "status": status,
        "status_reason": status_reason,
        "output_contract_mirror": contract_mirror,
        "grades": {
            "scale_version": grades_data.get("scale_version"),
            "docs": docs,
            "rejected_count": grades_data.get("rejected_count", len(rejected)),
        },
        "reliability": reliability,
        "uncertainties": uncertainties,
        "change_records": change_records,
        "generated_at": now_iso(),
    }
    # 契约声明字段镜像: 缺失者置 null 并记入不确定性 (绝不伪造值)
    for field in declared_fields:
        if field not in result:
            result[field] = None
            uncertainties.append("output_contract 声明字段 %r 本技能无法提供, 以 null 占位。" % field)

    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(os.path.join(output_dir, "grade_report.md"), "w", encoding="utf-8") as f:
        f.write(render_grade_report(result))
    log("完成: status=%s; 输出于 %s" % (status, output_dir))
    return EXIT_OK


def main(argv=None):
    ap = argparse.ArgumentParser(description="组装 result.json 与 grade_report.md")
    ap.add_argument("--workdir", required=True, help="工作目录 (derive/second_rater 的输出所在)")
    ap.add_argument("--output-dir", required=True, help="交付目录 (result.json 写于此)")
    ap.add_argument("--case", required=True, help="/input/case.json 路径")
    args = ap.parse_args(argv)  # argparse 用法错误自动 exit 2
    return assemble(args.workdir, args.output_dir, args.case)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        log("未预期错误: %s" % e)
        # 兜底: 尽量写出 failed 骨架结果
        try:
            out_dir = None
            for i, a in enumerate(sys.argv):
                if a == "--output-dir" and i + 1 < len(sys.argv):
                    out_dir = sys.argv[i + 1]
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
                skeleton = {"case_id": "unknown_case", "status": "failed",
                            "status_reason": "组装过程未预期错误: %s" % e,
                            "grades": {"docs": []}, "reliability": None,
                            "uncertainties": [str(e)], "change_records": [],
                            "generated_at": now_iso()}
                with open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as f:
                    json.dump(skeleton, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        sys.exit(EXIT_ERROR)
