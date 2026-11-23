#!/usr/bin/env bash
# run_example.sh — 端到端演示：cue_scan → coverage_matrix（含一次 omission 打回）→ aggregate
# 用法：bash examples/run_example.sh   （在 skill 根目录下运行）
set -u

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EX_DIR="$SKILL_DIR/examples"
RUN_DIR="$EX_DIR/_run"
mkdir -p "$RUN_DIR"
FAIL=0

echo "==== [1/5] cue_scan：线索词扫描 + 原子拆解 ===="
python3 "$SKILL_DIR/scripts/cue_scan.py" \
  --claims "$EX_DIR/claims.json" \
  --out "$RUN_DIR/atoms.json" || { echo "FATAL: cue_scan 失败"; exit 1; }
echo "exit=0  （产物：$RUN_DIR/atoms.json）"
echo

echo "==== [2/5] coverage_matrix（破坏版）：演示 omission 被打回，exit=1 ===="
RUN_DIR="$RUN_DIR" python3 - <<'PYEOF'
import json, os
run = os.environ["RUN_DIR"]
d = json.load(open(os.path.join(run, "atoms.json"), encoding="utf-8"))
# 人为清空 c1#a1 的 covers_slots，模拟"拆漏了"
d["claims"][0]["atoms"][0]["covers_slots"] = []
json.dump(d, open(os.path.join(run, "atoms_broken.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
PYEOF
python3 "$SKILL_DIR/scripts/coverage_matrix.py" \
  --atoms "$RUN_DIR/atoms_broken.json" --out "$RUN_DIR/coverage_broken_report.json"
code=$?
echo "exit=$code  （预期 exit=1：条件槽位'在 600°C 退火下'无人认领，拆解必须返工）"
[ "$code" -eq 1 ] || { echo "FATAL: 预期 exit=1，实际 exit=$code"; FAIL=1; }
echo

echo "==== [3/5] coverage_matrix（正常版）：修复后通过，exit=0 ===="
python3 "$SKILL_DIR/scripts/coverage_matrix.py" \
  --atoms "$RUN_DIR/atoms.json" --out "$RUN_DIR/coverage_report.json"
code=$?
echo "exit=$code  （产物：$RUN_DIR/coverage_report.json）"
[ "$code" -eq 0 ] || { echo "FATAL: 预期 exit=0，实际 exit=$code"; FAIL=1; }
echo

echo "==== [4/5] aggregate：三条论断的子判定 → 整论断判定 ===="
cat > "$RUN_DIR/subjudgments_c1.json" <<'JSONEOF'
{
  "claim_id": "c1",
  "subjudgments": [
    {"id": "c1#a1", "verdict": "supported", "type": "comparison",
     "note": "原文：600°C 538±11 MPa vs 500°C 412±9 MPa，提高约 30.6%≈30%，方向一致"},
    {"id": "c1#a2", "verdict": "supported", "type": "comparison",
     "note": "原文：生产成本较传统铸造工艺降低约 12%"},
    {"id": "c1#a3", "verdict": "supported", "type": "causal",
     "note": "原文：强度提升归因于晶粒细化与弥散强化，与论断的因果表述一致"},
    {"id": "c1#a4", "verdict": "contradicted", "type": "scope",
     "note": "原文：结论'仅适用于 6xxx 系铝合金'，与'适用于所有铝合金'直接冲突（核心范围断言）"}
  ]
}
JSONEOF
cat > "$RUN_DIR/subjudgments_c2.json" <<'JSONEOF'
{
  "claim_id": "c2",
  "subjudgments": [
    {"id": "c2#a1", "verdict": "supported", "type": "comparison",
     "note": "原文：延伸率由 8.1% 提高至 15.2%，数值一致"},
    {"id": "c2#a2", "verdict": "insufficient_evidence", "type": "comparison",
     "note": "原文明确声明'未测量热导率'；未报告≠反驳"}
  ]
}
JSONEOF
cat > "$RUN_DIR/subjudgments_c3.json" <<'JSONEOF'
{
  "claim_id": "c3",
  "subjudgments": [
    {"id": "c3#a1", "verdict": "insufficient_evidence", "type": "comparison",
     "note": "原文明确声明未开展任何腐蚀性能测试，亦无与 2024 铝合金的对比"}
  ]
}
JSONEOF
for f in c1 c2 c3; do
  echo "--- aggregate $f ---"
  python3 "$SKILL_DIR/scripts/aggregate.py" \
    --subjudgments "$RUN_DIR/subjudgments_$f.json" \
    --explain --out "$RUN_DIR/verdict_$f.json" || { echo "FATAL: aggregate $f 失败"; FAIL=1; }
done
echo

echo "==== [5/5] 结果汇总 ===="
RUN_DIR="$RUN_DIR" python3 - <<'PYEOF'
import json, os
run = os.environ["RUN_DIR"]
for f in ("c1", "c2", "c3"):
    d = json.load(open(os.path.join(run, "verdict_%s.json" % f), encoding="utf-8"))
    print("%s -> %s  (规则 %s)" % (f, d["verdict"], d["rule"]))
    print("  %s" % d["rationale"])
PYEOF
echo
echo "产物目录：$RUN_DIR/"
ls -1 "$RUN_DIR"
if [ "$FAIL" -eq 0 ]; then
  echo "ALL OK：预期 exit code 均符合（cue_scan=0，coverage 破坏版=1，coverage 正常版=0，aggregate=0）"
else
  echo "存在不符合预期的 exit code，请检查上方输出"; exit 1
fi
