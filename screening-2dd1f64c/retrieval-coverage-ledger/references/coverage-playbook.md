# 覆盖台账操作手册（coverage playbook）

本手册是 `scripts/coverage_engine.py` 的规则说明，供 Agent 在建账、判定、入账、校验四步中遵循。核心立场：**台账先于结论**——在给出任何筛选标签之前，先说清楚每条记录从哪来、每条查询产出了什么、以及这个快照遗漏了什么。

## 1. 来源归因优先级

对每条记录确定"哪条实际查询命中了它"，严格按以下优先级：

1. **显式来源字段**（最优先）：记录自带 `source_query` / `surfaced_by` / `retrieved_by` / `found_by` / `via_query` / `query_string` / `source` / `query` 字段时，取其**逐字值**记入 `source_value`，并记录字段名指针 `source_field`。若该值与某条声明的查询精确（忽略大小写）匹配，归因到该查询；不匹配时仍按原值记录并标注 `declared_query_match:false`——宁可暴露不一致，不可改写输入。
2. **词面重叠推断**：无显式字段时，计算记录 title+abstract 的内容词元（小写字母数字、长度≥3、去停用词）与每条查询词元的交集，归因到重叠最多的查询，**仅当重叠 ≥1 个内容词元**。条目必须带 `inferred:true` 与 `matched_tokens`（审计线索）。
3. **未归因登记**：两者皆无 → 进入 `unattributed_register`，注明原因。这是诚实暴露，不是丢失；它同时是该快照的一条遗漏证据（记录如何进入池中没有来源可考）。

## 2. 推断归因的诚实规则

- inferred 归因是启发式，不是事实：必须保留 `matched_tokens`，并在 `uncertainty` 中声明条数，提醒人工复核。
- 禁止"强行归因"：零重叠的记录不得挂到任何查询名下；per-query yield 只统计真正有归因的记录。
- 逐查询产出表（per-query yield）是审计对象而非宣传数字：某查询产出为 0 必须原样呈现，它本身就是检索遗漏的证据。

## 3. 重复/版本登记：合并 vs 复核队列的阈值

保守去重的理由：错误合并会销毁证据且不可逆，而漏合并只是多一条待复核项，代价不对称。

- **自动合并**（仅两种精确依据）：(a) DOI 精确一致；(b) 规范化标题精确一致（小写后剥去全部标点与空白）。合并组用并查集连通，组内选 canonical 的规则：正式发表优先于预印本（venue 含 preprint/arxiv/biorxiv/medrxiv 等判为预印本），否则年份较新者，否则输入顺序首条；其余成员记入 `merged_from`。
- **夹具声明**：带 `fixture_note` 的记录生成 `fixture_declared` 条目，**逐字引用** fixture 文本，标注 `provenance_only:true`。夹具标签只是输入自带的 provenance，永远不是 ground truth——它不能单独触发合并，只与精确匹配合并组关联（`linked_merged_group_canonical`）。
- **疑似对（不合并）**：标题词元 Jaccard ≥ 0.6 但不满足任何精确依据的对，进入 `suspected_duplicate_review_queue`，仅供人工复核，绝不自动合并。
- 合并是**登记**而非删除：重复记录在 screened_records 中仍各占一个分桶（会计恒等式不受影响），由判定步骤决定保留哪一版。

## 4. 遗漏说明模板

`omission_statement` 必须包含五要素：

1. `finite_snapshot_disclaimer`：候选池是随案例提供的 N 条有限快照；未查询任何实时数据库；快照之外的召回不可声称，快照遗漏了哪些相关记录在构造上不可知。
2. `per_query_yield`：逐查询产出原样转录（含 0 产出的查询）。
3. `unattributed_records`：未归因记录 id 列表。
4. `missing_metadata`：逐记录的 title/abstract/year/authors/doi/venue 缺口。
5. `suspected_duplicate_review_queue`：待人工复核的疑似重复对。

## 5. 会计恒等式与修复规则

恒等式：**|输入记录| = |keep| + |pending| + |exclude|**，且每个输入 record_id 在全部分桶中**恰好出现一次**，无重复、无丢失、无未知 id。account 步骤对决策文件做确定性修复，全部记入 `change_records`：

| 违规 | 修复 |
| --- | --- |
| 决策引用未知 record_id | 拒入 `rejected_register`（含原因），真实记录分桶不受影响 |
| 决策条目非对象 | 同上拒入 |
| 同一 record_id 多条决策 | 保留首次出现，其余丢弃并留痕 |
| 输入记录无决策 | 补 `pending`，rationale 为 "not judged"，逐条留痕 |
| bucket 非法值 | 降为 `pending` 并留痕 |
| quote 非标题/摘要逐字子串 | 置 null 并留痕（宁可空缺，不可疑似编造） |

修复永远朝向"诚实且恒等"的方向：不删除输入记录、不发明判定、不把非法内容洗成合法内容。

## 6. 为什么坚持保守去重与夹具纪律

评测案例中的重复导出/冲突意见夹具是**标注好的输入固定装置**（fixture），其标签只说明"输入这样声称"，不说明事实如此。把夹具标签当作答案会造成两级错误：合并了不该合并的（销毁证据），或对快照的重复结构做出未经独立依据支撑的断言。因此本 Skill 只允许 DOI/规范化标题精确匹配触发合并，fixture 文本逐字存档为 provenance，疑似对一律上交人工复核——可追溯性与遗漏说明由此成为一等交付物。
