#!/usr/bin/env bash
# 合成示例端到端运行（figure-fidelity）。所有数据为人工合成，输出不对应
# 任何正式案例结果。
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CASE="$HERE/synthetic_case"
WORK="$HERE/work"
OUT="$HERE/out"
FK="$HERE/../scripts/figkit.py"
rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"

echo "== 1) render：直方图与散点图（单位取自数据字典）"
python3 "$FK" render --table "$CASE/concrete_syn.csv" --kind hist --x strength \
  --title "strength distribution (synthetic)" --xlabel "strength (MPa)" \
  --out "$OUT/fig1_hist.png"
python3 "$FK" render --table "$CASE/concrete_syn.csv" --kind scatter --x cement --y strength \
  --title "cement vs strength (synthetic)" --xlabel "cement (kg/m3)" --ylabel "strength (MPa)" \
  --out "$OUT/fig2_scatter.png"

echo "== 2) lint：正常回执应通过"
python3 "$FK" lint --receipts "$OUT/fig1_hist.png.receipt.json" "$OUT/fig2_scatter.png.receipt.json" \
  --dictionary "$CASE/data_dictionary.json"

echo "== 3) lint 拦截演示：单位写错（GPa 不在字典中）应 FAIL"
python3 "$FK" render --table "$CASE/concrete_syn.csv" --kind hist --x strength \
  --title "bad unit demo (synthetic)" --xlabel "strength (GPa)" \
  --out "$WORK/fig_bad.png" >/dev/null
if python3 "$FK" lint --receipts "$WORK/fig_bad.png.receipt.json" --dictionary "$CASE/data_dictionary.json"; then
  echo "!! 意外：错误单位居然通过"
else
  echo ">> 符合预期：lint 拦截了字典中不存在的单位"
fi

echo "== 4) 降级演示：FIGKIT_NO_MPL=1"
FIGKIT_NO_MPL=1 python3 "$FK" render --table "$CASE/concrete_syn.csv" --kind line --x age --y strength \
  --title "strength vs age (synthetic)" --xlabel "age (day)" --ylabel "strength (MPa)" \
  --out "$OUT/fig3_line.png"

echo "== 5) 写 result.json 并 check"
python3 - "$OUT" <<'PY'
import json, sys
out = sys.argv[1]
r = {"case_id": "synthetic-demo-figkit-001", "status": "success",
     "figures": [out + "/fig1_hist.png", out + "/fig2_scatter.png",
                 {"path": out + "/fig3_line.png", "status": "SKIPPED_no_matplotlib",
                  "data_csv": out + "/fig3_line.png.data.csv"}],
     "anomalies": ["concrete_syn.csv 第 5 行 cement/strength 缺失，绘图时排除（见各 receipt 的 n_excluded_missing）",
                   "fig3 演示无 matplotlib 降级：未渲染，绘图数据已保存"],
     "provenance": {"demo": "SYNTHETIC EXAMPLE: 合成数据，figkit 真实渲染，非正式案例结果"}}
json.dump(r, open(out + "/result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
python3 "$FK" check --result "$OUT/result.json"

echo "== 产物 =="
ls -la "$OUT"
