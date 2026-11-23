# 证据台账（ledger.json）规范

台账是本技能的核心交付物：图中出现的每一个实体、关系、步骤、流都必须先在台账中登记，
并携带逐字证据（quote）。渲染器只读台账；门禁只验台账。**台账之外，图上不得有任何事实性内容。**

## 顶层结构

```json
{
  "meta": {"title": "图标题", "description": "可选说明"},
  "case_id": "来自 /input/case.json，逐字复制",
  "elements": [ /* Element 对象数组，顺序即台账顺序 */ ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `meta.title` | string | 建议 | 渲染为图标题；缺省时渲染器用默认标题，`--title` 可覆盖 |
| `meta.description` | string | 否 | 自由说明，不渲染 |
| `case_id` | string | 必填 | 与 case.json 一致，渲染进图副标题并写入 result.json |
| `elements` | array | 必填 | 至少 1 个元素；空台账渲染器拒绝出图 |

## Element 对象

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | 是 | 全局唯一；建议带种类前缀，如 `app-reactor-1`、`step-3`。渲染为 `data-eid` |
| `kind` | enum | 是 | `apparatus-unit`（装置单元）/ `step`（步骤）/ `flow`（物料流、数据流节点）/ `stage`（阶段、路线分期）/ `data-item`（数据、产物、指标）/ `note`（注记） |
| `label` | string | 是 | 图上文字。应与 quote 内容一致，可精简但**不得引入 quote 没有的参数/数值** |
| `attributes` | object | 否 | 附加键值（如 `{"温度":"37 °C","转速":"180 rpm"}`）。键值中的事实性内容同样必须出自 quote |
| `connects_to` | string[] | 否 | 目标元素 `id` 列表，渲染为带箭头连线。连线本身是"关系"的声明，其事实依据写在 `source.quote` 中 |
| `order` | int | 否 | 列（层）序号，从左到右升序；同 order 的元素同列竖排。若**全部**元素都有 order 则按 order 分层；否则按 `connects_to` 自动拓扑分层 |
| `source` | object | 是* | 证据，见下表。*豁免元素除外 |
| `waived` | bool | 否 | `true` 表示显式豁免门禁；必须同时给 `waiver_reason`。见 gate-rules.md 豁免政策 |
| `waiver_reason` | string | 豁免时必填 | 豁免理由，会原样出现在 gate_report.json 与最终记录中 |

## source 对象

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | string | 是 | 抽取源文本文件名，**相对于 sources 目录**（如 `paper1_page1-6.txt`、`table1_snapshot.txt`）。禁止 `../` 越出目录 |
| `locator` | string | 建议 | 人类可读定位：`论文.pdf 第3页 Methods 第2段`、`fig03 图注`、`table1.csv 第4行` 等。渲染为节点下方小字 |
| `quote` | string | 是 | **从 `file` 中逐字复制的连续片段**。是门禁唯一核验对象。选取规则见下 |

### quote 选取规则

1. 逐字复制，不增删改任何字符（标点、大小写、单位、上下标写法都保持原样）。
2. 长度适中：能独立支撑该元素 label 的最短片段，通常一句或一个分句（10–120 字）。过长会折损近失提示精度，过短（<5 字）证明力不足。
3. 跨行没关系——门禁做空白归一化；但跨页/跨段拼接的"合成句"禁止。
4. 一条 quote 可支撑多个元素；一个元素只有一条 quote，支撑不了就拆成多个元素或收窄 label。
5. 数字、参数、专有名词必须与 quote 完全一致；label 中不得出现 quote 之外的新数值。

## kind 使用指南与渲染外形

| kind | 典型用途 | 渲染外形 |
|---|---|---|
| `apparatus-unit` | 反应器、柱、泵、检测器等装置单元 | 圆角矩形（蓝） |
| `step` | 操作步骤、工序 | 矩形+序号徽章（绿，徽章按 step 出现顺序自动编号） |
| `stage` | 技术路线阶段、路线图分期 | chevron 箭头带（橙） |
| `data-item` | 原料、产物、数据表、指标 | 平行四边形（紫） |
| `flow` | 需要显式成节点的流/中间物 | 六边形（红） |
| `note` | 图注、约定说明（通常是豁免对象） | 虚线框（灰） |

## 最小示例（节选自 examples/minimal/ledger.json）

```json
{
  "id": "app-1",
  "kind": "apparatus-unit",
  "label": "恒温摇床酶解（37 °C, 180 rpm, 4 h）",
  "order": 3,
  "connects_to": ["step-2"],
  "source": {
    "file": "methods_excerpt.txt",
    "locator": "methods_excerpt.txt 第5行",
    "quote": "三角瓶置于恒温摇床，在 37 °C、180 rpm 条件下酶解 4 h。"
  }
}
```

## 编辑任务（EDIT）的附加约定

- 以既有 ledger 为起点时，原元素的 `id` 保持不变，便于 change_records 对照。
- 修改元素 = 改字段后**重跑门禁**；change_records 记 `before/after`。
- 既有 SVG 但无 ledger：为图中每个可辨识元素补建台账条目（quote 仍须命中源文本），
  无法补出证据的既有内容在 `uncertainties` 中声明，并在 change_records 标 `kept` + 说明。
