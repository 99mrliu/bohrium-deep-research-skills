#!/usr/bin/env bash
# run_example.sh — skill-e-deliverable-forge 端到端演示（合成示例，非正式测评结果）。
# 演示 1：故意缺 2 个 contract 字段的 result.json → contract_validate FAIL → 自动降级 partial。
# 演示 2：补齐字段恢复 complete → 重跑验收 PASS。
# 随后：report_render 渲染 audit_report.md/.html，summary_dashboard 生成 dashboard.json。
# 全部输出写入 examples/output/。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
OUT="$HERE/output"
mkdir -p "$OUT"

echo "== [1/5] 组装故意缺 2 个 contract 字段（sources、not_reviewed）的 result.json =="
python3 - "$HERE" "$OUT" <<'PY'
import json, sys
here, out = sys.argv[1], sys.argv[2]
findings = json.load(open(here + "/findings_final.json", encoding="utf-8"))["findings"]
result = {
    "note": "合成示例输出，非正式测评结果（故意缺 sources、not_reviewed 两字段，用于演示 FAIL→自动降级）",
    "case_id": "MOCK-E-001",
    "status": "complete",
    "summary": "对 synthetic_paper.txt 完成 5 个审查面的审查，共 6 条发现：critical 1、major 2、minor 2、info 1，其中 1 条待复核。",
    "findings": findings,
    "uncertainty": ["参考文献[2]的真伪未能本地核实（见 F02 待复核）。"],
    "change_log": ["初稿：组装 findings_final.json 的 6 条发现。"]
}
with open(out + "/result_missing.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
    f.write("\n")
print("written result_missing.json (缺 sources、not_reviewed)")
PY

echo "== [2/5] 第一次机械验收（预期 FAIL，并自动降级 status→partial）=="
python3 "$ROOT/scripts/contract_validate.py" \
  --case "$HERE/mock_case.json" \
  --result "$OUT/result_missing.json" \
  --out "$OUT/validation_missing.json"

echo "== [3/5] 补齐缺失字段、恢复 complete，组装 result_full.json =="
python3 - "$HERE" "$OUT" <<'PY'
import json, sys
here, out = sys.argv[1], sys.argv[2]
result = json.load(open(out + "/result_missing.json", encoding="utf-8"))
result["note"] = "合成示例输出，非正式测评结果（补齐全部 contract 字段后的完整版）"
result["status"] = "complete"
result["sources"] = [
    "synthetic_paper.txt（/input 提供的合成示意论文文本，全部 quote 的逐字来源）",
    "mock_case.json（output_contract 与审查面声明）"
]
result["not_reviewed"] = [
    "无未覆盖审查面：case.json 声明的 5 个审查面（事实一致性/引用核验/伦理合规/论断证据/报告完整性）均已完成审查"
]
result["facets_reviewed"] = [
    "事实一致性", "引用与参考文献核验", "伦理与合规", "论断证据充分性", "报告完整性"
]
result["change_log"].append("补齐缺失字段 sources、not_reviewed，status 恢复 complete，准备重跑机械验收。")
with open(out + "/result_full.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
    f.write("\n")
print("written result_full.json (8 个 contract 字段齐全)")
PY

echo "== [4/5] 第二次机械验收（预期 PASS）=="
python3 "$ROOT/scripts/contract_validate.py" \
  --case "$HERE/mock_case.json" \
  --result "$OUT/result_full.json" \
  --out "$OUT/validation_full.json"

echo "== [5/5] 渲染人读报告与结构化摘要 =="
python3 "$ROOT/scripts/report_render.py" \
  --result "$OUT/result_full.json" \
  --out-md "$OUT/audit_report.md" \
  --out-html "$OUT/audit_report.html"
python3 "$ROOT/scripts/summary_dashboard.py" \
  --result "$OUT/result_full.json" \
  --out "$OUT/dashboard.json"

echo "== 演示完成，输出清单：=="
ls -la "$OUT"
