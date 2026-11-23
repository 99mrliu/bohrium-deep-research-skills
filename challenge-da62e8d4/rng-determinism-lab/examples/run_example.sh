#!/usr/bin/env bash
# run_example.sh — 合成示例（synthetic），非正式案例结果。
#
# 用法: bash run_example.sh [输出目录]
#   输出目录缺省为 <技能目录>/examples/output
#
# 依次执行：
#   1) code_audit.py  审计 method_stable.py 与 method_unseeded.py
#   2) replay.py      两个脚本各重放 3 次（unseeded 附带 artifact 哈希对比）
#   3) env_snapshot.py --imports numpy
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT="${1:-$SCRIPT_DIR/output}"
mkdir -p "$OUT"

echo "== 合成示例（synthetic），非正式案例结果 =="
echo "技能目录: $SKILL_DIR"
echo "输出目录: $OUT"
echo

echo "[1/5] code_audit: method_stable.py"
python3 "$SKILL_DIR/scripts/code_audit.py" "$SKILL_DIR/examples/input/method_stable.py" \
    > "$OUT/code_audit_stable.json"
echo "  exit=$? -> $OUT/code_audit_stable.json"

echo "[2/5] code_audit: method_unseeded.py"
python3 "$SKILL_DIR/scripts/code_audit.py" "$SKILL_DIR/examples/input/method_unseeded.py" \
    > "$OUT/code_audit_unseeded.json"
echo "  exit=$? -> $OUT/code_audit_unseeded.json"

echo "[3/5] replay: method_stable.py x3（期望 identical 或 numerically_stable）"
python3 "$SKILL_DIR/scripts/replay.py" --name stable --runs 3 --timeout 60 \
    --out "$OUT/replay_stable" \
    -- python3 "$SKILL_DIR/examples/input/method_stable.py"
echo "  exit=$?"

echo "[4/5] replay: method_unseeded.py x3（期望 unstable 且 artifact 哈希不同）"
python3 "$SKILL_DIR/scripts/replay.py" --name unseeded --runs 3 --timeout 60 \
    --artifact result_unseeded.txt \
    --out "$OUT/replay_unseeded" \
    -- python3 "$SKILL_DIR/examples/input/method_unseeded.py"
echo "  exit=$?"

echo "[5/5] env_snapshot（--imports numpy；本机无 numpy 则记 not_installed）"
python3 "$SKILL_DIR/scripts/env_snapshot.py" --out "$OUT/env" --imports numpy
echo "  exit=$?"

echo
echo "完成。关键产物："
echo "  $OUT/code_audit_stable.json"
echo "  $OUT/code_audit_unseeded.json"
echo "  $OUT/replay_stable/determinism_report.json 与 report.md"
echo "  $OUT/replay_unseeded/determinism_report.json 与 report.md"
echo "  $OUT/env/env.json 与 rebuild.md"
