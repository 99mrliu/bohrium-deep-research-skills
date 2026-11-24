# Contract Playbook(契约手册)

本手册定义 `output_contract` 的解析形态、字段填充语义与 null 纪律。渲染引擎
`scripts/render_forge.py` 完全按本手册实现。

## 1. 契约的三种形态(发现顺序)

`case.json` 的 `output_contract` 字段可能出现三种形态,均保持其出现顺序
写入 `/app/work/contract_fields.json` 的 `contract_fields` 列表:

1. **dict 形**:`{"field_name": "规范说明", ...}`。`spec` 取字符串值;非字符串
   值序列化为 JSON 字符串。`spec_source = case.json:output_contract(dict)`。
2. **list 形**:`["field_a", "field_b", ...]`。`spec` 为空串。
   `spec_source = case.json:output_contract(list)`。
3. **string 形**(换行分隔):
   ```
   candidate_set
   ranking_basis
   ```
   每行去空白、去行首 `-`/`*` 后为字段名。
   `spec_source = case.json:output_contract(str)`。

**辅助挖掘**:task.md 中的反引号标识符(`` `candidate_set` ``)与含
"输出字段 / output field / deliverable / 交付字段 / 结果字段" 行中的标识符
被收集为 `task_mined_candidates`。仅当挖到的名字与既有契约字段完全同名时,
在该字段的 `spec_source` 追加 `+task.md`。**绝不依据挖掘结果新增契约字段。**

## 2. 填充语义(字段名 → 交付内容)

引擎按字段名(小写,子串匹配)选择填充器,全部内容来自 `ctx` 中的真实数据:

| 字段名特征 | 填充内容 |
|---|---|
| 含 `candidate` | 全部规范(canonical)记录:`merged` 字段值 + `field_provenance` + `sources_seen` + `dedup` + `conflicts` |
| 含 `rank` | 排序方法说明、词项表、逐记录 rank/score/matched_terms/citation_boost |
| 含 `evidence` | 每条记录的完整证据链(成员来源库/工件/定位/缺失字段/逐字段溯源) |
| 含 `coverage` | 覆盖矩阵对象(成员级计数、`merged` 计数、单一来源记录、系统性缺失) |
| 含 `status` 或 `note` | 状态说明(单一来源、系统性缺失、冲突数、上游消费)+ uncertainty |
| 含 `graph` 或 `reference` | 引用图摘要(节点/边数、边语义、规范 DOI 的入度) |
| 含 `import` | 导入状态对象原样透传(organizer 本地增量状态) |

**保留键冲突**:契约字段名等于 `case_id` / `status` / `sources` /
`uncertainty` / `change_records` / `artifacts` /
`unresolved_contract_fields` / `generated_by` 时,保留键优先,该契约字段记
unresolved(reason 注明碰撞),`status` 相应降为 `partial`。

**无语义填充器**:任何未命中上表的字段一律 `null` + unresolved,等待人工或
上游补齐——扩充填充器属于维护动作,不属于运行时推断。

## 3. Null 纪律(绝不编造)

1. 字段值只能来自:材料文件的解析结果、reference_graph/import_state 透传、
   排序与覆盖的机械计算。**不允许**常识补全(如猜测卷期页)、**不允许**生成
   材料中不存在的记录。
2. 每条规范记录的字段状态只有两种:`value`(带 source/artifact/locator)或
   `not_provided_by_any_source`(所有来源成员均无该字段)。
3. `null` 契约字段必须与 `unresolved_contract_fields` 一一对应;门控第 4 项
   检查该一致性。
4. 冲突处理只影响"取哪个来源的值",不创造新值;冲突变体全部列入
   `provenance_chain.md` 与 review appendix。

## 4. 门控检查清单(render_gate_report.md)

| # | 检查 | 失败后果 |
|---|---|---|
| 1 | 全部契约字段作为键存在于 result.json | FAIL → partial |
| 2 | 候选数从数据重算 = candidate_table.md 声明值(注释标记 `<!-- canonical_records:N -->`) | FAIL → partial |
| 3 | 覆盖矩阵逐行从数据重算 = 渲染行(`<!-- matrix:begin/end -->` 块) | FAIL → partial |
| 4 | null 契约字段 ↔ unresolved_contract_fields 一致 | FAIL → partial |
| 5 | 每个工件存在且 sha256 已记录 | FAIL → partial |

`gate_overall=PASS` 且无 unresolved 且有 ≥1 条规范记录 → `status=success`。
`result.json` 是清单载体,其自身哈希不写入 `artifacts`(避免自引用);
`render_gate_report.md` 定稿后重算其哈希覆写清单。
