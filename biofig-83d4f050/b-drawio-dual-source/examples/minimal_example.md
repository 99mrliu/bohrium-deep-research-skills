# 最小端到端示例（SYNTHETIC 合成示例，非真实 case）

以下命令用 `assets/example-geometry.json`（合成玩具通路）与
`assets/example-data.csv`（合成数据）跑通全部三个阶段。假设工作目录为
`/app/work`，产物到 `/app/output`。

```bash
SK=/skills/weekly-skill
mkdir -p /app/work /app/output

# --- 阶段 2/3：geometry -> drawio + SVG + PNG/PDF ---
python3 $SK/scripts/geometry.py \
  --geometry $SK/assets/example-geometry.json \
  --out /app/work/geometry.laid.json
python3 $SK/scripts/mxgraph_write.py \
  --geometry /app/work/geometry.laid.json \
  --out /app/output/figure.drawio --sidecar geometry.laid.json
python3 $SK/scripts/svg_write.py \
  --geometry /app/work/geometry.laid.json --out /app/output/figure.svg
python3 $SK/scripts/mpl_export.py \
  --geometry /app/work/geometry.laid.json \
  --out-dir /app/output --basename figure

# --- 阶段 4：校验 ---
python3 $SK/scripts/verify_exports.py \
  --geometry /app/work/geometry.laid.json \
  --drawio /app/output/figure.drawio --svg /app/output/figure.svg \
  --png /app/output/figure.png --pdf /app/output/figure.pdf \
  --out /app/work/verify.json

# --- 编辑模式：三个 cell 级操作 + 版本备份 + 编辑日志 + 重导出 ---
cat > /app/work/ops.json <<'EOF'
[
  {"op": "set-label", "cell": "entity:akt", "value": "AKT1"},
  {"op": "set-color", "cell": "entity:akt", "value": "#ff8800"},
  {"op": "add-edge", "from": "akt", "to": "p21", "kind": "inhibition"}
]
EOF
python3 $SK/scripts/edit_cells.py \
  --drawio /app/output/figure.drawio --ops /app/work/ops.json \
  --edit-record /app/work/edit-record.json \
  --reexport --geometry-out /app/work/geometry.edited.json
python3 $SK/scripts/svg_write.py \
  --geometry /app/work/geometry.edited.json --out /app/output/figure_edited.svg
python3 $SK/scripts/mpl_export.py \
  --geometry /app/work/geometry.edited.json \
  --out-dir /app/output --basename figure_edited

# --- 图表模式 ---
python3 $SK/scripts/build_chart.py \
  --data $SK/assets/example-data.csv --kind bar \
  --x gene --y log2FC --title "log2FC (synthetic)" \
  --out-dir /app/output --basename chart_expr \
  --content-map-out /app/work/chart-content-map.json

# --- result.json ---
python3 $SK/scripts/build_result.py \
  --case-id synthetic-demo --status success \
  --editable-source /app/output/figure.drawio \
  --editable-source /app/output/figure.svg \
  --export-artifact /app/output/figure.png \
  --export-artifact /app/output/figure.pdf \
  --content-map /app/work/chart-content-map.json \
  --compliance /app/work/verify.json \
  --exceptions '[]' \
  --out /app/output/result.json
```

预期：`figure.drawio` 可在 diagrams.net 直接打开（swimlane 三区室、5 个实体、
4 种边型，抑制边为 T 形端）；`figure.svg` 含四个 layer 分组与 `<metadata>` 内嵌
geometry；编辑后 `versions/figure.v1.drawio` 备份存在，`edit-record.json` 有 3 条
带 before/after 片段的记录，`geometry.edited.json` 中 AKT 标签为 AKT1、填充
`#ff8800`、新增 `edge:edit-1`。
