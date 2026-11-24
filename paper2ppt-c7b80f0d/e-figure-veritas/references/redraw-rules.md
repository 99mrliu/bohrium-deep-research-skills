# 重绘规则（redraw-rules）

## 何时允许重绘

同时满足才可重绘：

1. 存在机器可读来源：`data.csv` 或已从论文表格逐值抽出的 JSON/CSV；
2. 原图分辨率不足、风格与模板冲突、或需要合并/重排系列；
3. 重绘前后都跑得动 `redraw_verify.py`（容差 0）。

不允许：凭位图"目测读数"重绘（人眼读数不是机器可读来源）；
不允许：为美观平滑/插值后不标注。

## 数值零漂移规则

- spec.json 中的 `x.values` 与每个 `series.values` 由 Agent 从来源逐值抄入；
- `redraw_verify.py spec.json --data data.csv` 逐值 `float == float` 精确比对，
  容差 0；任何 mismatch → 退出码 1，该图**不得**入 deck；
- 单位换算（如 mT → T）属于漂移，除非换算在 spec 中显式声明且核验器支持；
  本版本核验器不支持换算，请直接重标来源列。

## provenance 标注格式

重绘图题注（图下小字与图内脚注）统一格式：

```
redrawn from Table X (values verified)
```

deck.json 中该图条目：

```json
{"id": "fig1", "provenance": "redrawn-from-data",
 "path": "figs/redrawn_fig1.png"}
```

三值 provenance 语义：

- `original-crop`：从论文 PDF 抽出的原始位图/整页渲染，未改一个像素；
- `redrawn-from-data`：用机器可读数据确定性重绘，且通过零漂移核验；
- `schematic-reference`：论文中的示意图，仅作概念参考，不作证据。
