---
name: contract-auditor
description: 面向文献抽取结果下游交付的清洗、异常分级、覆盖对账、独立终检与审计技能；适用于 JSON/CSV 抽取记录需要生成可统计表、变更证据、review queue、manifest 与 result.json 时。
---

# Contract Auditor：文献数据清洗与交付审计

## 目标与适用边界

本 Skill 的重心是**下游交付契约与可复核审计**，不是重新实现论文 PDF 摄取，也不要求先设计一个完整上游 schema。它接受案例中已经给出的嵌套 JSON 记录和/或声明的 CSV 抽取文件，以确定规则完成基础字段、数值、单位和身份清洗，并把重点放在：

1. 每个案例的 `output_contract` 字段完整回传；无法确定的新增键保持 `null` 且列入 `unresolved_fields`。
2. 每个输入行都有且仅有一个覆盖处置：`kept`、`flagged`、`deduplicated`、`rejected`。
3. 坏数字、未知单位、未映射列、缺值、ID 冲突进入 `anomalies.csv` 与 `review_queue.csv`；缺值保持空，不补造。
4. 每个被改动的单元格沿 `changes.jsonl` 的 `change_id + rule_id + input_row_id + source_pointer` 回到原始输入。
5. 所有产物原子写入，`checksums.sha256` 与 `manifest.json` 绑定载荷文件；独立 `verify` 阶段重新读取输入和产物，不信任运行阶段内存。

不适用：材料冲突的科学裁决、无证据补值、把不同实验/条件合并成一条、将字面单位换算当作科学同义判断。遇到这些情况时保持分离并开 review 项。

## 快速调用

默认路径符合平台运行时约定，四个路径都可覆盖：

```bash
python3 scripts/contract_auditor.py run \
  --case /input/case.json \
  --task /input/task.md \
  --work /app/work \
  --out /app/output
```

独立验证已有产物（不重新清洗、不读取运行阶段状态）：

```bash
python3 scripts/contract_auditor.py verify \
  --case /input/case.json \
  --task /input/task.md \
  --out /app/output
```

也可用 `--verify` 代替 `verify` 子命令。行预算：

```bash
python3 scripts/contract_auditor.py run --max-rows 10000
```

`--max-rows 0` 表示不限。默认 50000。超预算行不会被静默丢弃，而是记为 `rejected`、`BUDGET_EXCLUDED` 并进入 review；这是明确的部分结果，不是完整清洗。

## 推荐 Agent 工作流

1. **先保存部分结果**：脚本在读取完整输入后立即原子写出 schema-aware `result.json`。即使后续失败，也能看到状态、契约键和当前不确定性。
2. **运行清洗**：调用 `run`，然后先读 `result.json.status`、覆盖率与 `audit.md`。
3. **检查异常，不手工合并**：
   - `cleaned.csv`/`cleaned.json` 是可统计主表；`flagged` 行保留但不得把问题值当作已确认事实。
   - `anomalies.csv` 是机器异常账本。
   - `review_queue.csv` 是人工接管清单。
   - `changes.jsonl` 是逐单元格变更证据。
4. **独立终检**：必须调用 `verify`。只有 `exit_code=0` 且 `validation.json.status` 为 `pass` 或 `pass_with_findings` 时才说明交付结构、追踪和校验和可复核；这不等于所有科学异常已经解决。
5. **最终交付**：以 `/app/output/result.json` 为主 JSON，同时保留全部工件。回答用户时明确 `success`、`partial` 或 `input_error`，列出 unresolved fields、open review items 和限制。

## 输入识别

脚本按确定性顺序识别：

- 根 JSON 数组；或对象中 `records`、`rows`、`extractions`、`extraction_records`、`data_records`、`entries`、`items`、`observations` 等容器，允许嵌套。
- case 中以 `path/file/filename/filepath + format: csv` 或 `.csv` 后缀声明的 CSV，相对路径从 case 所在目录解析。
- 嵌套 dict 会展平成点路径；嵌套 list 以稳定 JSON 字符串保留。
- 可选 `field_mapping`、`target_units` 用来声明审阅过的映射和目标单位。没有映射的列不会被猜语义，而会保留为 `unmapped__...` 并报错级异常。

## 输出与状态

固定产物：

