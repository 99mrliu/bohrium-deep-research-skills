#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_all.py — archetype-interpreter 一键管线。

  python3 run_all.py --input /input --work /app/work --output /app/output

执行：
  1. partial-first：立即写 /app/output/result.json 骨架（契约字段占位）；
  2. 原型识别 + 原型专属确定性检查 -> /app/work/archetype_findings.json；
  3. 生成 /app/work/analysis_anchors.md（供 Agent 撰写五段结论的数值锚点）；
  4. 按 output_contract 字段名做关键词映射，把可由脚本负责的部分填入 result.json，
     其余保留 null 并在 limitations 中点名（诚实 partial）；
  5. 渲染 /app/output/report.md。

之后 Agent 的职责：读 anchors 与原始文件，撰写/补全结论字段，
用 result_contract.py update 填写并置 status。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import archetypes  # noqa: E402
import result_contract as rc  # noqa: E402

# 契约字段关键词 → findings 映射键
FIELD_MAP = [
    (("趋势", "trend"), "trend"),
    (("异常", "anomal", "离群"), "anomaly"),
    (("原因", "cause", "机理"), "cause"),
    (("复核", "核查", "recheck", "verify"), "recheck"),
    (("后续", "下一步", "建议", "next"), "next_experiment"),
    (("方案", "设计", "plan"), "plan"),
    (("依据", "风险", "risk", "evidence"), "evidence_risk"),
    (("确认", "confirm"), "confirmations"),
]


def build_anchors(report):
    """把 findings 转成人读锚点文本（数值全部来自脚本输出）。"""
    arch = report["archetype"]
    f = report["findings"]
    L = ["# 分析锚点（合成示例/真实运行均由脚本生成，可直接引用）",
         "", "- 识别原型: `%s`" % arch,
         "- 识别证据: `%s`" % json.dumps(report["detection_evidence"], ensure_ascii=False)]
    if arch == "bending_traces":
        ps = f.get("peak_stats", {})
        L += ["", "## 弯曲 traces",
              "- trace 数: %s" % f.get("n_traces"),
              "- 峰值 mean±std: %.4f ± %.4f (min=%.4f, max=%.4f)" % (
                  ps.get("mean", float("nan")), ps.get("std", float("nan")),
                  ps.get("min") or 0.0, ps.get("max") or 0.0),
              "- IQR 离群 traces: %s" % f.get("peak_outlier_traces"),
              "- 饱和 traces(平台≥5): %s" % f.get("saturated_traces(plateau>=5)"),
              "- 重复曲线组: %s" % f.get("duplicate_trace_groups"),
              "- 判定阈值: %s" % json.dumps(f.get("thresholds"), ensure_ascii=False)]
    elif arch == "iris_computational":
        L += ["", "## Iris 计算实验"]
        for es in f.get("estimator_stats", []):
            L.append("- estimator 列 %d: mean=%.4f std=%.4f min=%.4f max=%.4f values=%s"
                     % (es["estimator_col"], es["mean"], es["std"],
                        es["min"], es["max"], es["split_values"]))
        L.append("- 逐 split 差(col0-col1): %s, 符号一致: %s"
                 % (f.get("per_split_diff_col0_minus_col1"), f.get("sign_consistent")))
        if f.get("note"):
            L.append("- 注意: " + f["note"])
    elif arch == "cefixime_workbook":
        L += ["", "## Cefixime 工作簿"]
        for wb in f.get("workbooks", []):
            L.append("- 工作簿 %s: %d 个 sheet" % (wb["file"], len(wb.get("sheets", []))))
            for sh in wb.get("sheets", [])[:20]:
                L.append("  - sheet `%s`: 数值单元格 %d, 文本单元格 %d"
                         % (sh.get("name"), sh.get("numeric_cells"), sh.get("text_cells")))
        L.append("- PDF↔工作簿数值交叉命中数: %s" % f.get("cross_hit_count"))
        L.append("- 单位记号计数: %s" % json.dumps(f.get("unit_tokens"), ensure_ascii=False))
    else:
        L += ["", "## 通用表格统计",
              "```json", json.dumps(f, ensure_ascii=False, indent=2)[:3000], "```"]
    return "\n".join(L) + "\n"


