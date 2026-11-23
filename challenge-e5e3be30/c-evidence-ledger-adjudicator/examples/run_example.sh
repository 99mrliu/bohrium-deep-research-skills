#!/usr/bin/env bash
# run_example.sh — evidence-ledger-adjudicator 合成示例端到端流水线。
# 真实执行: ledger_init → 填台账（演示输入）→ validate → verdict_engine(--explain --update)
#          → validate(含 adjudication) → conflict_pairs → 组装演示 result。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL_ROOT="$(cd "$HERE/.." && pwd)"
WORK="$HERE/demo_work"
PY=python3

echo "################################################################"
echo "# evidence-ledger-adjudicator 合成示例（examples/paper.txt 为虚构论文）"
echo "################################################################"

echo ""
echo "== [1/7] ledger_init: 从 claims.json 生成台账骨架（含锚点预提取） =="
rm -rf "$WORK"; mkdir -p "$WORK"
"$PY" "$SKILL_ROOT/scripts/ledger_init.py" "$HERE/claims.json" --outdir "$WORK"

echo ""
echo "== [2/7] 填写证据台账 =="
echo "   【演示输入】正式运行时此步由模型阅读论文 PDF 后逐条填写 evidence；"
echo "   本例使用预填的演示台账 examples/demo_ledgers/（在台账内注明）。"
cp "$HERE/demo_ledgers/"ledger-*.json "$WORK/"

echo ""
echo "== [3/7] ledger_validate: schema 与标注一致性机检 =="
"$PY" "$SKILL_ROOT/scripts/ledger_validate.py" "$WORK"

echo ""
echo "== [4/7] verdict_engine: 确定性裁决（--explain --update） =="
for f in "$WORK"/ledger-*.json; do
    "$PY" "$SKILL_ROOT/scripts/verdict_engine.py" "$f" --explain --update
done

echo ""
echo "== [5/7] ledger_validate: 复检（含 adjudication 一致性，允许 WARNING 不阻塞） =="
"$PY" "$SKILL_ROOT/scripts/ledger_validate.py" "$WORK"

echo ""
echo "== [6/7] conflict_pairs: 正反 direct 证据对撞检测 =="
"$PY" "$SKILL_ROOT/scripts/conflict_pairs.py" "$WORK" --out "$WORK/conflicts.json"

echo ""
echo "== [7/7] 组装演示 result-demo.json =="
WORK_DIR="$WORK" "$PY" - <<'EOF'
import json, glob, os
work = os.environ.get("WORK_DIR", "demo_work")
ledgers, verdicts, conflicts = [], [], []
for path in sorted(glob.glob(os.path.join(work, "ledger-*.json"))):
    d = json.load(open(path, encoding="utf-8"))
    a = d["adjudication"]
    verdicts.append({
        "claim_id": d["claim_id"],
        "claim": d["claim_text"],
        "verdict": a["verdict"],
        "base_verdict": a["base_verdict"],
        "conflict": a["conflict"],
        "anchor_table": a["anchor_table"],
        "evidence_ids": [e["evidence_id"] for e in d["evidence"]],
    })
c = json.load(open(os.path.join(work, "conflicts.json"), encoding="utf-8"))
result = {
    "case_id": "example-ledger-001",
    "status": "complete",
    "verdicts": verdicts,
    "sources": [{"source_id": "paper.txt", "title": "PerillaSeed-X 合成示例论文",
                 "type": "paper", "locator": "examples/paper.txt"}],
    "conflicts": c["conflicts"],
    "uncertainty": ["C2 摘要与表 1 数值不一致，冲突未消解，需作者更正"],
    "change_records": ["demo 输入：evidence 为人工预填演示数据；"
                       "C2/C4 锚点文本做过编辑性清理"],
}
out = os.path.join(work, "result-demo.json")
json.dump(result, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("已写出", out)
for v in verdicts:
    print("  %s -> %s (base=%s, conflict=%s)" % (
        v["claim_id"], v["verdict"], v["base_verdict"], v["conflict"]))
EOF

echo ""
echo "完成。最终台账与 conflicts.json / result-demo.json 位于 $WORK"
