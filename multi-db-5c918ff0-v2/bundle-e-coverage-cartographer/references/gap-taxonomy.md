# 缺口分类法（Gap Taxonomy）

coverage-cartographer 的缺口台账（gap_ledger.json）中每条目都必须是下列
类型之一。每条目含：`entry_id`、`type`、`severity`、`db`、`evidence`
（证据定位）、`impact`（影响陈述）。脚本内嵌模板与本文件一致。

严重级：`critical` > `warning` > `info`。台账非空 ⇒ `status="partial"`。

## 条目类型一览

| type | severity | 触发条件 | 影响陈述要点（用户不能得出什么结论） |
|---|---|---|---|
| `db_absent` | critical | 期望数据库（case.json `source_dbs` 或 task.md 提及）无任何材料 | 该库命中整体不可见，候选集对该库系统性缺失 |
| `material_missing` | critical | case.json 清单声明的材料文件不存在 | 对应内容缺失，相关来源无法审计 |
| `envelope_malformed` | critical | 材料无法解析为 JSON/JSONL | 内容整体缺失，相关来源覆盖结论不可用 |
| `hitcount_mismatch` | warning | 声明命中总数（total-results / hitCount）与实际返回条数不一致且无 cursor/翻页证据 | 未返回部分不可见，不能断言已覆盖全部命中 |
| `empty_response` | warning | 某库信封有效但 0 条记录 | 无法区分「无命中」与「检索式/接口问题」 |
| `field_systematic_gap` | warning | 某规范字段在该库全部记录中 0 次提供（且该库有记录） | 跨库合并时该字段对该库系统性缺失，不能据此字段比较/筛选该库记录 |
| `identifier_conflict` | warning | 同一归一化 DOI 跨库年份/归一化标题冲突 | 已列待仲裁、未静默合并；仲裁前不能确信规范元数据 |
| `import_state_gap` | warning | 增量导入状态声明的 id 在响应中缺失，或响应中的 id 未在导入状态声明（双向） | 导入集与检索集存在偏差，不能断言二者一致 |
| `referenced_not_retrieved` | warning | 引用图节点在任何来源中无匹配记录 | 引文追踪断点，被引/引用文献可能遗漏 |
| `mechanical_copy` | warning | 同一检索式逐字发送至 ≥2 个语法不同的库 | 字段检索能力未利用，召回可能系统性偏低 |
| `unclassified_material` | warning | 材料结构无法归类为已知信封 | 已跳过，其潜在贡献未计入 |
| `query_evidence_missing` | info | 某有记录的库在 case.json/task.md/信封中均无检索式证据 | 该库覆盖度无法归因，不能断言检索按预期执行 |
| `extra_source` | info | 材料来自期望集合之外的数据库 | 已纳入审计，是否采信需用户确认 |
| `single_source_only` | info | 规范文献（身份键归并后）仅出现于一个库 | 无第二来源交叉验证，可信度依赖单一来源 |

## 影响陈述模板（impact templates）

脚本按下列模板生成中文影响陈述，`{...}` 为实例化槽位：

- `db_absent`：期望数据库 {db} 没有任何可用材料：该库本应命中的文献整体不可见，
  候选集对该库系统性缺失，用户不能断言检索覆盖了 {db}。
- `hitcount_mismatch`：{db} 声明命中总数 {declared}，实际返回 {returned} 条，
  且无翻页/游标证据：未返回部分不可见，用户不能断言已覆盖全部命中。
- `field_systematic_gap`：字段 {field} 在 {db} 的 {count} 条记录中 0 次提供：
  跨库合并时该字段对 {db} 系统性缺失，用户不能据此字段比较或筛选该库记录。
- `identifier_conflict`：标识符 {identifier} 在不同来源间元数据冲突（{detail}）：
  已列出待仲裁、未静默合并；仲裁前用户不能确信其规范元数据。
- `import_state_gap`：增量导入状态与检索响应不一致（{direction}：{identifier}）：
  导入集与检索集存在偏差，用户不能断言二者一致。
- `referenced_not_retrieved`：引用图节点 {node} 未被任何来源检索到：
  引文追踪存在断点，被引/引用文献可能遗漏，用户不能断言引用网络已闭合。
- `single_source_only`：文献 {identity} 仅出现于 {db}：无第二来源交叉验证，
  其存在性与元数据可信度依赖单一来源。
- 其余类型模板见 `scripts/coverage_cartographer.py` 中 `ENTRY_SPECS`，与本表语义一致。

## 证据定位（evidence locator）约定

每条目的 `evidence` 字段必须指出可供复核的位置：材料文件名、信封内 JSON
指针式描述（如 `message.total-results=3 vs items=2`）、task.md 行号、
或引用图节点 id。空口无凭的条目不得入账。

## 诚实性红线

1. 任何异常必须入账，禁止静默吞没；
2. 冲突（identifier_conflict）列待仲裁，禁止脚本自作主张地「解决」；
3. 无证据不假设（如查询证据缺失记 `query_evidence_missing`，而非默认检索正确）；
4. 台账非空 ⇒ `status` 必须为 `partial`，不确定性陈述必须落实到具体条目。