| 文件 | 作用 |
|---|---|
| `cleaned.csv` | 统计用扁平表；数值列为有限 JSON 数或空值 |
| `cleaned.json` | 与 CSV 等价的 JSON 数组，禁止 NaN/Infinity |
| `anomalies.csv` | blocking/error/warning/info 异常账本 |
| `review_queue.csv` | 需人工接管的问题，含定位、原值和建议动作 |
| `changes.jsonl` | 逐单元格变更与换算公式；一行一个 JSON |
| `validation.json` | 独立终检报告 |
| `checksums.sha256` | 载荷文件 SHA-256 |
| `manifest.json` | 载荷大小、哈希、清单范围和 artifact 名 |
| `audit.md` | 覆盖率、严重度、异常和完整性摘要 |
| `result.json` | 最终结构化结果，含合同字段、来源、不确定性、覆盖和工件引用 |

状态定义：

- `success`：无 error/warning/blocking，且无未适配契约键。
- `partial`：表已产出，但存在需复核异常、预算排除或未适配契约键；可继续下游使用 flagged 行时必须带条件。
- `input_error`：case/CSV 无法解析、没有可用记录或发生其他 blocking 输入失败；空表与异常文件仍会写出，便于接管。

## 严重度与失败矩阵

| 级别 | 代表代码 | 对表的影响 | 对状态/退出的影响 |
|---|---|---|---|
| blocking | `INPUT_CASE_INVALID`、`NONFINITE_OUTPUT`、`COVERAGE_MISMATCH`、`ARTIFACT_CHECKSUM_DRIFT` | 输入 blocking 阻止生成有效统计值；产物 blocking 表示交付不可信 | run 通常 `input_error` 并返回 2；verify 返回 3 |
| error | `MALFORMED_NUMBER`、`UNKNOWN_UNIT`、`UNMAPPED_COLUMN`、`DUPLICATE_ID_CONFLICT` | 单元格置空或行保留并 flagged；绝不猜值/合并 | `partial`，需 review；独立验证结构错误返回 0 但报告 findings |
| warning | `MISSING_VALUE`、`MISSING_UNIT`、`INTERVAL_VALUE`、`POTENTIAL_DUPLICATE_EXPERIMENT` | 保留空缺/区间端点，开人工项 | `partial` |
| info | `EXACT_DUPLICATE_REMOVED`、规范化说明 | 可解释的自动动作 | 不单独导致 partial |

`verify` 的非零退出只由 blocking 产物失败触发，包括合同字段缺失、行数/覆盖不一致、NaN/Infinity、未报告的未映射列追踪破坏、raw conversion trace 破坏、artifact hash drift、manifest/checksum 无效。源数据中已如实报告的 error/warning 不会被伪装成 `success`，也不妨碍 partial 结果可验证。

## 去重与身份规则

- 自动排除仅发生在：显式 `record_id` 相同，且排除指针、行号、变更 ID 后的完整科学/上下文明文身份一致（D001）。
- 同 ID 但值或上下文不同：两行都保留并 flagged，报 `DUPLICATE_ID_CONFLICT`，不选择、不平均、不合并。
- 值与上下文相同但没有同一显式 ID：保留并开 `POTENTIAL_DUPLICATE_EXPERIMENT`，因为可能是重复实验而非重复抽取。
- 来源、页码、表格、条件、实验上下文和未映射列都参与身份键，避免不同条件或来源上下文错并。

## 预算降级

- 平台预算有限时优先调用脚本，不要手工逐行复制。
- `run` 会立即保存 partial result；随后按行处理。若接近预算上限，减小 `--max-rows`，交付带 `BUDGET_EXCLUDED` 的可验证 partial，而不是超时后空手。
- 每个阶段都是原子替换；中断后旧产物不会被半个文件覆盖。
- 验证阶段无模型请求，适合作为最后必须执行的一步。

## 维护入口

- 字段同义词与单位 registry 在 `scripts/contract_auditor.py` 中有明确常量；新增映射必须先审查歧义。
- 交付字段和文件语义见 `references/delivery-schema.md`。
- 独立终检清单、故障代码与预期退出码见 `references/verification-checklist.md`。
- `examples/synthetic-input` 是**合成标记示例**，展示坏数字、未知单位、重复抽取、缺值、冲突 ID、未映射列和额外契约键；`examples/synthetic-output` 是实际运行产物，不是正式案例答案。

## 限制

- CSV/JSON 摄取是面向抽取表的确定性实现，不解析 PDF 版面。
- 单位表覆盖常用科研单位；未知单位进入 review，不根据字符串相似度猜换算。
- 数字区间被拆为 min/max，不编造中位数或均值。
- 复杂异构 case 若把数据放在非常规键中，应提供 `field_mapping` 或把行放入已知 records 容器。
- 脚本能证明交付完整性与规则追踪，不能替代科学冲突裁决或人工领域判断。
