#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""omission_statement.py — 结构化“遗漏说明”生成器。

汇总 work/ 下三个诊断产物（near_misses / fragility_report / facet_coverage），
生成两部分：
  1. output/omission_statement.md：人读的结构化遗漏说明（排除了什么、按什么理由、
     哪些条目存在遗漏风险需人工复核、本快照无法回答什么）；
  2. result.json 的 omission_statement 字段：机器可读的结构化摘要 + md 相对路径。

退出码：0=通过；2=上游诊断产物缺失（诚实降级）；3=校验失败。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

EXIT_OK, EXIT_INSUFFICIENT, EXIT_INVALID = 0, 2, 3

CANNOT_ANSWER = [
    "本诊断仅基于有限题录快照，无法回答数据库之外是否仍有未检出的合格文献（不声称全局召回）。",
    "facet 零纳入报警无法在本快照内定性为“检索遗漏”“筛选过严”或“该面真空”，须人工回查检索式与全文。",
    "被排除记录中证据锚定弱的条目，其判定正确性须人工核对原文后才能确认。",
    "本技能不重新执行初筛判定，上游 judgments 本身的系统性偏倚只能被标记、不能被本流程纠正。",
]


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def ensure_result(result_path, case_id):
    if os.path.exists(result_path):
        return load_json(result_path)
    return {"case_id": case_id, "status": "partial",
            "sources": [], "uncertainty": [], "change_records": []}


def render_markdown(case_id, nm, frag, fc, wl):
    lines = []
    lines.append("# 遗漏说明（Omission Statement）")
    lines.append("")
    lines.append("- case_id：%s" % (case_id or "未知"))
    lines.append("- 生成：omission_statement.py v1.0.0 @ %s" % utcnow())
    lines.append("- 性质：基于上游 judgments 的下游诊断；不构成对全局召回的声明；"
                 "不含任何人工复核结论。")
    lines.append("")
    lines.append("## 1. 排除了什么、按什么理由")
    dist = (frag or {}).get("reason_code_distribution") or {}
    lines.append("排除总数：%s。主理由码分布：" % (frag or {}).get("total_exclusions", "未知"))
    if dist:
        for code, n in dist.items():
            lines.append("- `%s`：%d 条" % (code, n))
    else:
        lines.append("- （无分布数据）")
    lines.append("")
    lines.append("## 2. 排除稳健性")
    sr = (frag or {}).get("single_reason_exclusions") or {}
    un = (frag or {}).get("excluded_without_not_met") or {}
    lines.append("- 单理由排除：%s 条（占比 %s）" % (sr.get("count", "?"), sr.get("share", "?")))
    lines.append("- 无 not_met 依据的排除：%s 条" % un.get("count", "?"))
    lines.append("- fragile_share=%s（阈值 %s），fragile_flag=%s" % (
        (frag or {}).get("fragile_share"), (frag or {}).get("fragile_threshold"),
        (frag or {}).get("fragile_flag")))
    lines.append("")
    lines.append("## 3. 存在遗漏风险、须人工复核的条目（按风险分降序）")
    worklist = (wl or {}).get("worklist") or []
    if worklist:
        lines.append("| rank | record_id | risk_score | 触发器 |")
        lines.append("|---|---|---|---|")
        for w in worklist:
            lines.append("| %d | %s | %d | %s |" % (
                w.get("rank"), w.get("record_id"), w.get("risk_score"),
                ", ".join(w.get("trigger_types") or [])))
    else:
        lines.append("（险漏队列为空）")
    inc_unc = (nm or {}).get("included_uncertain") or []
    if inc_unc:
        lines.append("")
        lines.append("另：%d 条已纳入记录含 uncertain 判据（错误纳入风险，建议抽查）：%s" % (
            len(inc_unc), ", ".join(str(x.get("record_id")) for x in inc_unc)))
    lines.append("")
    lines.append("## 4. 主题面覆盖报警")
    alarms = (fc or {}).get("alarms") or []
    if alarms:
        for a in alarms:
            lines.append("- facet `%s`（%s）：%s" % (
                a.get("facet_id"), a.get("label"), a.get("interpretation")))
    else:
        lines.append("（无零纳入 facet 报警）")
    lines.append("")
    lines.append("## 5. 本快照无法回答的问题")
    for item in CANNOT_ANSWER:
        lines.append("- %s" % item)
    lines.append("")
    lines.append("## 6. 建议的后续人工动作")
    lines.append("1. 按第 3 节工作清单顺序双人复核，先处理 excluded_without_not_met 与单理由排除。")
    lines.append("2. 对每个 facet 零纳入报警，回查检索式是否覆盖该主题面、排除理由是否误伤。")
    lines.append("3. 复核结论须由真实人工产生并单独留痕；本技能产物不构成复核结论。")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="结构化遗漏说明生成器")
    ap.add_argument("--input-dir", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args()

    try:
        os.makedirs(args.output_dir, exist_ok=True)
        result_path = os.path.join(args.output_dir, "result.json")
        case_path = os.path.join(args.input_dir, "case.json")
        case = load_json(case_path) if os.path.exists(case_path) else {}
        result = ensure_result(result_path, case.get("case_id"))

        paths = {k: os.path.join(args.work, k + ".json") for k in
                 ("near_misses", "fragility_report", "facet_coverage", "recheck_worklist")}
        missing = [k for k, p in paths.items() if not os.path.exists(p)]
        if missing:
            note = ("字段 omission_statement 置 null：缺少上游诊断产物 %s；请先运行 "
                    "mine_near_misses.py / fragility_report.py / facet_coverage.py。"
                    % ", ".join(missing))
            unc = result.get("uncertainty") or []
            if note not in unc:
                unc.append(note)
            result["uncertainty"] = unc
            result["omission_statement"] = None
            result["change_records"].append({
                "ts": utcnow(),
                "action": "omission_statement: upstream artifacts missing, degraded",
                "files": [result_path]})
            save_json(result_path, result)
            print(note, file=sys.stderr)
            return EXIT_INSUFFICIENT

        nm = load_json(paths["near_misses"])
        frag = load_json(paths["fragility_report"])
        fc = load_json(paths["facet_coverage"])
        wl = load_json(paths["recheck_worklist"])

        md = render_markdown(case.get("case_id"), nm, frag, fc, wl)
        md_path = os.path.join(args.output_dir, "omission_statement.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md)

        structured = {
            "path": "omission_statement.md",
            "excluded_total": frag.get("total_exclusions"),
            "reason_code_distribution": frag.get("reason_code_distribution"),
            "fragile_share": frag.get("fragile_share"),
            "fragile_flag": frag.get("fragile_flag"),
            "recheck_queue_size": nm.get("queue_size"),
            "top_recheck": [w.get("record_id") for w in (wl.get("worklist") or [])[:3]],
            "facet_alarms": [a.get("facet_id") for a in (fc.get("alarms") or [])],
            "cannot_answer": list(CANNOT_ANSWER),
        }
        result["omission_statement"] = structured
        result["change_records"].append({
            "ts": utcnow(),
            "action": "omission_statement: statement generated",
            "files": [md_path, result_path]})
        save_json(result_path, result)
        print("遗漏说明已生成：%s" % md_path)
        return EXIT_OK
    except Exception as e:
        print("omission_statement 未预期失败: %s" % e, file=sys.stderr)
        return EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
