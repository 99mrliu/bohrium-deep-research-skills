#!/usr/bin/env python3
"""build_report.py -- 从流程产物组装可复核筛选报告（方法学附录草稿）。

输入（均可选，缺失即降级并在报告注明"数据缺失"）：
  --counts     counts.json（同 render_flow.py 输入）
  --protocol   search_protocol.json（检索范围声明来源）
  --decisions  decisions_summary.json：
               {"exclusion_reasons": {...}, "needs_human_reasons": {...},
                "agreement": {"screened": 177, "both_judged": 177,
                              "agreed": 170}}
  --flow-md    flow.md 路径（渲染产物，内嵌进报告）
  --out        输出 screening_report.md 的目录

报告只复述输入产物中的数字，不生成新数字；任何一节缺数据即标注
"数据缺失"并在末尾汇总缺失清单——渲染层不替上游补数。
退出码：0=正常（允许有缺失标注）；2=全部输入缺失。
"""
import argparse
import json
import os
import sys

MISSING = "数据缺失"


def load_json(path):
    if path and os.path.isfile(path):
        return json.load(open(path, encoding="utf-8"))
    return None


def main():
    ap = argparse.ArgumentParser(description="筛选报告组装")
    ap.add_argument("--counts", default="")
    ap.add_argument("--protocol", default="")
    ap.add_argument("--decisions", default="")
    ap.add_argument("--flow-md", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="系统性文献筛选报告")
    args = ap.parse_args()

    counts = load_json(args.counts)
    protocol = load_json(args.protocol)
    decisions = load_json(args.decisions)
    flow_md = ""
    if args.flow_md and os.path.isfile(args.flow_md):
        flow_md = open(args.flow_md, encoding="utf-8").read()

    if not any([counts, protocol, decisions, flow_md]):
        print("REPORT-ERROR: 全部输入缺失，无内容可组装", file=sys.stderr)
        sys.exit(2)

    gaps = []
    sec = ["# %s" % args.title, "",
           "> 本报告由 build_report.py 从流程产物组装；所有数字可回溯到"
           " counts/protocol/decisions 产物文件，渲染层不生成新数字。", ""]

    # 1 检索范围
    sec.append("## 1 检索范围")
    if protocol:
        sec.append("- 检索日期：%s" % (protocol.get("search_date") or MISSING))
        for q in protocol.get("queries", []):
            dl = q.get("date_limit") or {}
            sec.append("- **%s**：字段范围 %s；日期限定 %s..%s；语种限定 %s" % (
                q.get("database"), q.get("field_scope", MISSING),
                dl.get("from", MISSING), dl.get("to", MISSING),
                ", ".join(q.get("language_limit") or []) or MISSING))
        sec.append("- 快照声明：%s" % protocol.get("snapshot_policy", MISSING))
    else:
        sec.append("- %s（未提供 search_protocol.json）" % MISSING)
        gaps.append("检索范围")
    sec.append("")

    # 2 流程计数
    sec.append("## 2 流程计数")
    if counts:
        sec += ["| 环节 | n |", "|---|---|"]
        for k in ("identified", "duplicates_removed", "screened",
                  "excluded", "included", "needs_human"):
            sec.append("| %s | %s |" % (k, counts.get(k, MISSING)))
    else:
        sec.append("- %s（未提供 counts.json）" % MISSING)
        gaps.append("流程计数")
    sec.append("")

    # 3 流程图
    sec.append("## 3 流程图")
    if flow_md:
        sec.append(flow_md.strip())
    else:
        sec.append("- %s（未提供 flow.md）" % MISSING)
        gaps.append("流程图")
    sec.append("")

    # 4 排除理由
    sec.append("## 4 排除理由分布")
    reasons = (decisions or {}).get("exclusion_reasons") \
        or (counts or {}).get("exclusion_reasons")
    if reasons:
        sec += ["| 理由码 | n |", "|---|---|"]
        for k in sorted(reasons):
            sec.append("| %s | %d |" % (k, reasons[k]))
    else:
        sec.append("- %s" % MISSING)
        gaps.append("排除理由分布")
    sec.append("")

    # 5 一致性
    sec.append("## 5 双人标注一致性")
    ag = (decisions or {}).get("agreement")
    if ag and ag.get("both_judged"):
        rate = ag["agreed"] / ag["both_judged"]
        sec.append("双人判定 %d 条，一致 %d 条，一致率 %.1f%%；"
                   "分歧处理见仲裁记录。" % (
                       ag["both_judged"], ag["agreed"], rate * 100))
    else:
        sec.append("- %s（未提供 agreement 统计）" % MISSING)
        gaps.append("一致性统计")
    sec.append("")

    # 6 待人工
    sec.append("## 6 待人工确认")
    if counts and isinstance(counts.get("needs_human"), int):
        sec.append("待人工确认记录 %d 条；在人工回填前其模型判定仅为"
                   " pending 建议，不纳入最终结论。" % counts["needs_human"])
    else:
        sec.append("- %s" % MISSING)
        gaps.append("待人工确认")
    sec.append("")

    if gaps:
        sec += ["## 缺失清单", ""]
        for g in gaps:
            sec.append("- %s：%s" % (g, MISSING))

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "screening_report.md")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sec) + "\n")
    print("REPORT -> %s (gaps=%d)" % (out_path, len(gaps)))
    sys.exit(0)


if __name__ == "__main__":
    main()
