# manifest.json 字段规范（v1）

实体-关系清单是图的唯一事实源。渲染脚本只认识这里声明的字段。

## 顶层结构

```json
{
  "manifest_version": 1,
  "figure": {
    "title": "图题（须与来源中的图号/主题对应）",
    "canvas": {"width": 1000, "height": 640},
    "source": {"file": "材料文件名", "locator": "Figure 3, p.7"},
    "language": "en"
  },
  "classes": {
    "receptor":  {"color": "#4C78A8", "label": "Receptor"},
    "kinase":    {"color": "#F58518", "label": "Kinase"},
    "tf":        {"color": "#54A24B", "label": "Transcription factor"},
    "gene":      {"color": "#B279A2", "label": "Gene"},
    "compound":  {"color": "#E45756", "label": "Compound"},
    "process":   {"color": "#9D755D", "label": "Process"},
    "phenotype": {"color": "#72B7B2", "label": "Phenotype"},
    "other":     {"color": "#8C8C8C", "label": "Other"}
  },
  "entities": [ ... ],
  "groups": [ ... ],
  "relations": [ ... ],
  "annotations": [ ... ],
  "uncertainty": [ "方向存疑、材料缺失等自由文本说明" ]
}
```

- `classes` 可按来源实际分类增删；颜色必须为十六进制；图例由实际用到的
  class 与 relation type 自动生成，未使用的不进图例。
- `canvas` 缺省 1000x640；实体超过 ~25 个时加大画布或拆 `subfigures`。

## entities[i]

```json
{
  "id": "egfr",
  "label": "EGFR",
  "class": "receptor",
  "grid": {"col": 0, "row": 0},
  "box": {"x": 80, "y": 60, "w": 130, "h": 48},
  "evidence": {"locator": "p.4 左栏第2段", "quote": "EGFR recruits and activates RAS"}
}
```

- `id`：小写字母/数字/下划线，全清单唯一；图的 SVG 元素 id 由它派生。
- `label`：图面文字，**必须与来源中的名称拼写一致**（含大小写）。
- `grid` 与 `box` 二选一；`box` 优先。`grid` 的 col 表示层级列（0 起，
  上游在左），row 表示列内行序。grid 缺省时按关系拓扑自动分层。
- `evidence.locator` 与 `evidence.quote` **均为必填**，缺一则校验 fail。

## groups[i]（包含/分区关系专用）

```json
{"id": "nucleus", "label": "Nucleus", "members": ["stat3", "myc"],
 "box": {"x": 520, "y": 60, "w": 380, "h": 240},
 "evidence": {"locator": "p.5 图注", "quote": "p-STAT3 translocates into the nucleus"}}
```

- 只表达"包含/位于"语义；并列关系不建 group。`box` 缺省时由成员外接矩形
  加 padding 自动生成。成员必须是已声明的 entity id。

## relations[i]

```json
{"id": "r1", "from": "egfr", "to": "ras", "type": "activates",
 "label": "",
 "evidence": {"locator": "p.4 左栏第2段", "quote": "EGFR activates RAS"}}
```

- `type` 只能取受控词表（见 relation_vocabulary.md）：activates / inhibits /
  binds / produces / degrades / translocates / modifies / contains / unclear。
- 方向一律 `from → to`：activates 表示 from 激活 to；inhibits 表示 from 抑制
  to（脚本画 T 形端头）；translocates 表示 from 移动到 to（to 可为 group）。
- `label` 可放空串；只在来源明确给出修饰语（如 "Tyr705"）时填写。

## annotations[i]（可选，图面补充文字）

```json
{"id": "note1", "text": " serum starvation 16 h",
 "grid": {"col": 0, "row": 3},
 "evidence": {"locator": "Methods p.9", "quote": "cells were serum-starved for 16 h"}}
```

图面上除标题/标签/图例外的任何文字都必须在这里声明并带来源，否则反幻觉
校验判 fail。
