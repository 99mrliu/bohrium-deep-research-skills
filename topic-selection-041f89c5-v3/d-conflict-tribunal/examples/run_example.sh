#!/usr/bin/env bash
# conflict-tribunal 合成示例驱动脚本（非正式测试案例）。
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/output"
rm -rf "$OUT"; mkdir -p "$OUT"

echo "=== 1) lint 好卷宗（预期 exit 0）==="
python3 "$HERE/../scripts/docket.py" lint \
    --docket "$HERE/input/docket_good.jsonl" > "$OUT/lint_good.json"
echo "exit=$?"

echo "=== 2) lint 坏卷宗（预期 exit 1：两组都缺对抗检索记录）==="
python3 "$HERE/../scripts/docket.py" lint \
    --docket "$HERE/input/docket_bad.jsonl" > "$OUT/lint_bad.json" 2>&1
echo "exit=$?"

echo "=== 3) adjudicate 好卷宗 ==="
python3 "$HERE/../scripts/docket.py" adjudicate \
    --docket "$HERE/input/docket_good.jsonl" --out "$OUT/tribunal"
echo "exit=$?"

echo "=== 产物 ==="
find "$OUT" -type f | sort