def auto_fill(res, report):
    """按契约字段名关键词，把脚本可直接负责的内容写入对应字段。"""
    arch = report["archetype"]
    f = report["findings"]
    blocks = {
        "trend": "（脚本锚点）原型=%s；详见 /app/work/analysis_anchors.md 与 "
                 "archetype_findings.json，趋势判读需 Agent 结合 task.md 完成。" % arch,
        "anomaly": json.dumps({
            "bending": {"outliers": f.get("peak_outlier_traces"),
                        "saturated": f.get("saturated_traces(plateau>=5)"),
                        "duplicates": f.get("duplicate_trace_groups")},
            "iris": {"per_split_diff": f.get("per_split_diff_col0_minus_col1"),
                     "sign_consistent": f.get("sign_consistent")},
            "cefixime": {"cross_hit_count": f.get("cross_hit_count")},
            "generic": f.get("tables", [])[:5]}, ensure_ascii=False).replace(
                '{"' + {"bending_traces": "bending", "iris_computational": "iris",
                        "cefixime_workbook": "cefixime"}.get(arch, "generic") + '"', '{"data"'),
        "cause": None,  # 原因判断必须经排除过程，由 Agent 完成，脚本不猜
        "recheck": "可由第二人执行的复核动作: 重跑 run_all.py 复算全部锚点数值；"
                   "回查 archetype_findings.json 中列出的具体文件名与阈值；"
                   "对离群/饱和/重复对象逐一回原始文件核对。",
        "next_experiment": None,
        "plan": None,
        "evidence_risk": "本结果依据: run_all.py 对 /input 的确定性重算 "
                         "(见 archetype_findings.json 阈值字段)；风险: 原型误识别、"
                         "单位/方法歧义未消解——须在结论中显式标注。",
        "confirmations": "需专家确认项: (1) 原型识别是否正确; (2) 单位与量程约定; "
                         "(3) 饱和/重复读数是否为设备真实行为。",
    }
    filled, unfilled = [], []
    for field in [k for k in res if k not in ("case_id", "status", "limitations",
                                              "sources", "uncertainty", "change_records")]:
        if res[field] not in (None, "", [], {}):
            continue
        fl = str(field).lower()
        target = None
        for keys, name in FIELD_MAP:
            if any(k in fl for k in keys):
                target = name
                break
        val = blocks.get(target) if target else None
        if val:
            res[field] = val
            filled.append(field)
        else:
            unfilled.append(field)
    return filled, unfilled


def render_report(res, report):
    L = ["# 实验结果解释与异常分析 — 运行报告",
         "", "- case_id: `%s`" % res.get("case_id"),
         "- status: **%s**" % res.get("status"),
         "- 原型: `%s`" % report["archetype"], "",
         "## 契约字段概览", ""]
    for k, v in res.items():
        if k in ("case_id", "status"):
            continue
        s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        L.append("### %s" % k)
        L.append(s[:800] if s else "_(未填写)_")
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    os.makedirs(a.output, exist_ok=True)
    result_path = os.path.join(a.output, "result.json")
    case_path = os.path.join(a.input, "case.json")

    # 1) partial-first
    if os.path.exists(case_path):
        case = json.load(open(case_path, encoding="utf-8"))
    else:
        case = {"case_id": "unknown_case", "output_contract": {}}
    res = rc.init_result(case, note="run_all: partial-first 骨架")
    json.dump(res, open(result_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # 2) 原型识别与检查
    report = archetypes.run(a.input, work_dir=a.work)
    with open(os.path.join(a.work, "archetype_findings.json"), "w", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)

    # 3) 锚点
    anchors = build_anchors(report)
    with open(os.path.join(a.work, "analysis_anchors.md"), "w", encoding="utf-8") as fp:
        fp.write(anchors)

    # 4) 自动填充可负责字段
    filled, unfilled = auto_fill(res, report)
    res["sources"].append("run_all.py 重算输出: /app/work/archetype_findings.json")
    res["sources"].append("分析锚点: /app/work/analysis_anchors.md")
    res["uncertainty"].append("原型识别基于文件形态与关键词启发式，存在误识别风险")
    if unfilled:
        res["status"] = "partial"
        res["limitations"] = [
            "以下契约字段需 Agent 阅读锚点与原始材料后撰写（脚本不猜测）: %s"
            % ", ".join(unfilled)]
    else:
        res["status"] = "success"
        res["limitations"] = []
    res["change_records"].append(
        "run_all 完成: 原型=%s, 自动填充字段=%s, 待撰写字段=%s"
        % (report["archetype"], filled, unfilled))
    json.dump(res, open(result_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # 5) 报告
    with open(os.path.join(a.output, "report.md"), "w", encoding="utf-8") as fp:
        fp.write(render_report(res, report))
    print("[run_all] archetype=%s filled=%d unfilled=%d status=%s"
          % (report["archetype"], len(filled), len(unfilled), res["status"]))
    print("[run_all] outputs:", result_path, "and report.md")


if __name__ == "__main__":
    main()
