#!/usr/bin/env bash
# run_example.sh：合成示例一键复现（生成库 → 建档 → 执行 → 独立复核）。
# 可在任意工作目录运行；示例库 sensors_syn.db 由脚本现场生成，包内不含任何二进制。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$(dirname "$SCRIPT_DIR")"
PY="${PYTHON:-python3}"
DB="$SCRIPT_DIR/output_demo/sensors_syn.db"
FOUNDRY="$BUNDLE_DIR/scripts/dbfoundry.py"

echo "== [1/5] 生成合成数据库 =="
"$PY" "$SCRIPT_DIR/make_synthetic_db.py"

echo
echo "== [2/5] survey 建档 =="
"$PY" "$FOUNDRY" survey --db "$DB" --work "$SCRIPT_DIR/output_demo/survey"

echo
echo "== [3/5] exec 逐条执行 q1 / q2 / q3 并对账 =="
"$PY" "$FOUNDRY" exec --db "$DB" --sql "$SCRIPT_DIR/queries/q1_valid_readings_per_site.sql" --tag q1 --outdir "$SCRIPT_DIR/output_demo/exec"
"$PY" "$FOUNDRY" exec --db "$DB" --sql "$SCRIPT_DIR/queries/q2_region_mean.sql" --tag q2 --outdir "$SCRIPT_DIR/output_demo/exec"
set +e
"$PY" "$FOUNDRY" exec --db "$DB" --sql "$SCRIPT_DIR/queries/q3_empty_result.sql" --tag q3 --outdir "$SCRIPT_DIR/output_demo/exec"
q3_rc=$?
set -e
echo "q3 退出码：$q3_rc（合法空结果应如实记录 empty_result 且退出码为 0）"

echo
echo "== [4/5] reconcile 独立复核 =="
"$PY" "$FOUNDRY" reconcile --db "$DB" --claim "$SCRIPT_DIR/reconcile_claim.json" --out "$SCRIPT_DIR/output_demo/recon.json"
echo "reconcile 退出码：0（全部 PASS）"

echo
echo "== [5/5] 关键产物摘录 =="
echo "--- survey.md（前 36 行）---"
head -n 36 "$SCRIPT_DIR/output_demo/survey/survey.md"
echo
echo "--- q1 元数据（行数对账）---"
cat "$SCRIPT_DIR/output_demo/exec/q1_1.meta.json"
echo
echo "--- q3 元数据（空结果纪律）---"
cat "$SCRIPT_DIR/output_demo/exec/q3_1.meta.json"
echo
echo "--- recon.json（独立复核裁定）---"
cat "$SCRIPT_DIR/output_demo/recon.json"
echo
echo "示例运行完成。产物位于：$SCRIPT_DIR/output_demo/"
