# 冲突模型与查询类型（d-identity-resolution-kg）

## 1. 冲突登记（conflict_registry.json）

建图时，脚本把 claims 按 `(规范实体 ID, 归一化 metric 键)` 分组：

- 组内 ≥2 个声明且数值集合大小 ≥2 → 登记一条冲突：
  - `conflict_id` K0001…；`claims[]` 保留**全部**竞争声明（值、单位、条件、
    来源段落、逐字 quote）；
  - `differing_conditions` = 各声明条件集合的对称差异（交并差），
    `shared_conditions` = 共有条件；
  - `resolution = "preserved"`：永不消解、永不平均、永不取最新；
  - 图上添加一条 `conflicts-with` 边（两端为声明节点），qualifiers 里带
    conflict_id 与差异条件。
- 数值相同、条件不同的声明**不**算冲突，但也绝不合并——它们各自是独立节点。

典型例（合成示例）：PCE 21.1%（1-sun 初始扫描，S1）vs PCE 18.7%
（500 h 湿热老化后，S2）→ 两个 C 节点 + 一条 conflicts-with 边，
差异条件列出 "1-sun AM1.5G illumination / initial scan" 与
"after 500 h damp-heat aging ..."。

## 2. 查询类型（query.py，自动执行 case.json 的 query_specs）

| type | params | 结果 |
|---|---|---|
| `neighborhood` | `entity`（表面形式）, `hops`（默认 1） | 从规范实体出发的双向 BFS 子图 + 证据 + 未确定关系 |
| `edges_by_relation` | `relation` | 该关系全部边及端点子图 + 证据 |
| `conflict_check` | `entity`, `metric`（可空） | 命中的冲突档案 + 冲突边 ID + 证据 |

每个查询结果都含：

- `status`: answered / empty / unsupported（空结果诚实标注并说明）；
- `subgraph` 或 `conflicts`；
- `evidence`: 逐字 quote + (source_id, paragraph_id)；
- `undetermined_relations`: 封闭关系词表中在该子图内**没有**任何边的关系——
  显式列出"查了但没有"，而不是静默缺席。

case.json 未给 query_specs 时，query.py 退化为 3 个兜底查询
（uses 边全量、全部冲突、一个可能为空的 neighborhood），保证 ≥3 个真实执行
的查询这一硬要求仍被满足；空结果同样计入执行。

## 3. 与证据规则的关系

- 图节点（实体）携带 mentions[]（每个 mention 都是逐字 quote + 地址）；
  声明节点携带 quote + 地址；边携带 quote + 地址。
- `conflicts-with` 边由脚本生成，quote 为 null（其证据在两端的声明节点上）；
  verify.py 跳过 null quote。
- verify.py 另检查所有产物中不存在 page/page_number/pages 字段
  （本数据包没有 PDF 页码，禁止编造）。
