# 跨文档实体身份裁决策略（Identity Policy）

本文档是 `scripts/identity_gate.py` 的规则说明，二者必须保持一致；修改规则时同步修改测试。

## 1. 术语

- **提及（mention）**：一篇论文中一次实体出现，带 `source_id`（独立论文标识）、
  `paragraph_id`（组织方 JATS 段落 ID，非 PDF 页码）、逐字短引、别名、属性。
- **候选键（candidate key）**：由 surface 与 aliases 经确定性规范化得到的键；
  只负责“把可能相同的跨篇提及放到一起”，**本身不构成合并依据**。
- **定义性属性（defining attributes）**：判断“是否同一对象/实例”的身份属性：
  `chemical_formula`、`composition`、`cas_number`、`identifier`、`architecture`、
  `principle`、`algorithm`、`dataset_version`、`version`、`model_version`、
  `sample_id`、`batch`、`instrument`、`conditions`。
- **测量属性（measured attributes）**：`numbers` 中的 `{name, value, unit}`，
  属于结果而非身份；不同论文的测量值绝不合成一个结论。

## 2. 裁决规则（按优先级）

- **R0 同篇排除**：`source_id` 相同的提及对不构成本门的跨篇候选。
  同一论文的多种文件格式、多处出现都不算跨篇证据。
- **R1 阻断项（任一成立 → KEEP_DISTINCT，记录 blocking_evidence）**：
  - `defining_conflict`：同名定义性属性规范化后不同
    ——不同样品、模型实例、数据集版本、实验条件即属此类；
  - `numeric_conflict`：同名测量属性、规范化单位一致、数值不同；
  - `unit_conflict`：同名测量属性但单位不可比（保守处理，不做不确定换算）。
  - 明确说明：**不同 DOI / 不同来源不是阻断项**；`source_id`、DOI 永远
    不参与定义性属性比较（有专门测试 N5 保证）。
- **R2 合并依据（无阻断项时 → MERGE，记录 merge_basis）**：至少一个定义性
  属性规范化一致（如化学式、原理、架构完全相同）。
- **R2b 通用术语封顶**：候选键属于 `generic_terms`（如 xrd、sintering 等
  通用方法/材料术语）时，除非强身份键（`cas_number` / `identifier` /
  `sample_id` / `instrument`）一致，否则至多 UNDECIDED——相同通用术语
  不代表两篇使用了同一物理样品、模型实例、数据集或实验条件。
- **R3 证据不足（无阻断、无合并依据 → UNDECIDED）**：仅规范化别名相同
  不得合并；UNDECIDED 在图谱中保持为两个节点，并在结果的不确定性中声明。

## 3. 稳定 ID

节点稳定 ID（`E-0001…`）只在全部裁决完成后，按簇内最小 `mention_id`
顺序分配；MERGE 簇合并为一个节点并保留 `merged_from` 与双方来源证据；
KEEP_DISTINCT / UNDECIDED 的提及各自成节点。辅助节点（测量指标等字面量）
按 `AUX-XXXX` 编号，作用域限于单一来源，永不参与跨篇合并。

## 4. 冲突保留

合并节点上来自不同论文的同名测量值若不同，`build_graph.py` 将其记入
`conflicts.json`（`measurement_conflict_kept_separate`），各来源数值与条件
分别保留，绝不取平均、绝不覆盖。

## 5. 证据要求

每个实质节点/边必须有：独立论文 `source_id` + JATS `paragraph_id` +
逐字短引（空白折叠后仍为原文子串）。本包**无 PDF 页码**：证据携带
`page`/`pages`/`pdf_page` 字段即判核验失败。伪造或错挂引文的元素被剔除并
记录在 `verification-report.json`。
