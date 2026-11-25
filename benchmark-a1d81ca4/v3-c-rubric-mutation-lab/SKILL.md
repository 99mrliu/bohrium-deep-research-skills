---
name: v3-c-rubric-mutation-lab
description: "为 benchmark-a1d81ca4 revision2 固定 case 从真实段落或表格编写四个来源约束的 Deep Research 小题，并对确定性 0/1/2 评分器做探针与变异测试；当任务要求声明式谓词、下游候选答案评分、错误单位/实体/条件等 rubric mutation、原始输出可追溯打分时触发。不要用于单纯来源索引、blueprint QC、通用 run ledger、UI，或只是 non-empty machine_check/单条引文质检。"
---

# Rubric Mutation Lab

## 核心边界

本技能的中心产物是**四个可从本题实际材料作答的 item**，以及能区分完整、部分、错误答案的确定性 0/1/2 rubric。必须把每个分数追溯到候选原始输出、逐谓词通过/失败原因和 rubric 哈希。`machine_check` 非空、存在一条引文、JSON 可解析均不代表回答正确。

不要把工作漂移到来源索引、蓝图 QC、通用运行日志或 UI。不要臆造 DSH 分数、人类一致性、外部实验或任何人工评分。rule score 不是英文语义蕴含认证；触发人工复核的条件见 `references/predicate_schema.md`。

## DeepSeek 实际运行流程

1. **先检查真实输入。** 阅读 `/input/case.json`、`/input/task.md` 以及 `/input/materials/` 的实际段落和表格。记录原 `case_id`，只从显式 `output_contract` 解析要求的顶层结果字段；不得把原 case 的任意元数据字段误当作结果契约，也不得假设契约与 synthetic example 相同。
2. **立即写入诚实的 partial。** 在 `/app/output/result.json` 保留原 `case_id`，按 `output_contract` 把每个声明字段写到结果顶层，并添加独立的 `rubric_mutation_lab` 诊断对象。`status` 先为 `"partial"`；已知内容使用真实值或声明类型的空占位，未知必需字段为 `null` 且必须有失败 gate。不得等待最后一步才写文件，不得写入预先编好的正式答案或虚构完成状态。可直接用 `finalize.py` 的无报告模式生成该结构。
3. **所有中间文件放 `/app/work`。** 依次保存来源摘录、item bank、独立预期探针、探针报告、原始候选输出、评分报告与严格最终结果；不得污染 `/input`。
4. **只从本题材料 authoring。** 恰好四项，尽量覆盖不同段落/表格及不同推理负担。每项以 `status: "benchmark-DRAFT"` 标记，记录 `reference_answer`、材料原文 evidence、声明式 predicates、有序 score bands 与 default 0。引用只用于来源绑定，不能代替谓词执行。
5. **谓词必须可观测且原子。** 分开表达关键实体、数值+必需单位、条件、禁止断言及“材料未报告”。用 all/any/not 组合，不用任意 Python/eval。数值容差必须显式，即使为 0。
6. **独立标注探针，再执行。** 每项必须有 `REQUIRED_PROBE_CLASSES` 中全部类别；适用时加 `legitimate_unreported`。`expected_score` 和 `expected_predicates` 来自人工对材料/rubric 的独立判断，严禁运行评分器后反填。exact/paraphrase 不应只验证关键词非空；partial 与各类错误须说明理由。
7. **变异 rubric/probe，而非迎合现有输出。** 至少做一个能暴露真实缺陷的负例，如把错误单位加入 numeric units 后必须由 mutation gate 检出，或删除必需 probe 后必须失败。修复的是 rubric/schema/独立标注中经核实的错误，不得为了绿灯随意改预期。
8. **对真实候选原始输出评分。** `score_outputs.py` 必须拒绝未知、缺失、重复 item ID；空输出和超长输出默认拒绝，只有显式配置才放行。检查四条必需记录的 raw-output SHA-256、逐 check 原因、failure taxonomy 和 0..8 rollup。分母只含实际评分的四个 required item。
9. **最后严格 finalize。** 两次执行应字节一致。所有 gate 通过才可 `complete`；否则保留显式 `partial`，列出失败 gate 和 uncertainty，严禁伪造 success。最终须再次核对 `case_id` 和每一个 `output_contract` 字段都位于结果顶层、非 null 且类型兼容；原 case 的其他字段只作为 extras 保留。

## 动态输出契约

`finalize.py` 独立解析本 case 的 `output_contract`，支持以下写法：`list[str]`；`{"fields": ["field", ...]}`；`{"fields": [{"name": "field", "type": "object", ...}, ...]}`；直接的 `field -> type/metadata` map；`properties` map；以及 `required_fields` / `required_top_level_fields` 名称列表（也可与其他写法组合）。类型声明按 JSON 类型检查，包括 `string`、`array`、`object`、`boolean`、`integer`、`number`、`null`，也支持类型数组和 `nullable`。契约不必重复声明 `case_id` 或 `status`；`case_id` 始终来自输入并写到顶层，未声明的 `status` / `success` 也作为真实运行状态 extras 输出。

绑定覆盖 item bank / items、score report / records / rollup、mutation report、sources、uncertainty、change_records、summary / diagnostics 和 human agreement 等同义字段。人类一致性未测量时，使用明确的 `measured: false` 对象或说明文本；数值分数绝不以 0 冒充测量结果。未知的已声明字段、缺失报告及类型不兼容均不能 strict complete。未知必需字段输出 `null` 和显式失败 gate；无报告 early partial 对其余已知字段输出有类型的空数组/对象等，并写明失败 gate。成功要求所有契约字段均有非 null、类型兼容的真实绑定，同时恰好四项及全部 scoring、hash、rollup、trace、mutation gate 通过。

`rubric_mutation_lab` 仅保存嵌套的完整导出与 gate 诊断，不能替代顶层契约字段；最终断言应遍历实际 `output_contract`，而不是只检查这个 exporter。原 case 的 `revision`、任务说明等有用元数据可作为 extras 保留，但它们不构成契约，也不会被用来猜测未知结果字段。

## 命令入口

以下命令中的路径均为参数，不依赖固定本机路径；解释器只需 Python 3 标准库：

```bash
python3 scripts/score_engine.py --items /app/work/item_bank.json \
  --item-id ITEM_ID --candidate-file /app/work/one_raw_output.txt \
  --output /app/work/one_score.json
python3 scripts/mutation_check.py --items /app/work/item_bank.json \
  --output /app/work/mutation_report.json
python3 scripts/score_outputs.py --items /app/work/item_bank.json \
  --candidate-outputs /app/work/candidate_outputs.json \
  --output /app/work/score_report.json
python3 scripts/finalize.py --case /input/case.json --items /app/work/item_bank.json \
  --score-report /app/work/score_report.json \
  --mutation-report /app/work/mutation_report.json \
  --output /app/output/result.json --strict
```

输入/输出 schema、失败语义和限制见 `references/predicate_schema.md`；独立探针设计见 `references/probe_design.md`。`example/run_example.sh` 是完全合成的四题回归示例，默认输出到 `mktemp`，不得把其标签或答案复制到真实 case。
