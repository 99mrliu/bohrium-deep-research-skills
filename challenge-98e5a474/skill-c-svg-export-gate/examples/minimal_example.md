# 最小调用示例（示例，非正式案例结果）

以下为演示接口用的**示意样例**，不来自正式测试案例。源 SVG 可用任何符合
`resources/layer_conventions.md` 的图（例如实体-关系渲染器的输出）。

## 场景：把图中一个标签 "EGFR" 改为 "HER2"，并把一条抑制边标红

### 1. lint 源文件

```bash
python3 /skills/weekly-skill/scripts/svg_lint.py \
  --svg /app/work/figure.svg --out /app/output/lint_report.json
# => {"status":"pass","layers":["background","groups","relations",
#      "entities","labels","legend"], ...}
```

### 2. 写操作单 edits.json

```json
{"edits": [
  {"op": "retext",   "id": "ent-egfr", "text": "HER2"},
  {"op": "set_attr", "id": "rel-r3",   "attr": "stroke", "value": "#B03030"}
]}
```

### 3. 外科式应用

```bash
python3 /skills/weekly-skill/scripts/apply_edit.py \
  --svg /app/work/figure.svg --edits /app/work/edits.json \
  --out /app/output/figure_edited.svg --log /app/output/edit_log.json
# => {"status":"ok","applied":2,"bytes_delta":...}
```

`diff figure.svg figure_edited.svg` 只显示两处改动，其余字节逐位相同——
"只改了这两处"可独立核验。若操作单引用不存在的 id，脚本列出
lint 报告中的可用 id 并报错，不产出半成品。

### 4. 合规导出

```bash
python3 /skills/weekly-skill/scripts/export_gate.py \
  --svg /app/output/figure_edited.svg --profile nature_1col \
  --outdir /app/output --basename figure \
  --report /app/output/export_compliance.json
# => {"status":"pass","formats":{"pdf":"pass","png":"pass","eps":"pass"}}
#    或如实报告 degraded（后端缺失）/ fail（尺寸、DPI、字体不达标）
```

### 5. 示意输出

- `figure_edited.svg`：分层源文件（改动可 diff 核验）。
- `figure.pdf` / `figure.png`（300 dpi，像素宽度 ≈ 89mm×300/25.4）/
  `figure.eps`（有 inkscape/rsvg-convert 时）。
- `lint_report.json`、`edit_log.json`、`export_compliance.json`。
- `result.json`：`case_id` + `output_contract` 各键 + status/sources/
  uncertainty/change_log（合并编辑日志）。
