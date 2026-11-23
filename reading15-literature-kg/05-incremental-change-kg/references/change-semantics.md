# 变更语义（change semantics）

变更集（changeset）是 Agent 阅读 secondary 论文后编写的 JSON，由确定性校验器
（`kg_verify.py`）先校验、再由 `kg_apply.py apply` 应用。五种操作，全部**只追加、
不覆盖、不删除**：

## ADD（新增）

- `{"op":"ADD","kind":"node","node":{...}}`：新增实体节点。同锚点已存在则幂等跳过。
- `{"op":"ADD","kind":"edge","edge":{...}}`：新增关系边。端点可用
  `{"label":...}`（经别名解析）、`{"id":...}`（稳定 ID）或 `{"ref":"op:N"}`
  （引用本变更集第 N 个操作新建的节点）。
- 用途：secondary 的新方法/新样品/新数值边/新结论。

## MERGE（真别名合并）

```json
{"op":"MERGE","candidate":{节点候选,含 secondary 证据},"into":{"label或id":...},
 "justification":"合并依据（>=20 字符，须引用证据）"}
```

- 要求：候选节点证据逐字命中；justification 非空且具体；
  **通用术语防护**：标签命中通用词表（见下）时默认拒绝，除非设 `allow_generic:true`
  且 justification 引用显式证据（如原文同时出现全称与缩写："LFP/C composite
  (LiFePO4/C, hereafter LFP/C)"）。
- 效果：幸存者保留原 ID，别名+证据追加；不删除任何记录。

## KEEP_DISTINCT（保持区分）

```json
{"op":"KEEP_DISTINCT","candidate":{节点候选},"distinct_from":{既有节点},
 "reason":"区分理由（>=20 字符）"}
```

- 用途：同名/通用术语但**无同一物理对象证据**时显式保持区分。
  典型：两篇都用 "commercial carbon black"，一篇作碳源、一篇作导电添加剂，
  无批号/供应商信息——通用术语相同不代表同一物理样品。
- 效果：新节点获得确定性 `_2` 后缀 ID；两节点互记 `related_but_distinct`；
  旧 ID 不动。

## UPDATE_EVIDENCE（追加证据）

```json
{"op":"UPDATE_EVIDENCE","target":{节点或边},"add_evidence":[...]}
```

- 只追加证据（去重），不改写任何既有字段。用于为 baseline 记录补充另一段的
  支持短引，或为新合并节点补充次要证据。

## CONFLICT（冲突保留）

```json
{"op":"CONFLICT","candidate":{新边候选},"conflicts_with":{"id":"e_xxx"},
 "reason":"冲突说明（>=20 字符）"}
```

- 用途：两篇结论/关系方向相反（如"溶胶凝胶优于水热" vs "水热优于溶胶凝胶"），
  或数值、条件不一致且无法调和。
- 效果：新边以 `status:"conflicted"` 加入，旧边也标记 `conflicted`，
  二者结成同一 `conflict_group`；**两条边都完整保留，均未覆盖**。
  图谱不替论文"裁决"，只并列呈现双方证据。

## 通用术语词表（防护用，可按主题扩充）

`sample / commercial sample / control / control group / reference /
reference sample / composite / the composite / material / the material /
standard method / commercial carbon black / carbon black / the electrode /
electrode / commercial / baseline / blank / substrate / catalyst / solution /
powder`

## 类型词表

- 节点类型：`material / method / task / metric / researcher / conclusion /
  sample / dataset / condition / device`。
- 关系名：snake_case 自由词表（建议：`synthesized_by / uses / applied_to /
  delivers_capacity / measured_by / outperforms / supports / contradicts /
  compares_with / improves / reports / authored_by`）。
- 数值与条件一律放边的 `attributes.value` / `attributes.condition`，
  **逐字照抄原文**（含范围与不等号），不得换算、平均或四舍五入。

## 证据字段（每个实质节点/边必备）

```json
{"source_id":"primary|secondary","paragraph_id":"p1.003","quote":"原文精确短引（<=280字符）"}
```

- `paragraph_id` 是组织方 JATS 段落 ID，**不是 PDF 页码**；本包无 PDF 页码，
  evidence 中出现 `page` 字段会被校验器直接拒绝。
- quote 经空白规范化后必须是该段落原文的精确子串；行内公式/上下标已线性化，
  按线性化文本照抄（可对照 secondary-publisher.xml）。
