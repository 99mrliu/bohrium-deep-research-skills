# figure.spec.json 字段规范（v1）

绑定声明是图表的唯一事实源：渲染脚本只画这里声明的绑定，校验脚本按这里
对账。所有列名必须与数据快照中的实际列名完全一致（区分大小写）。

```json
{
  "spec_version": 1,
  "chart_type": "grouped_bar",
  "title": "Cell viability under inhibitor treatment (example)",
  "data_file": "assay.csv",
  "x":        {"column": "dose",      "label": "Vemurafenib dose", "unit": "nM"},
  "y":        {"column": "viability", "label": "Cell viability",   "unit": "%"},
  "category_column": "cell_line",
  "yerr_column": "sd",
  "na_label": null,
  "legend_title": "Cell line",
  "palette": ["#4C78A8", "#F58518", "#54A24B"],
  "annotations": [],
  "source": {"sha256": "<freeze_data.py 输出的哈希>", "locator": "Supplementary Table 2"}
}
```

## 字段说明

| 字段 | 必填 | 说明 |
|-|-|-|
| chart_type | 是 | bar / grouped_bar / stacked_bar / line / scatter |
| data_file | 是 | 快照目录内的文件名（freeze_data.py 复制后的 basename） |
| x / y | 是 | `column` 必须存在；`label` 缺省用列名；`unit` 存在时渲染为 "label (unit)"，校验要求该单位确实出现在图内 |
| category_column | 否 | 驱动图例与配色的分类列；图例项=该列实际取值（按出现顺序），**不允许手工另写图例标签** |
| yerr_column | 否 | 误差棒列，数值必须来自来源数据，脚本不做任何统计估计 |
| na_label | 否 | 分类缺失时的替代标签；缺省则剔除缺类行并在 render_log 记录 |
| palette | 否 | 十六进制颜色列表，长度必须 ≥ 分类数，否则报错 |
| annotations | 否 | 图面补充文字 `[{"text": ...}]`，须可追溯到来源；未声明的文字会被反幻觉门禁判 fail |
| source.sha256 | 强烈建议 | 填 freeze_data.py 报告的快照哈希；不一致即判定数据漂移 |
| source.locator | 是 | 数据在来源材料中的位置（表号/页码/补充材料条目） |

## 规则

1. 图例的唯一事实源是 `category_column` 的取值；分类数变 → 图例与配色
   自动变 → 重跑 render + check 即同步。
2. scatter/line 的 x 列必须为数值；bar 系的 x 列作为分类轴。
3. 不要在 spec 里写数据中不存在的数值、列名或分类；校验脚本逐项核对。
4. 多子图：每个子图一份 spec 与 basename，分开渲染与校验。
