#!/usr/bin/env bash
# run_example.sh —— 诚实交付演练（合成数据，可从任意 cwd 运行）。
# 演示一：故意留一个字段不填 + 故意失败一条命令 → finalize 必须 exit 4（partial）。
# 演示二：全部字段填满 → finalize 必须 exit 0（complete）。
# 阴性测试：静默 null（无理由）→ finalize 必须 exit 1（invalid）。
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SG="$HERE/../scripts/stagegate.py"
TOY="$HERE/toy_analysis.py"
CASE="$HERE/synthetic_case/case.json"
CSV="$HERE/synthetic_case/measurements_syn.csv"
PY="$(command -v python3)"

OUT1="$HERE/demo_out_partial";  WORK1="$HERE/demo_work_partial"
OUT2="$HERE/demo_out_complete"; WORK2="$HERE/demo_work_complete"

rm -rf "$OUT1" "$WORK1" "$OUT2" "$WORK2"
mkdir -p "$WORK1" "$WORK2"

fails=0
expect() { # expect <期望码> <实际码> <标签>
  if [ "$1" -eq "$2" ]; then
    echo "[OK] $3 (exit $2)"
  else
    echo "[FAIL] $3: expected $1 got $2"; fails=$((fails+1))
  fi
}

echo "================================================================"
echo "演示一：中断场景下的合法 partial"
echo "================================================================"

"$PY" "$SG" init --case "$CASE" --output "$OUT1"
expect 0 $? "init 落盘骨架"

"$PY" "$SG" run --output "$OUT1" --journal "$WORK1/journal.jsonl" -- \
  "$PY" "$TOY" --csv "$CSV" --out "$OUT1"
expect 0 $? "run toy_analysis.py（成功命令）"

"$PY" "$SG" set --output "$OUT1" --field statistics --value-file "$OUT1/stats.json" --evidence stats.json
expect 0 $? "set statistics（带证据 stats.json）"

"$PY" "$SG" set --output "$OUT1" --field cleaned_table --value-json '"cleaned.csv"' --evidence cleaned.csv
expect 0 $? "set cleaned_table（带证据 cleaned.csv）"

echo "--- 故意失败的命令（exit 3），演示失败日志 + 自动 anomaly ---"
"$PY" "$SG" run --output "$OUT1" --journal "$WORK1/journal.jsonl" -- \
  "$PY" -c 'import sys; print("boom: plotting backend unavailable", file=sys.stderr); sys.exit(3)'
expect 3 $? "失败命令透明传递退出码 3"

"$PY" "$SG" anomaly --output "$OUT1" --kind figure_backend_missing \
  --detail "合成演示：绘图后端不可用，figures 字段在本轮预算内无法产出"
expect 0 $? "anomaly 手工记录"

"$PY" "$SG" set --output "$OUT1" --field notes \
  --value-json '"合成演示：统计与清洗表已交付；figures 因绘图后端不可用而缺失，详见 anomalies。"'
expect 0 $? "set notes"

"$PY" "$SG" reason --output "$OUT1" --field figures \
  --text "绘图后端不可用且预算不足以修复；保持 null 并在此给出理由，绝不静默缺省"
expect 0 $? "reason 为 figures 写明缺失理由"

"$PY" "$SG" checkpoint --output "$OUT1" --work "$WORK1" --note "核心计算完成，figures 缺失已定因"
expect 0 $? "checkpoint 链式校验"

"$PY" "$SG" status --output "$OUT1" --work "$WORK1"

"$PY" "$SG" finalize --output "$OUT1" --case "$CASE" --journal "$WORK1/journal.jsonl"
expect 4 $? "finalize 诚实 partial"

echo "--- result.json ---"
cat "$OUT1/result.json"
echo "--- delivery_summary.md ---"
cat "$OUT1/delivery_summary.md"

echo "================================================================"
echo "演示二：全部填满的 complete"
echo "================================================================"

"$PY" "$SG" init --case "$CASE" --output "$OUT2"
expect 0 $? "init（第二个输出目录）"

"$PY" "$SG" run --output "$OUT2" --journal "$WORK2/journal.jsonl" -- \
  "$PY" "$TOY" --csv "$CSV" --out "$OUT2"
expect 0 $? "run toy_analysis.py"

"$PY" -c 'import json, pathlib, sys
out = pathlib.Path(sys.argv[1])
(out / "fig_placeholder.txt").write_text("synthetic placeholder figure (text)\n", encoding="utf-8")
(out / "figures_manifest.json").write_text(json.dumps({"figures": ["fig_placeholder.txt"], "note": "synthetic demo figure"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("figure artifacts written")' "$OUT2"

"$PY" "$SG" set --output "$OUT2" --field statistics --value-file "$OUT2/stats.json" --evidence stats.json
"$PY" "$SG" set --output "$OUT2" --field cleaned_table --value-json '"cleaned.csv"' --evidence cleaned.csv
"$PY" "$SG" set --output "$OUT2" --field figures --value-json '["fig_placeholder.txt"]' --evidence figures_manifest.json
"$PY" "$SG" set --output "$OUT2" --field notes --value-json '"合成演示：全部契约字段均已填充。"'
expect 0 $? "set 全部字段"

"$PY" "$SG" checkpoint --output "$OUT2" --work "$WORK2" --note "all fields filled"
"$PY" "$SG" finalize --output "$OUT2" --case "$CASE" --journal "$WORK2/journal.jsonl"
expect 0 $? "finalize complete"

echo "================================================================"
echo "阴性测试：静默 null 必须被拒绝（exit 1）"
echo "================================================================"

NEG="$(mktemp -d /tmp/stagegate_neg.XXXXXX)"
"$PY" "$SG" init --case "$CASE" --output "$NEG" >/dev/null
# 人为制造静默 null：删除 statistics 的 missing_fields 理由条目
"$PY" - "$NEG" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]) / "result.json"
r = json.loads(p.read_text(encoding="utf-8"))
r["missing_fields"] = [m for m in r["missing_fields"] if m["field"] != "statistics"]
p.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("sabotaged: statistics 现在是静默 null")
PYEOF
"$PY" "$SG" finalize --output "$NEG" --case "$CASE"
expect 1 $? "静默 null 被拒绝"

echo "--- 未知字段转 extras 的告警演示 ---"
"$PY" "$SG" set --output "$NEG" --field not_in_contract --value-json '42'
expect 0 $? "未知字段进入 extras（带警告）"
"$PY" -c 'import json, sys; r = json.load(open(sys.argv[1])); assert r["extras"]["not_in_contract"] == 42; print("extras 校验通过:", r["extras"])' "$NEG/result.json"
rm -rf "$NEG"

echo "================================================================"
if [ "$fails" -eq 0 ]; then
  echo "全部断言通过（0 失败）"
  exit 0
else
  echo "存在 $fails 个失败断言"
  exit 1
fi
