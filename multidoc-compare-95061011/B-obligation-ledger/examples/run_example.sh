#!/usr/bin/env bash
# run_example.sh — 端到端合成示例：compile → close → coverage → result.json → contract_gate
# 所有数据均为虚构（合成），仅供演示义务台账流程。产物写入 examples/output/。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
OUT="$HERE/output"
mkdir -p "$OUT"

echo "== 1/5 编译义务 =="
python3 "$ROOT/scripts/compile_obligations.py" \
  --workorder "$HERE/comparison-workorder.json" \
  --case "$HERE/case.json" \
  --out "$OUT/obligations.jsonl"

echo "== 2/5 校验并合并关闭记录 =="
python3 "$ROOT/scripts/close_obligations.py" \
  --obligations "$OUT/obligations.jsonl" \
  --closures "$HERE/sample_closures.jsonl" \
  --corpus "$HERE/corpus" \
  --out "$OUT/obligations.jsonl"

echo "== 3/5 覆盖度核算与渲染 =="
python3 "$ROOT/scripts/coverage.py" \
  --obligations "$OUT/obligations.jsonl" \
  --out-dir "$OUT"

echo "== 4/5 由台账组装 result.json（演示：实际评测中由 agent 组装） =="
python3 - "$OUT" <<'PYEOF'
import json, sys, os
out = sys.argv[1]
obligations = [json.loads(l) for l in open(os.path.join(out, "obligations.jsonl"), encoding="utf-8") if l.strip()]
coverage = json.load(open(os.path.join(out, "coverage.json"), encoding="utf-8"))
matrix_md = open(os.path.join(out, "comparison-matrix.md"), encoding="utf-8").read()
ledger_md = open(os.path.join(out, "obligation-ledger.md"), encoding="utf-8").read()

matrix = {}
for o in obligations:
    if o["kind"] != "field_cell":
        continue
    c = o.get("closure") or {}
    matrix.setdefault(o["field"], {})[o["document_id"]] = {
        "status": o["status"],
        "value": c.get("value"),
        "unit": c.get("unit"),
        "source_document_id": c.get("source_document_id"),
        "paragraph_id": c.get("paragraph_id"),
    }
cmp_notes = [
    {"doc_pair": o["doc_pair"], "dimension": o["dimension"],
     "verdict": (o.get("closure") or {}).get("value"), "status": o["status"]}
    for o in obligations if o["kind"] == "comparability"
]
sources = sorted({
    "%s#%s" % (c.get("source_document_id"), c.get("paragraph_id"))
    for c in (o.get("closure") or {} for o in obligations)
    if c.get("source_document_id")
} | {
    "%s#%s" % (c.get("secondary_source_document_id"), c.get("secondary_paragraph_id"))
    for c in (o.get("closure") or {} for o in obligations)
    if c.get("secondary_source_document_id")
})
result = {
    "case_id": "SYNTH-EXAMPLE-001",
    "status": "success" if coverage["open"] == 0 else "partial",
    "comparison_matrix": matrix,
    "comparability_notes": cmp_notes,
    "coverage": coverage,
    "ledger": {"markdown": ledger_md, "matrix_markdown": matrix_md},
    "sources": sources,
    "uncertainty": [] if coverage["open"] == 0 else
        [{"obligation_id": oid, "reason": "示例中未关闭，实际评测须写明原因"} for oid in coverage["open_obligations"]],
}
with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print("[example] result.json 已生成：status=%s sources=%d" % (result["status"], len(sources)))
PYEOF

echo "== 5/5 交付门禁 =="
python3 "$ROOT/scripts/contract_gate.py" \
  --result "$OUT/result.json" \
  --case "$HERE/case.json" \
  --obligations "$OUT/obligations.jsonl"

echo "== 全部通过。产物见 $OUT =="
