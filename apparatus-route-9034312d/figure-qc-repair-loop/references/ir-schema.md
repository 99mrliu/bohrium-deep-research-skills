# Figure IR Schema（轻量中间表示）

IR 是唯一由 agent 编辑的制品（`/app/work/figure_ir.json`）；SVG 永远由
`scripts/ir_render.py` 从 IR 重新生成。一个 IR 描述一张装置/流程/物料/路线图。

## 顶层结构

```json
{
  "title": "图题（string）",
  "nodes": [ /* Node，见下 */ ],
  "edges": [ /* Edge，见下 */ ],
  "legend": [ /* 可选；缺省时渲染器按实际用到的边类型自动生成 */ ],
  "canvas": "auto"            // 或 {"width_mm": 180, "height_mm": 100}
}
```

## Node

```json
{"id": "n1",                       // 必填，全图唯一；边用 id 引用
 "label": "培养基配制",            // 必填，显示文字；应尽量使用源文本原词
 "kind": "step",                   // equipment | material | step | input | output（仅影响底色）
 "order": 1,                       // 可选，整数：有序步骤编号，渲染为 S1..Sn 徽章，
                                   //   且决定分层（层 = order-1）与 REVERSED_FLOW/NUMBERING_GAP 检查
 "source": {"locator": "excerpt.txt 第3行",   // 必填：来源定位（文件名+页/行/表）
            "quote": "步骤1 培养基配制"}}      // 必填：源文本逐字片段（轻度核对，UNVERIFIED_QUOTE）
```

## Edge

```json
{"id": "e2",                       // 可选；缺省自动 e1,e2,...
 "from": "n2", "to": "n3",         // 必填，必须是已存在的节点 id（否则 DANGLING_EDGE）
 "kind": "material",               // material 物料 | energy 能量 | information 信息 | sequence 步骤顺序
 "label": "藻液",                  // 可选，边中点标注
 "source": {"locator": "...", "quote": "..."}}   // 同 Node
```

边类型决定颜色/线型（规范调色板，渲染器对**边**始终使用它）：

| kind | 颜色 | 线型 | 默认图例名 |
|---|---|---|---|
| material | #1f77b4 蓝 | 实线 | 物料流 |
| energy | #d62728 红 | 虚线 4,2 | 能量流 |
| information | #2ca02c 绿 | 点线 1,3 | 信息流 |
| sequence | #666666 灰 | 实线 | 步骤顺序 |

`sequence` 边，或两端节点都带 order 的边，具有顺序语义：必须 from.order < to.order，
否则 REVERSED_FLOW。

## legend（可选，慎用）

```json
"legend": [{"kind": "material", "label": "物料流", "color": "#1f77b4", "dash": null}]
```

- **缺省（推荐）**：渲染器按图中实际用到的边类型自动生成图例，天然一致。
- 显式给出时渲染器**信任原文**（label/color/dash 可覆盖图例外观，但不影响边的真实样式）。
  因此显式 legend 是 LEGEND_MISMATCH 的常见来源——编辑旧图时残留的旧颜色会被检出；
  修复办法是删除自定义 color/dash，或删除整个 legend 字段改回自动。

## canvas

- `"auto"`（推荐）：渲染器按布局自动计算画布，不会 CANVAS_OVERFLOW。
- `{"width_mm": 180, "height_mm": 100}`：固定毫米尺寸；给小了会被 CANVAS_OVERFLOW 检出。

## source.quote 约定

- 从 `pdftotext -layout` 抽取文本或表格文本中**逐字复制**（可截取片段）。
- QC 做归一化（去空白/标点、小写）子串匹配；找不到 → UNVERIFIED_QUOTE（warn，不阻断）。
- 该字段是溯源记录，不做证据门控（其他 bundle 的职责）；本 bundle 只做轻核对。

## 最小示例

见 `examples/minimal/figure_ir.v2.json`（干净版）与 `figure_ir.v1.json`（预埋缺陷版）。
