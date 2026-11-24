#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_gate.py — 上游真实性取证门禁：一键管线。

  python3 run_gate.py --input /input --work /app/work --output /app/output

1. partial-first 落 result.json 骨架；
2. 运行 F1-F8 取证检查 -> /app/work/forensics_report.json；
3. 生成 /app/work/authenticity_brief.md（人读取证简报）；
4. 按契约字段名映射预填 result.json（真实性相关字段），其余点名待撰写；
5. 输出 /app/output/report.md。

门禁原则：authenticity_findings 非空时，Agent 的每条下游结论都必须声明
它是否受各 finding 影响；verdict=PASS_WITH_FLAGS 时 status 不得直接 success，
除非 limitations 中逐条处置了 flags。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import forensics  # noqa: E402
import gate_result as gr  # noqa: E402

FIELD_MAP = [
    (("异常", "anomal"), "anomaly"),
    (("复核", "核查", "verify"), "recheck"),
    (("依据", "风险", "risk"), "evidence_risk"),
    (("确认", "confirm"), "confirmations"),
    (("数据", "质量", "真实", "authentic"), "data_quality"),
]


def brief(report):
    L = ["# 上游数据真实性取证简报", "",
         "- 文件数: %d" % report["n_files"],
         "- 门禁结论: **%s**" % report["verdict"], "",
         "## 取证发现（按严重度）", ""]
    if not report["authenticity_findings"]:
        L.append("（无发现：所有 F1-F8 检查通过）")
    for fnd in report["authenticity_findings"]:
        L.append("- [%s] %s: `%s`" % (fnd["severity"], fnd["kind"],
                                      json.dumps(fnd["detail"], ensure_ascii=False)[:300]))
    L += ["", "## 阈值声明",
          "- F1: " + report["F1_file_lineage"]["threshold"],
          "- F2/F3/F4: " + json.dumps(report["F2_F3_F4_table_checks"]["thresholds"],
                                      ensure_ascii=False),
          "- F5: " + report["F5_unit_ambiguity"]["threshold"],
          "- F6: " + report["F6_cross_file_overlap"]["threshold"],
          "- F7: " + report["F7_xlsx_structure"]["threshold"],
          "- F8: " + report["F8_matlab_params"]["threshold"]]
    return "\n".join(L) + "\n"


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
    case = json.load(open(case_path, encoding="utf-8")) if os.path.exists(case_path) \
        else {"case_id": "unknown_case", "output_contract": {}}

    cid, fields = gr.contract_of(case)
    res = {"case_id": cid, "status": "partial",
           "limitations": ["取证骨架已建立，真实性检查进行中"],
           "sources": [], "uncertainty": [], "change_records": ["run_gate partial-first"]}
    for f in fields:
        res[f] = None
    json.dump(res, open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    report = forensics.run(a.input)
    with open(os.path.join(a.work, "forensics_report.json"), "w", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)
    with open(os.path.join(a.work, "authenticity_brief.md"), "w", encoding="utf-8") as fp:
        fp.write(brief(report))

    flags_txt = json.dumps(report["authenticity_findings"], ensure_ascii=False)[:1500]
    blocks = {
        "anomaly": "（取证视角）数据级异常对象: " + (flags_txt if flags_txt != "[]" else "无"),
        "recheck": "第二人复核: 重跑 run_gate.py 比对 forensics_report.json；"
                   "对每个 finding 回原始文件按 F1-F8 阈值逐项复算。",
        "evidence_risk": "取证依据: F1-F8 检查（阈值见 forensics_report.json）；"
                         "风险: 取证只覆盖文件层与数值层签名，不能排除采集端系统性偏差。",
        "confirmations": "需专家确认: 饱和/重复读数是否为设备真实行为；单位歧义的正确约定；"
                         "隐藏 sheet 是否属于分析范围。",
        "data_quality": "门禁结论 %s；findings=%d 条，详见 authenticity_brief.md"
                        % (report["verdict"], len(report["authenticity_findings"])),
    }
    filled, unfilled = [], []
    for f in fields:
        fl = f.lower()
        val = None
        for keys, name in FIELD_MAP:
            if any(k in fl for k in keys):
                val = blocks.get(name)
                break
        if val is None:
            val = blocks["data_quality"] if "质量" in f else None
        if val:
            res[f] = val
            filled.append(f)
        else:
            unfilled.append(f)
    res["sources"] += ["forensics_report.json (F1-F8 取证输出)",
                       "authenticity_brief.md (人读简报)"]
    res["uncertainty"].append("取证检查基于签名启发式，false positive/negative 均可能；"
                              "finding 须由 Agent 回原始文件确认后再写进结论")
    if report["verdict"] == "PASS_WITH_FLAGS":
        res["uncertainty"].append("门禁 PASS_WITH_FLAGS：下游结论须逐条声明是否受 findings 影响")
    if unfilled:
        res["limitations"] = ["以下契约字段需 Agent 结合取证简报与原始材料撰写: "
                              + ", ".join(unfilled)]
    else:
        res["status"] = "success" if report["verdict"] == "PASS" else "partial"
        if res["status"] == "partial":
            res["limitations"] = ["门禁存在 flags，须逐条处置后方可 success"]
        else:
            res["limitations"] = []
    res["change_records"].append("run_gate 完成: verdict=%s findings=%d filled=%s"
                                 % (report["verdict"],
                                    len(report["authenticity_findings"]), filled))
    json.dump(res, open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    with open(os.path.join(a.output, "report.md"), "w", encoding="utf-8") as fp:
        fp.write("# 取证运行报告\n\n- case_id: `%s`\n- status: %s\n- verdict: %s\n\n"
                 % (cid, res["status"], report["verdict"])
                 + brief(report))
    print("[run_gate] verdict=%s findings=%d filled=%d unfilled=%d status=%s"
          % (report["verdict"], len(report["authenticity_findings"]),
             len(filled), len(unfilled), res["status"]))


if __name__ == "__main__":
    main()
