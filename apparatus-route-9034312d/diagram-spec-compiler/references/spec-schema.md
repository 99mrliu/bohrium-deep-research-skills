# figure_spec.json — 声明式图稿 spec 全字段文档

编译器输入的唯一文件。Agent 从科研材料中抽取结构后手写此 JSON；
所有版式计算由 `scripts/compile_figure.py` 完成，**不要在 spec 里写坐标**。

## 顶层结构

```json
{
  "kind": "apparatus | stepflow | roadmap",   // 必填，图稿类型
  "title": "图题",                             // 必填，非空
  "canvas": "auto" 或 {"width_mm": 190, "height_mm": 120},
  "styles": { "flow_types": {...}, "palette": {...} },
  "nodes": [ ... ],   // 必填，≥1
  "edges": [ ... ],   // 可空数组
  "stages": [ ... ]   // 仅 roadmap 必填
}
```

## kind 语义

| kind | 用途 | 版式 |
|---|---|---|
| `apparatus` | 实验装置/工艺流程示意图 | 按 DAG 分层排成列，列内垂直居中堆叠 |
| `stepflow` | 实验步骤流程图 | 同上；`kind:"step"` 节点必须带整数 `num`，校验 S1..Sn 连续 |
| `roadmap` | 技术路线图 | `stages` 渲染为横向泳道（箭头带），节点按 `stage` 落入泳道 |

## canvas

- `"auto"`（推荐）：编译器按内容计算所需毫米尺寸，记入 render_log.canvas。
- `{"width_mm","height_mm"}`：固定画布（如期刊栏宽 90/140/190mm）。内容溢出时
  **整体等比缩小**，缩放因子记入 render_log.scale 并产生 warning。

## styles.flow_types

键为流型名（边通过 `flow_type` 引用）。内置默认三种，可覆盖或新增：

```json
"flow_types": {
  "material":    {"stroke": "#1565c0", "dash": "",    "width": 1.8, "color": "#1565c0"},
  "energy":      {"stroke": "#e65100", "dash": "7 3", "width": 1.6, "color": "#e65100"},
  "information": {"stroke": "#2e7d32", "dash": "2 3", "width": 1.3, "color": "#2e7d32"}
}
```

- `stroke`：线条颜色（同时用于箭头 marker 填充）；`color`：边标签文字色（缺省同 stroke）。
- `dash`：SVG stroke-dasharray，空串 = 实线。
- **图例按构造生成**：图例条目直接取自本表与实际使用的流型集合，与图形永不脱节。

## styles.palette（可选，缺省用内置值）

`node_fill, node_stroke, text, subtext, background, title, badge_fill, note_fill,
lane_fills`（泳道底色数组，循环使用）。

## nodes[]

```json
{"id": "rxr",                  // 必填，全局唯一
 "label": "固定床反应器",       // 必填，非空
 "kind": "unit",               // unit(默认)|step|stage|data|note
 "sublabel": "R-101",          // 可选，小号灰字（位号/条件等）
 "num": 3,                     // 仅 stepflow 的 step 节点必填（整数，1..n 连续）
 "stage": "p2",                // 仅 roadmap：所属泳道 id
 "parts": ["催化剂床层", "夹套"], // 可选：unit 子隔室，逐行渲染
 "source": {"locator": "paper.pdf p.3 Fig.2", "quote": "原文短句"}}
```

节点形状：`unit`=圆角矩形（可带子隔室）；`step`=矩形+编号徽章；`stage`=箭头形
（chevron）；`data`=平行四边形（储罐/数据）；`note`=虚线注释框。

`source` 为轻量溯源：locator 指明出处位置，quote 为原文短句（合成示例写"合成数据：…"）。
缺失只产生 warning，不阻塞。

## edges[]

```json
{"id": "e06",                  // 可选；缺省自动编号 e00,e01,…（显式 id 更利于编辑 diff）
 "from": "sep", "to": "hx",    // 必填，必须引用存在的节点 id；不允许自环
 "flow_type": "material",      // 必填，必须在 styles.flow_types（或内置默认）中定义
 "label": "循环氢气（回流）",   // 建议非空（空 label 仅 warning）
 "source": {"locator": "…", "quote": "…"}}
```

- **回流边无需声明**：编译器用 SCC+DFS 自动检测环，回边以底部通道绕行、
  强制虚线、反向箭头渲染，并自动加入图例。
- 跨层前向边（跨越 ≥1 层）自动走底部通道正向绕行，不会穿过中间节点。

## stages[]（仅 roadmap）

```json
"stages": [{"id": "p1", "label": "阶段一 基础研究"}, …]
```

顺序即泳道自上而下顺序。每个节点用 `stage` 字段引用；未知引用为 error。

## 完整注释示例

见 `examples/minimal/figure_spec.json`（合成示例）：8 节点、9 条边、3 种流型、
2 条回流边（e06 物料循环、e08 信息联锁）、1 条跨层能量边（e07）、unit 子隔室、
完整 source 溯源。对应产物 figure.svg / validation_report.json /
render_log.json / export_report.json 同目录可查。

## 校验规则速查（check_spec.py）

ERROR（退出码 1）：kind/title/nodes 非法；节点 id 重复；label 空；节点 kind 未知；
边 id 重复；边端点未知；flow_type 未定义；自环；stepflow num 缺失/不连续；
roadmap stages 缺失/id 重复/stage 引用未知。
WARNING（不阻塞）：缺 source、边 label 空、重复边 (from,to,flow_type)、孤立节点、
roadmap 节点未指定 stage（落入第一泳道）。
