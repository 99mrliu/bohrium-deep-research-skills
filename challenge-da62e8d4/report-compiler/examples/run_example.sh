#!/usr/bin/env bash
# 合成示例（synthetic），非正式案例结果。
# 用法：run_example.sh [输出目录] [compile_report.py 附加参数，如 --svg]
#   输出目录缺省为 examples/output（评测/演示时请显式指定到工作区）。
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$SKILL_DIR/examples/output}"
if [ "$#" -gt 0 ]; then shift; fi

echo "== 合成示例（synthetic），非正式案例结果 =="
echo "== [1/2] 编译：台账 -> report.md / report.html / figures / report_map.json =="
python3 "$SKILL_DIR/scripts/compile_report.py" \
    --ledgers "$SKILL_DIR/examples/ledgers" \
    --out "$OUT" "$@"

echo "== [2/2] 审计：report_map 对账 + 覆盖率 + 孤儿数字 + 图检查 + result 契约 =="
python3 "$SKILL_DIR/scripts/audit_report.py" \
    --ledgers "$SKILL_DIR/examples/ledgers" \
    --report "$OUT"

echo "== 结论分级（摘自编译产物 report.md） =="
grep -m1 "结论分级" "$OUT/report.md"
echo "== 示例结束，产物目录：$OUT =="
