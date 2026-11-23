# draw.io (mxGraph) 映射词汇表 — drawio-dual-source

本文件是 geometry 模型 ↔ mxCell 的唯一权威映射。emit(mxgraph_write.py) 与回读
(mxgraph_parse.py) 必须同时遵守；新增样式时先改这里。

## 文件骨架

```
mxfile(host="app.diagrams.net", agent, type="device", version)
 └─ diagram(name, id)
     └─ mxGraphModel(dx,dy,grid,...,pageWidth,pageHeight, data-geometry-sidecar?)
         └─ root
             ├─ mxCell id="0"
             ├─ mxCell id="1" parent="0"
             └─ ...业务 mxCell...
```

## 区室 → swimlane

| geometry | mxCell |
|---|---|
| compartment | `style="swimlane;fontSize=14;startSize=24;verticalAlign=top;align=left;spacingLeft=12;fillColor=<band色>;strokeColor=#94a3b8;html=1;"`, vertex=1, parent="1" |
| id | `compartment:<id>` |
| 子节点坐标 | 实体 parent 指向 swimlane 时 mxGeometry 为**相对坐标**；回读时加回泳道原点 |

band 固定填充色：extracellular `#f8fafc`，membrane `#fde68a`，cytosol `#f0fdf4`，nucleus `#eff6ff`。

## 实体 → vertex mxCell（id 恒为 `entity:<id>`）

| type | style 要点 |
|---|---|
| protein | `rounded=1;arcSize=18;fillColor=<fill>` |
| gene | `rounded=1;arcSize=18;fillColor=<fill>;fontStyle=2`（斜体=2） |
| small_molecule | `ellipse;fillColor=<fill>` |
| complex | `shape=ext;double=1;fillColor=<fill>`（双线矩形） |
| receptor | `rounded=0;fillColor=<fill>`（高矩形，**位置**横跨 membrane 泳道带） |
| generic | `rounded=1;arcSize=18;fillColor=#f1f5f9` |

公共片段：`whiteSpace=wrap;html=1;fontSize=13;fontFamily=Helvetica;strokeColor=#334155;strokeWidth=1.6;`
数据编码（如 log2FC）只改写 `fillColor`，不改变形状语义。

## 边 → edge mxCell（id 恒为 `edge:<id>`）

公共片段：`edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;jettySize=auto;orthogonalLoop=1;strokeWidth=2;`
source/target 指向 `entity:<id>`；内部拐点写入 `mxGeometry/Array/as=points` 的 mxPoint。

| kind | endArrow | 附加 | 颜色 | 标签 |
|---|---|---|---|---|
| activation | classic (endFill=1) | — | `#15803d` | — |
| inhibition | **bar** (endFill=0) | T 形抑制端 | `#b91c1c` | — |
| binding | open (endFill=0) | — | `#475569` | — |
| phosphorylation | classic | — | `#7e22ce` | `P` |
| ubiquitination | classic | — | `#7e22ce` | `Ub` |
| transport | classic | `dashed=1;dashPattern=6 4` | `#1d4ed8` | — |
| uncertain | classic | `dashed=1` | `#64748b` | `?` |

任何边带 `evidence=uncertain` 时：强制 `dashed=1`、颜色 `#64748b`、无标签时加 `?`。

## data-* 属性（往返保真）

每个业务 mxCell 携带：
- 实体：`data-etype`、`data-compartment`、`data-source`（文献定位，如 "paper.pdf p.4 Fig.2"）
- 边：`data-ekind`、`data-evidence`、`data-source`
- 区室：`data-ctype="compartment"`、`data-band`
- mxGraphModel：`data-geometry-sidecar="<geometry.json 文件名>"`

## 往返规则（什么能活下来）

| 操作 | 结果 |
|---|---|
| edit_cells.py / 手工 XML 编辑 | 全部 data-* 属性、id、样式存活，可无损回读 |
| diagrams.net GUI 里移动/改色 | 几何、fillColor、value 存活，可回读 |
| diagrams.net GUI 保存 | **可能剥离 data-* 自定义属性**；回读退化为样式推断（endArrow/dashed/label），无法确定 kind 的边记为 uncertain 并写入 `_skipped`/exceptions |
| 无 `entity:/edge:/compartment:` 前缀且无 data-etype 的 cell | 回读跳过并在 `_skipped` 中如实报告 |
