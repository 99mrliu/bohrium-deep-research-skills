#!/usr/bin/env bash
# run_example.sh — 一键演示（合成示例 / synthetic）
# 步骤1: 矩阵结构门控（期望 exit 0）
# 步骤2: 合规版 冲突检出+裁定+分级+文本审计（期望 exit 0）
# 步骤3: 埋雷版 同上（期望 exit 1，C 编号逐项命中）
# 产物保留在 examples/output_demo/；任一步骤实际退出码与期望不符则脚本以 1 退出。
set +e
cd "$(dirname "$0")"
SKILL_DIR="$(cd .. && pwd)"
OUT=output_demo
mkdir -p "$OUT"

pass=0
fail=0
report() { # $1=步骤名 $2=期望退出码 $3=实际退出码
  if [ "$2" = "$3" ]; then
    st=OK; pass=$((pass+1))
  else
    st=MISMATCH; fail=$((fail+1))
  fi
  printf '%-22s EXPECTED=%s ACTUAL=%s [%s]\n' "$1" "$2" "$3" "$st"
}

echo "== 步骤1: matrix_check（结构门控 S1-S4，期望 0）=="
python3 "$SKILL_DIR/scripts/matrix_check.py" --matrix study_matrix.jsonl \
  | tee "$OUT/step1_matrix_check.log"
rc=${PIPESTATUS[0]}
report "matrix_check" 0 "$rc"
echo

echo "== 步骤2: conflict_adjudicate 合规版（C1-C4，期望 0）=="
python3 "$SKILL_DIR/scripts/conflict_adjudicate.py" \
  --matrix study_matrix.jsonl \
  --registry "$OUT/conflict_registry.json" \
  --adjudications adjudications.json \
  --conclusions conclusions.json \
  --synthesis synthesis.md \
  | tee "$OUT/step2_adjudicate_good.log"
rc=${PIPESTATUS[0]}
report "adjudicate_good" 0 "$rc"
echo

echo "== 步骤3: conflict_adjudicate 埋雷版（期望 1，应命中 C2/C3/C4）=="
python3 "$SKILL_DIR/scripts/conflict_adjudicate.py" \
  --matrix study_matrix.jsonl \
  --registry "$OUT/bad_conflict_registry.json" \
  --adjudications bad_adjudications.json \
  --conclusions bad_conclusions.json \
  --synthesis bad_synthesis.md \
  | tee "$OUT/step3_adjudicate_bad.log"
rc=${PIPESTATUS[0]}
report "adjudicate_bad" 1 "$rc"
echo

echo "== 汇总: ${pass} 项符合预期, ${fail} 项不符；产物见 ${OUT}/ =="
[ "$fail" -eq 0 ]
