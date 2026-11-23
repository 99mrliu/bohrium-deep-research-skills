# 最小调用示例（示例，非正式案例结果）

以下数据与输出均为演示接口用的**示意样例**，不来自正式测试案例。

## 示意输入 assay.csv

```csv
cell_line,dose,viability,sd
A375,0,100,4.2
A375,10,72,3.8
A375,100,31,2.9
SKMEL28,0,100,5.1
SKMEL28,10,85,4.4
SKMEL28,100,66,3.3
```

## 调用方式

```bash
python3 /skills/weekly-skill/scripts/freeze_data.py \
  --inputs /input/assay.csv --outdir /app/output/data_snapshot
# 读 data_provenance.json 取得 sha256，写入 figure.spec.json 的 source.sha256
python3 /skills/weekly-skill/scripts/render_chart.py \
  --spec /app/work/figure.spec.json --snapshot /app/output/data_snapshot \
  --outdir /app/output --basename figure --profile generic_1col
python3 /skills/weekly-skill/scripts/check_consistency.py \
  --spec /app/work/figure.spec.json --snapshot /app/output/data_snapshot \
  --legend-map /app/output/figure.legend_map.json \
  --svg /app/output/figure.svg --out /app/output/consistency_report.json
```

## 示意 figure.spec.json

```json
{
  "spec_version": 1,
  "chart_type": "grouped_bar",
  "title": "Cell viability under vemurafenib (example)",
  "data_file": "assay.csv",
  "x": {"column": "dose", "label": "Vemurafenib dose", "unit": "nM"},
  "y": {"column": "viability", "label": "Cell viability", "unit": "%"},
  "category_column": "cell_line",
  "yerr_column": "sd",
  "source": {"sha256": "<按实际快照填写>", "locator": "example data"}
}
```

## 示意输出

- `figure.svg`（文字可选中编辑）/ `figure.pdf` / `figure.png`（300 dpi）/
  `figure.tiff`（有 Pillow 时）。
- `figure.legend_map.json`：`[{"category":"A375","color":"#4C78A8",
  "marker":"o"},{"category":"SKMEL28","color":"#F58518","marker":"s"}]`。
- `consistency_report.json`：`status: pass`。
  若把 spec 的 category_column 改成不存在的列 → fail（columns_exist）；
  若手工在 SVG 里加图例项 → fail（legend_equals_data_categories 或
  anti_hallucination_text_gate）；若渲染后改动数据文件 → fail
  （data_version_match）。
- 数据更新演示：在 CSV 中加入第三个细胞系后重跑三步命令，图例自动变为
  3 项、配色自动扩展，无需手工改图。

## result.json

`case_id` + `output_contract` 各键 + `status`/`sources`（含数据快照
sha256）/`uncertainty`/`change_log`。
