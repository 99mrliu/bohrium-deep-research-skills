#!/usr/bin/env bash
# 合成示例端到端运行（run-forensics）。所有数据为人工合成，输出不对应任何
# 正式案例结果。
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CASE="$HERE/synthetic_case"
WORK="$HERE/work"
OUT="$HERE/out"
RC="$HERE/../scripts/runcap.py"
rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"

python3 "$HERE/make_synthetic_data.py" "$CASE/lab.db" >/dev/null

echo "== 0) init：输入哈希清单 + result.json 骨架"
python3 "$RC" init --input "$CASE" --work "$WORK" --output "$OUT"

echo "== 1) clean（runcap 包装）"
python3 "$RC" exec --work "$WORK" --tag clean --hash "$CASE/signals.csv" -- \
  python3 "$HERE/step_clean.py" "$CASE/signals.csv" "$WORK/clean.csv" || { echo "clean 失败"; exit 1; }

echo "== 2) stats（runcap 包装）"
python3 "$RC" exec --work "$WORK" --tag stats --hash "$WORK/clean.csv" -- \
  python3 "$HERE/step_stats.py" "$WORK/clean.csv" "$WORK/stats.json" || { echo "stats 失败"; exit 1; }

echo "== 3) sql：第一次故意查错表名（演示失败现场捕获）"
python3 "$RC" exec --work "$WORK" --tag sql1 --hash "$CASE/lab.db" -- \
  python3 -c "
import sqlite3
con = sqlite3.connect('$CASE/lab.db')
print(con.execute('SELECT channel, COUNT(*) FROM registery GROUP BY channel').fetchall())
"
echo ">> 上一步退出码非零是预期行为；failure_record 已入台账"

echo "== 4) sql：核对 sqlite_master 后以同 tag 重跑（形成重试链）"
python3 "$RC" exec --work "$WORK" --tag sql1 --hash "$CASE/lab.db" -- \
  python3 -c "
import sqlite3, json
con = sqlite3.connect('$CASE/lab.db')
rows = con.execute('SELECT channel, COUNT(*) FROM registry GROUP BY channel ORDER BY channel').fetchall()
json.dump(rows, open('$WORK/sql1.json', 'w'), ensure_ascii=False)
print('sql1:', rows)
" || { echo "sql1 修复后仍失败"; exit 1; }

echo "== 5) 填充 result.json"
python3 - "$WORK" "$OUT" <<'PY'
import json, sys
work, out = sys.argv[1], sys.argv[2]
r = json.load(open(out + "/result.json", encoding="utf-8"))
r.update({
  "status": "success",
  "cleaned_table": work + "/clean.csv",
  "summary_statistics": json.load(open(work + "/stats.json", encoding="utf-8")),
  "query_results": {"channel_counts": json.load(open(work + "/sql1.json", encoding="utf-8"))},
  "anomalies": ["signals.csv 含 1 个 NA 缺失与 1 个完全重复行，清洗后 7->5 行",
                "sql1 第一次执行表名拼写错误（registery），经核对 sqlite_master 修复，重试链见 run_summary.md"],
})
r["provenance"]["demo"] = "SYNTHETIC EXAMPLE: 合成数据，非正式案例结果"
json.dump(r, open(out + "/result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
cp "$WORK/clean.csv" "$OUT/cleaned_signals.csv"

echo "== 6) report / replay / seal"
python3 "$RC" report --work "$WORK"
python3 "$RC" replay --work "$WORK"
python3 "$RC" seal --input "$CASE" --work "$WORK" --output "$OUT"
SEAL_RC=$?

echo "== 7) 真实重放 replay.sh（复核者视角）"
bash "$WORK/replay.sh" && echo "REPLAY 全部成功"

echo "== 产物 =="
ls -la "$WORK" "$OUT"
echo "== run_summary.md =="
cat "$WORK/run_summary.md"
exit $SEAL_RC
