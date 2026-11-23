# graph_schema — 证据图谱模式定义

证据图谱存于 `graph.json`（UTF-8 JSON），顶层结构：

```json
{
  "version": 1,
  "case_id": "...",
  "task_type": "T1 | T2",
  "contract_fields": ["..."],
  "nodes": [{"id": "...", "type": "...", "attrs": {...}}],
  "edges": [{"type": "...", "src": "...", "dst": "...", "attrs": {...}}],
  "conflicts": [ConflictEdge]
}
```

## 1. 节点类型

| 类型 | ID 规则 | 关键 attrs | 语义 |
|---|---|---|---|
| Source | `doc{n}`，按 (basename, abspath) 排序编号 | `path`、`sha256`（文件字节级）、`status`（ok / degraded:*） | 一份源材料。PDF 无 pdftotext 时 status=degraded 且无锚点 |
| Anchor | `doc{n}.para{k}`（k 为块序号，含表格块） | `source`、`kind`（para/table）、`index`、`text`、`sha256`（块文本） | 源文的最小引用单元：空行切分的段落或表格 |
| Task | T1 用 `q{n}`，T2 用 `item{n}`，按 task.md 编号行顺序 | `label` | 一个问题（T1）或一道题卡（T2） |
| Claim | `c.<task>.<seq>.<hash8>` | `task`、`text`、`honest`、`honest_reason`、`kind`（claim/item）、T2 另有 `reference_answer`、`difficulty`、`license` | 一条论断 / 一道题卡。hash8 = 归一化文本 SHA1 前 8 位 |
| Evidence | `e.<claim-id>.<k>` | `claim`、`anchor`、`quote`、`verdict`、`reason` | 一条逐字引文证据 |
| RubricRule | `r.<task>.<k>` | `task`、`text` | T2 题卡的一条评分规则 |

**稳定 ID 规则**：内容哈希 + 序号。Source/Anchor/Task 的序号只由输入
文件排序与行文顺序决定；Claim/Evidence/RubricRule 的序号只由
answers 文件内顺序决定，ID 内嵌内容哈希。同一输入重跑必得同一 ID、
同一 graph.json（逐字节一致，可 sha256 校验）。

## 2. 边类型

| 边 | src → dst | attrs | 语义 |
|---|---|---|---|
| contains | Source → Anchor | — | 锚点属于该源 |
| answers | Claim → Task | — | 论断/题卡回答该任务 |
| supports | Evidence → Claim | `verdict`、`reason` | 证据支持论断（带核验结论） |
| derived_from | Evidence → Anchor | — | 证据引文派生自该锚点 |
| governed_by | Claim → RubricRule | — | 题卡受其评分规则约束（T2） |

## 3. verdict 语义（supports 边）

- **pass**：引文经归一化（NFKC、fi/fl 连字还原、断词连字符接合、
  空白折叠）后，是其声称锚点归一化文本的子串（verbatim_match）。
- **fail**：`anchor_not_found`（锚点 ID 不存在）、`verbatim_mismatch`
  （引文不在锚点内）、`empty_quote`（空引文）。
- **degraded**：`anchor_text_unavailable`（锚点文本不可用，如 PDF
  降级情形）。degraded 不算 pass，也不计入 fail 门禁，但须在
  uncertainty 中说明。

## 4. ConflictEdge（冲突边）

跨源冲突是显式结构而非文字备注，存于 `conflicts` 数组：

```json
{
  "id": "conf-<seq>",
  "kind": "numeric_mismatch | negation",
  "node_a": "doc1.para1",
  "node_b": "doc1.para4",
  "attr": "过电位",
  "unit": "mV",
  "values": {"doc1.para1": "287", "doc1.para4": "312"},
  "detail": "numeric_mismatch：doc1.para1=287mV vs doc1.para4=312mV"
}
```

分类与检测启发式（仅作用于 verdict=pass 的证据引文）：

- **numeric_mismatch**：两条引文来自不同锚点、属性名相同或公共
  后缀 ≥2 字符、单位一致、数值不同。
- **negation**：同上但数值相同，且一方数值前 12 字符窗口内含否定词
  （不/未/无/并非/不是/没有/not/never/no），极性相反。

属性名抽取：取数值前 ≤32 字符窗口，清洗表格竖线与标点后取尾部
≤15 字符短串（剥离"为/是/约/of/is"等系动词），去空白并小写拉丁
字母。该启发式**不做语义等价判断**（同义词、换算、上下位关系需
agent 标注），可能漏报或误报，属于已知限制。

## 5. 孤儿与诚实标记

- **孤儿论断**：无任何 supports 边且 `honest != true` 的 Claim。
  必须修复（补证据重跑 graph_link）或改诚实标记
  （`honest=true` + `honest_reason`），否则 graph_export 交付门禁
  拦截（退出码 2）。
- **诚实标记**：agent 主动声明"无法判断/源文无据"的论断，不要求
  证据，不参与逐题评分，但会在 q_honest_flags 与 uncertainty 中
  显式列出。
