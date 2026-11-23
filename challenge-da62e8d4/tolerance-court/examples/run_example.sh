#!/usr/bin/env bash
# 合成示例（synthetic），非正式案例结果。
# 用法：run_example.sh [输出目录]（默认 examples/output）
# 依次执行：preregister（先注册容差）→ adjudicate（再裁决）→ 打印 comparison.md
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$HERE")"
OUT="${1:-$HERE/output}"
RUNS="$OUT/runs"   # 合成运行日志：本示例只 touch 占位文件用于 mtime 校验演示

mkdir -p "$OUT" "$RUNS"

echo "== [1/3] 事前注册容差（必须先于任何运行）=="
python3 "$SKILL_DIR/scripts/preregister.py" \
  --targets "$HERE/input/targets.json" \
  --out "$OUT/tolerances.json" || exit 2

# 模拟：容差注册之后才产生运行日志
sleep 1
for f in method_a_seed1 method_a_seed2 method_a_seed3 method_a_seed4 method_a_seed5 \
         method_a_ablation method_b_seed1 method_b_seed2 method_b_seed3 \
         method_b_ablation method_b_crash; do
  echo "synthetic run log: $f" > "$RUNS/$f.log"
done

echo
echo "== [2/3] 统计裁决 =="
python3 "$SKILL_DIR/scripts/adjudicate.py" \
  --tolerances "$OUT/tolerances.json" \
  --observations "$HERE/input/observations.json" \
  --out "$OUT" \
  --runs "$RUNS"
ADJ_CODE=$?
echo "adjudicate exit code: $ADJ_CODE"
# 预期退出码 1：合成示例故意包含 systematic_deviation / missing / insufficient_runs

echo
echo "== [3/3] comparison.md =="
cat "$OUT/comparison.md"

exit 0
