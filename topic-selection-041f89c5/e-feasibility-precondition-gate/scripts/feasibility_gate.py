#!/usr/bin/env python3
"""feasibility_gate.py — 可行性前提门控判定器。

可行性结论由前提台账机检生成，不允许"技术路线可行"式一句话结论。
每条前提必须显式标注依据性质：source（有来源定位）或 assumption（假设）。

台账（preconditions.jsonl，每行一条）：
  {"id": "P1", "category": "data|compute|experiment|time|personnel",
   "statement": "前提陈述", "status": "ok|blocked|unknown",
   "backing": "source|assumption",
   "evidence_ref": "来源文件#定位",   # backing=source 时必填
   "note": "假设理由或风险说明"}

门控规则（脚本强制）：
  G1 任一前提 status=blocked → verdict = not_feasible，列出全部 blocker；
  G2 否则，存在 status=unknown 或 backing=assumption 的前提
     → verdict = conditional，逐条列出成立条件与待核假设；
  G3 全部前提 status=ok 且 backing=source → verdict = feasible；
  G4 台账为空 → verdict = insufficient_evidence。
一致性违例（退出码 1）：
  Y1 backing=source 但 evidence_ref 为空；
  Y2 backing=assumption 但 note 为空（假设必须给理由）；
  Y3 category/status/backing 非法取值；
  Y4 id 重复。

输出（--out 目录）：
  verdict.json         判定、blocker 清单、条件清单
  feasibility_memo.md  决策备忘录（五类前提分组 + 结论 + 条件）
  risk_register.md     风险登记册（unknown 与 assumption 项全部入册）
仅标准库。
"""
import argparse
import json
import sys
from pathlib import Path

CATS = ["data", "compute", "experiment", "time", "personnel"]
CAT_ZH = {"data": "数据可得性", "compute": "算力条件",
          "experiment": "实验条件", "time": "时间窗口", "personnel": "人员能力"}
STATUS = {"ok", "blocked", "unknown"}
BACKING = {"source", "assumption"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    records, violations, seen = [], [], set()
    with open(args.ledger, encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            records.append(r)
            rid = r.get("id", "line-%d" % ln)
            if rid in seen:
                violations.append("%s: id 重复（Y4）" % rid)
            seen.add(rid)
            if r.get("category") not in CATS:
                violations.append("%s: category 非法 %r（Y3）"
                                  % (rid, r.get("category")))
            if r.get("status") not in STATUS:
                violations.append("%s: status 非法 %r（Y3）"
                                  % (rid, r.get("status")))
            if r.get("backing") not in BACKING:
                violations.append("%s: backing 非法 %r（Y3）"
                                  % (rid, r.get("backing")))
            if r.get("backing") == "source" \
                    and not (r.get("evidence_ref") or "").strip():
                violations.append("%s: backing=source 但 evidence_ref 为空（Y1）"
                                  % rid)
            if r.get("backing") == "assumption" \
                    and not (r.get("note") or "").strip():
                violations.append("%s: backing=assumption 但缺假设理由 note（Y2）"
                                  % rid)

    if not records:
        verdict = "insufficient_evidence"
    elif any(r.get("status") == "blocked" for r in records):
        verdict = "not_feasible"
    elif any(r.get("status") == "unknown" or r.get("backing") == "assumption"
             for r in records):
        verdict = "conditional"
    else:
        verdict = "feasible"

    blockers = [r for r in records if r.get("status") == "blocked"]
    conditions = [r for r in records
                  if r.get("status") == "unknown"
                  or r.get("backing") == "assumption"]
    risks = [{"id": r.get("id"), "category": r.get("category"),
              "statement": r.get("statement"),
              "kind": "unknown" if r.get("status") == "unknown" else "assumption",
              "note": r.get("note", "")} for r in conditions]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    out.joinpath("verdict.json").write_text(json.dumps({
        "verdict": verdict, "violations": violations,
        "n_premises": len(records),
        "blockers": [b.get("id") for b in blockers],
        "conditions": [c.get("id") for c in conditions]}, ensure_ascii=False,
        indent=2) + "\n", encoding="utf-8")

    v_zh = {"feasible": "可行", "conditional": "有条件可行",
            "not_feasible": "不可行", "insufficient_evidence": "证据不足"}
    memo = ["# 可行性决策备忘录", "",
            "结论：**%s**（前提 %d 条，blocker %d 条，条件/待核 %d 条）"
            % (v_zh[verdict], len(records), len(blockers), len(conditions)),
            ""]
    for cat in CATS:
        group = [r for r in records if r.get("category") == cat]
        if not group:
            continue
        memo.append("## %s" % CAT_ZH[cat])
        for r in group:
            mark = {"ok": "✓", "blocked": "✗", "unknown": "?"}[r["status"]]
            ref = r.get("evidence_ref") or ("假设：" + r.get("note", ""))
            memo.append("- %s **%s** %s（%s，%s）"
                        % (mark, r.get("id"), r.get("statement"),
                           r.get("backing"), ref))
        memo.append("")
    if blockers:
        memo.append("## 阻塞项")
        memo += ["- %s：%s" % (b.get("id"), b.get("statement"))
                 for b in blockers]
        memo.append("")
    if conditions:
        memo.append("## 成立条件 / 待核假设")
        memo += ["- %s：%s（%s）" % (c.get("id"), c.get("statement"),
                                     c.get("note") or c.get("evidence_ref"))
                 for c in conditions]
        memo.append("")
    if violations:
        memo.append("## 一致性违例（修复后方可交付）")
        memo += ["- " + v for v in violations]
        memo.append("")
    out.joinpath("feasibility_memo.md").write_text("\n".join(memo),
                                                   encoding="utf-8")

    reg = ["# 风险登记册", "",
           "登记全部 unknown 与 assumption 前提（共 %d 条）：" % len(risks), ""]
    if risks:
        reg.append("| ID | 类别 | 风险 | 性质 | 说明 |")
        reg.append("|---|---|---|---|---|")
        for r in risks:
            reg.append("| %s | %s | %s | %s | %s |"
                       % (r["id"], CAT_ZH.get(r["category"], "?"),
                          r["statement"], r["kind"], r["note"] or "-"))
    else:
        reg.append("无。")
    out.joinpath("risk_register.md").write_text("\n".join(reg) + "\n",
                                                encoding="utf-8")
    print(json.dumps({"verdict": verdict, "violations": len(violations),
                      "premises": len(records)}, ensure_ascii=False))
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
