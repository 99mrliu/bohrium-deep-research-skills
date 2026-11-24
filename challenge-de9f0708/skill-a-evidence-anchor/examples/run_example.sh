#!/usr/bin/env bash
# run_example.sh — 合成示例端到端复跑脚本
# 管道：audit_skeleton（保底骨架）-> extract_text（分页抽取）
#       -> quote_bind（锚定机械核验+自动降级）-> 汇总 result.json 与 report.md
# 输出全部写入 examples/output/。注意：本示例为合成示意案例，非正式测评结果。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL_ROOT="$(cd "$HERE/.." && pwd)"
SCRIPTS="$SKILL_ROOT/scripts"
OUT="$HERE/output"
mkdir -p "$OUT"

echo "== [1/4] audit_skeleton: 生成 result.json 保底骨架 =="
python3 "$SCRIPTS/audit_skeleton.py" \
  --case "$HERE/mock_case.json" \
  --out "$OUT/result.json" --force

echo "== [2/4] extract_text: 分页抽取 mock_paper.txt =="
python3 "$SCRIPTS/extract_text.py" \
  "$HERE/mock_paper.txt" \
  --out "$OUT/pages.json"

echo "== [3/4] quote_bind: 锚定机械核验（失败自动降级） =="
python3 "$SCRIPTS/quote_bind.py" \
  --pages "$OUT/pages.json" \
  --findings "$HERE/findings_draft.json" \
  --out "$OUT/findings_bound.json" \
  --stats "$OUT/anchor_stats.json"

echo "== [4/4] 汇总 result.json 并渲染 report.md =="
python3 - "$HERE" "$OUT" <<'PYEOF'
import json, os, sys

here, out = sys.argv[1], sys.argv[2]
NOTE = "合成示例输出，非正式测评结果"

def load(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)

case = load(os.path.join(here, "mock_case.json"))
result = load(os.path.join(out, "result.json"))
bound = load(os.path.join(out, "findings_bound.json"))
stats = load(os.path.join(out, "anchor_stats.json"))
pages = load(os.path.join(out, "pages.json"))
page_count = pages.get("page_count", 0)

findings = bound.get("findings", [])
facets = case.get("review_facets", [])
covered = {f.get("category") for f in findings if f.get("category")}
not_reviewed = [{"facet": fc, "reason": "无任何 finding 覆盖（合成示例中不应出现）"}
                for fc in facets if fc not in covered]

result["_note"] = NOTE
result["status"] = "partial" if stats.get("downgraded") else "complete"
result["findings"] = findings
result["not_reviewed"] = not_reviewed
result["anchor_stats"] = stats
result.pop("skeleton_warnings", None)
result["uncertainty"] = (
    "F-004 为 absence 类 finding（伦理声明缺失），quote 为空、锚定核验不适用，"
    "已人工通读全文确认无 ethics/consent/IRB 字样；F-006 锚定核验未通过，"
    "已自动降级为待复核，不得作为已确认问题上报。"
)
result["sources"] = ["mock_paper.txt（合成示意论文，examples/）"]
result["change_log"].append({
    "seq": 2,
    "actor": "run_example.sh",
    "event": "review_completed",
    "detail": ("extract_text 分页 %d 页；quote_bind 核验 %d 条 finding："
               "verified=%d, skipped=%d, downgraded=%d；status=%s。"
               % (page_count,
                  stats.get("total_findings", 0), stats.get("verified", 0),
                  stats.get("skipped_absence_claim", 0),
                  stats.get("downgraded", 0), result["status"])),
})
with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as fh:
    json.dump(result, fh, ensure_ascii=False, indent=2)
    fh.write("\n")

lines = [
    "# 审查报告：%s" % case.get("case_id", "UNKNOWN"),
    "",
    "> %s。所有论文内容、机构、人物均为虚构。" % NOTE,
    "",
    "## 锚定统计",
    "",
    "| 指标 | 数值 |",
    "| --- | --- |",
    "| findings 总数 | %d |" % stats.get("total_findings", 0),
    "| 锚定通过 verified | %d（exact=%d, normalized=%d, cross_page=%d） |"
      % (stats.get("verified", 0), stats.get("exact", 0),
         stats.get("normalized", 0), stats.get("cross_page", 0)),
    "| absence 跳过 | %d |" % stats.get("skipped_absence_claim", 0),
    "| 锚定失败自动降级 | %d %s |" % (stats.get("downgraded", 0),
                                     stats.get("downgraded_ids", [])),
    "",
    "## Findings",
    "",
    "| id | type | severity | page | match_level | verdict_status |",
    "| --- | --- | --- | --- | --- | --- |",
]
def fmt_page(p):
    return "—" if p is None else str(p)

for f in findings:
    loc = f.get("location") or {}
    anchor = f.get("anchor") or {}
    lines.append("| %s | %s | %s | %s | %s | %s |" % (
        f.get("id"), f.get("type"), f.get("severity"),
        fmt_page(loc.get("page")), anchor.get("match_level"),
        f.get("verdict_status")))
lines += ["", "## 详情", ""]
for f in findings:
    loc = f.get("location") or {}
    anchor = f.get("anchor") or {}
    lines += [
        "### %s [%s / %s] verdict=%s" % (
            f.get("id"), f.get("type"), f.get("severity"), f.get("verdict_status")),
        "",
        "- 位置：%s 第 %s 页 / %s" % (loc.get("file"),
                                      fmt_page(loc.get("page")), loc.get("section")),
        "- quote：%s" % (repr(loc.get("quote")) if loc.get("quote") else "（空：absence 类 finding）"),
        "- match_level：%s；found_on_pages=%s" % (
            anchor.get("match_level"), anchor.get("found_on_pages")),
        "- evidence：%s" % f.get("evidence", ""),
        "- suggestion：%s" % f.get("suggestion", ""),
    ]
    for r in f.get("verdict_reasons") or []:
        lines.append("- 复核理由：%s" % r)
    lines.append("")
with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))

print("summary: status=%s findings=%d downgraded=%s"
      % (result["status"], len(findings), stats.get("downgraded_ids")))
PYEOF

echo "== 完成。输出位于 $OUT =="
ls -la "$OUT"
