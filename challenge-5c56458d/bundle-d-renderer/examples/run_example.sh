#!/bin/sh
# 合成示例（synthetic demo, NOT a formal case result）：
# 现场生成合成结果 CSV，跑 chart_select -> render_chart -> figure_caption。
set -eu
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d /tmp/chart-demo.XXXXXX)"
echo "demo workspace: $WORK"

cat > "$WORK/result.csv" <<'CSV'
group_id,n,mean_metric
control,21,20.59
treat_a,19,16.08
treat_b,20,16.54
CSV

python3 "$SKILL_DIR/scripts/chart_select.py" --csv "$WORK/result.csv" \
  --question "compare groups" --out "$WORK/rec.json"
python3 "$SKILL_DIR/scripts/render_chart.py" --csv "$WORK/result.csv" \
  --type bar --x group_id --y mean_metric --y-unit MPa \
  --title "Mean metric by group (synthetic demo)" --out "$WORK/fig1"
python3 "$SKILL_DIR/scripts/figure_caption.py" --figure "$WORK/fig1.figure.json" \
  --caveat "synthetic demo data, not a formal case result" \
  --out "$WORK/fig1.caption.md"
echo "--- caption ---"; cat "$WORK/fig1.caption.md"
ls -la "$WORK"
