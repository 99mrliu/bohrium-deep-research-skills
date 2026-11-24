#!/usr/bin/env bash
# 合成示例端到端运行（envport-core）。所有数据为人工合成，输出不对应任何
# 正式案例结果。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CASE="$HERE/synthetic_case"
WORK="$HERE/work"
OUT="$HERE/out"
EP="$HERE/../scripts/envport.py"
rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"

echo "== 0) 生成合成 SQLite 库（确定性重建）"
python3 "$HERE/make_synthetic_data.py" "$CASE/lab.db"

echo "== 1) env 环境快照 + profile 输入档案"
python3 "$EP" --work "$WORK" --output "$OUT" env
python3 "$EP" --work "$WORK" --output "$OUT" profile "$CASE/mix_data.csv" "$CASE/lab.db"

echo "== 2) clean 按 rules.json 清洗"
python3 "$EP" --work "$WORK" --output "$OUT" clean \
  --table "$CASE/mix_data.csv" --rules "$CASE/rules.json" \
  --out "$WORK/clean.csv" --report "$WORK/clean_report.json"
cp "$WORK/clean.csv" "$OUT/cleaned_mix.csv"

echo "== 3) 统计与查询"
python3 "$EP" --work "$WORK" --output "$OUT" describe --table "$WORK/clean.csv" --columns strength,cement | tee "$WORK/describe.json"
python3 "$EP" --work "$WORK" --output "$OUT" aggregate --table "$WORK/clean.csv" --group-by batch --metrics "strength:mean,strength:std,strength:count" | tee "$WORK/aggregate.json"
python3 "$EP" --work "$WORK" --output "$OUT" ttest --table "$WORK/clean.csv" --column strength --group batch | tee "$WORK/ttest.json" || echo "(ttest 需要恰好 2 组；本例有 3 组，演示显式报错)"
python3 "$EP" --work "$WORK" --output "$OUT" corr --table "$WORK/clean.csv" --x cement --y strength | tee "$WORK/corr.json"
python3 "$EP" --work "$WORK" --output "$OUT" sql --db "$CASE/lab.db" \
  --query "SELECT batch, COUNT(*) AS n, AVG(strength) AS mean_strength FROM specimens GROUP BY batch ORDER BY batch" \
  --out "$WORK/q_batch.csv"

echo "== 4) 图（正常渲染）"
python3 "$EP" --work "$WORK" --output "$OUT" figure --table "$WORK/clean.csv" --kind hist \
  --x strength --title "strength distribution (synthetic)" --xlabel "strength (MPa)" \
  --out "$OUT/fig_strength_hist.png"

echo "== 5) 降级演示：ENVPORT_NO_MPL=1 时诚实降级"
ENVPORT_NO_MPL=1 python3 "$EP" --work "$WORK" --output "$OUT" figure --table "$WORK/clean.csv" \
  --kind scatter --x cement --y strength --title "cement vs strength (synthetic)" \
  --xlabel "cement (kg/m3)" --ylabel "strength (MPa)" --out "$OUT/fig_scatter.png"

echo "== 6) 填充 result.json 并 finalize"
python3 - "$WORK" "$OUT" <<'PY'
import json, sys
work, out = sys.argv[1], sys.argv[2]
r = {"case_id": "synthetic-demo-envport-001", "status": "success",
     "cleaned_table": out + "/cleaned_mix.csv",
     "summary_statistics": json.load(open(work + "/describe.json")),
     "group_comparison": {"aggregate": json.load(open(work + "/aggregate.json")),
                          "welch_ttest_note": "示例含 3 个批次，引擎对 !=2 组显式拒绝（见 run_log）；正式案例中选取任务指定的两组"},
     "query_results": {"batch_summary_csv": work + "/q_batch.csv"},
     "figures": [out + "/fig_strength_hist.png",
                 {"path": out + "/fig_scatter.png", "status": "SKIPPED_no_matplotlib",
                  "data_csv": out + "/fig_scatter.png.data.csv"}],
     "anomalies": ["M03 的 cement/strength 缺失、M07 strength='not_measured' 置为缺失，均未参与统计",
                   "M05 完全重复行 1 行，已去重",
                   "fig_scatter 演示无 matplotlib 降级：未渲染，绘图数据已保存，如实报告"],
     "provenance": {"demo": "SYNTHETIC EXAMPLE: 合成数据，envport.py 真实计算，非正式案例结果"}}
json.dump(r, open(out + "/result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
python3 "$EP" --work "$WORK" --output "$OUT" finalize --input "$CASE"

echo "== 产物 =="
ls -la "$WORK" "$OUT"
