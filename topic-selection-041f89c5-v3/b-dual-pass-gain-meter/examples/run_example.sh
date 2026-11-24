#!/usr/bin/env bash
# dual-pass-gain-meter 合成示例驱动脚本（非正式测试案例）。
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/output"
rm -rf "$OUT"; mkdir -p "$OUT"

echo "=== 1) overclaim_lint 扫描基线稿（预期 exit 1，3 处违规）==="
python3 "$HERE/../scripts/overclaim_lint.py" "$HERE/input/pass0_result.json" \
    > "$OUT/lint_pass0.json" 2> "$OUT/lint_pass0.stderr.txt"
echo "exit=$?"
grep -c '"bounded": false' "$OUT/lint_pass0.json" || true

echo "=== 2) overclaim_lint 扫描严谨稿（预期 exit 0）==="
python3 "$HERE/../scripts/overclaim_lint.py" "$HERE/input/pass1_result.json" \
    > "$OUT/lint_pass1.json" 2> "$OUT/lint_pass1.stderr.txt"
echo "exit=$?"

echo "=== 3) gain_meter 差分（预期五项判定全过）==="
python3 "$HERE/../scripts/gain_meter.py" \
    --baseline "$HERE/input/pass0_result.json" \
    --final "$HERE/input/pass1_result.json" \
    --contract "$HERE/input/case.json" --out "$OUT/gain"
echo "exit=$?"
echo "=== 产物 ==="
find "$OUT" -type f | sort
