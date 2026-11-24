#!/usr/bin/env python3
"""render_review_pack.py — 选题评估交付包确定性渲染器。

把结构化评估载荷（payload.json）渲染成人读交付物：
  evaluation_report.md   评估报告（问题定义/已有工作比较/创新点边界/可行性/不确定性）
  evidence_matrix.md     证据矩阵表
渲染是确定性的：同一 payload 必得同字节输出（键排序、行尾统一），
便于复核"报告确实由这份数据生成"，而不是事后手改。

payload.json 结构（键均可缺省，缺省段落标注"未提供"）：
{
  "title": "...", "case_id": "...",
  "question": {"statement": "...", "object": "...", "variables": "...",
               "baseline": "...", "falsifiable_if": "..."},
  "prior_work": [{"id": "W1", "task": "...", "method": "...", "data": "...",
                  "metric": "...", "result": "...", "comparability": "..."}],
  "novelty_claims": [{"id": "C1", "claim": "...", "type": "...",
                      "verdict": "covered|partial|uncovered|indeterminate",
                      "basis": "..."}],
  "feasibility": {"verdict": "...", "conditions": ["..."],
                  "premises": [{"item": "...", "backing": "source|assumption",
                                "ref": "..."}]},
  "uncertainty": ["..."],
  "evidence_matrix": [{"ref": "E1", "source": "...", "field": "...",
                       "value": "...", "locator": "..."}]
}

用法：python3 render_review_pack.py --payload payload.json --out /app/output
仅依赖 Python 3.8+ 标准库。
"""
import argparse
import json
from pathlib import Path


def md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "---|" * len(headers)]
    for row in rows:
        lines.append("| " + " | ".join(
            str(c).replace("\n", "<br>").replace("|", "\\|") for c in row)
            + " |")
    return "\n".join(lines)


def render_report(p):
    q = p.get("question") or {}
    parts = ["# %s" % (p.get("title") or "选题评估报告（未命名）"), "",
             "case_id：`%s`" % (p.get("case_id") or "未提供"), "",
             "## 1. 研究问题定义", ""]
    if q:
        parts += ["- 可检验陈述：%s" % q.get("statement", "未提供"),
                  "- 研究对象：%s" % q.get("object", "未提供"),
                  "- 关键变量：%s" % q.get("variables", "未提供"),
                  "- 比较基线：%s" % q.get("baseline", "未提供"),
                  "- 可证伪条件：%s" % q.get("falsifiable_if", "未提供")]
    else:
        parts.append("未提供")
    parts += ["", "## 2. 已有工作比较", ""]
    pw = p.get("prior_work") or []
    if pw:
        parts.append(md_table(
            ["ID", "任务", "方法", "数据", "评价", "结果", "与本课题可比性"],
            [[w.get("id", "-"), w.get("task", "-"), w.get("method", "-"),
              w.get("data", "-"), w.get("metric", "-"), w.get("result", "-"),
              w.get("comparability", "-")] for w in pw]))
    else:
        parts.append("未提供")
    parts += ["", "## 3. 创新点边界", ""]
    nc = p.get("novelty_claims") or []
    if nc:
        parts.append(md_table(
            ["ID", "创新陈述", "类型", "判定", "依据"],
            [[c.get("id", "-"), c.get("claim", "-"), c.get("type", "-"),
              c.get("verdict", "-"), c.get("basis", "-")] for c in nc]))
    else:
        parts.append("未提供")
    parts += ["", "## 4. 可行性判断", ""]
    fs = p.get("feasibility") or {}
    if fs:
        parts.append("结论：**%s**" % fs.get("verdict", "未提供"))
        conds = fs.get("conditions") or []
        if conds:
            parts.append("前置条件：")
            parts += ["- " + c for c in conds]
        premises = fs.get("premises") or []
        if premises:
            parts.append("")
            parts.append(md_table(
                ["前提", "依据性质", "来源/说明"],
                [[m.get("item", "-"), m.get("backing", "-"),
                  m.get("ref", "-")] for m in premises]))
    else:
        parts.append("未提供")
    parts += ["", "## 5. 不确定性", ""]
    unc = p.get("uncertainty") or []
    parts += (["- " + u for u in unc] if unc else ["未提供"])
    return "\n".join(parts) + "\n"


def render_matrix(p):
    em = p.get("evidence_matrix") or []
    lines = ["# 证据矩阵", ""]
    if not em:
        lines.append("未提供")
    else:
        lines.append(md_table(
            ["证据ID", "来源", "字段", "取值/摘录", "定位"],
            [[e.get("ref", "-"), e.get("source", "-"), e.get("field", "-"),
              e.get("value", "-"), e.get("locator", "-")] for e in em]))
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--payload", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "evaluation_report.md").write_text(
        render_report(payload), encoding="utf-8")
    (out / "evidence_matrix.md").write_text(
        render_matrix(payload), encoding="utf-8")
    print(json.dumps({"rendered": ["evaluation_report.md",
                                   "evidence_matrix.md"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
