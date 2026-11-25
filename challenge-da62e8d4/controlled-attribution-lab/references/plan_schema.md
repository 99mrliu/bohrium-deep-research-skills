# 预注册计划与结果契约

计划是 UTF-8 JSON，示例见 `examples/synthetic/plan.json`。这里必须区分两个不同对象：

- **真实输入 `case.json` 的 `output_contract`**：最终必须逐项回答的顶层字段；它不是 artifact 路径映射。
- **plan 的 `artifact_contract`**：已知 artifact 名称到输出目录内安全相对路径的映射；它不提供问题答案。

## 顶层字段

- `schema_version`：当前必须为 1。
- `case_file`：真实 case JSON 路径，相对 plan 所在目录；正式运行必填。执行器实际读取它，以其中的 `case_id` 和 `output_contract` 为准。
- `case_id`：必须与真实 `case.json.case_id` 完全一致；不能用 plan 自创 ID 覆盖正式 case。
- `registration`：`registered_at`（说明性时间字符串）与 `plan_sha256`（64 个小写十六进制）。
- `question`：要解释的复现差异。
- `metric`：`key`（候选 stdout 最后一行 JSON 中的有限数值字段）和 `noise_epsilon`（事前声明的非负数）。
- `hypotheses`：每项含 `hypothesis_id`、`statement`、`direction`（`increase/decrease/unresolved`）、`predicted_signatures`（非空数组）、`falsification`。
- `runs`：每个实际 subprocess 的定义。
- `variants`：每项含 `variant_id`、`hypothesis_id`、`factor`、`changed_paths`、`baseline_run_ids`、`run_ids`。
- `artifact_contract`：非空对象；键是 artifact 名称，值是输出目录内安全相对路径。核心名称 `runs`、`intervention_report_json`、`intervention_report_md`、`result` 默认映射到 `runs/index.json`、`intervention_report.json`、`intervention_report.md`、`result.json`。
- `contract_values`：可选对象，为 case 的回答字段提供实质值或结构化 unavailable；见下文。该对象参与 plan 哈希。
- `sources`：来源对象数组，至少含 `path`、`role`；可含 `sha256`、`locator`、`reported_by`。
- `provenance_notes`：组织方合成、原代码/全量 PMLB/原始仓库情况、自行设定参数等字符串数组。

### 向后兼容的 artifact 映射

旧版把 **plan** 的 `output_contract` 当 artifact 路径映射。执行器仍接受这一旧别名，但不能同时提供 `artifact_contract` 与旧别名。新计划必须改用 `artifact_contract`。这项兼容不改变正式输入规则：`case_id` 与回答字段永远从 `case_file` 指向的真实 case 的 `output_contract` 读取，旧 plan 路径映射不会展开成正式答案。

## case.output_contract 支持的形状

以下示例都声明 `reproduction_summary` 与 `status` 两个必需顶层字段；标准 result 字段允许出现在合同中，不能被 `contract_values` 覆盖。

1. 字符串列表，或带 `name/key/field/id` 的项：

   ```json
   ["reproduction_summary", {"name": "status"}]
   ```

2. 直接 mapping；默认所有键必需，`required: false` 可排除可选项：

   ```json
   {"reproduction_summary": {"type": "object"}, "status": {"type": "string"}}
   ```

3. `fields` 或 `required_fields` 包装，也接受 mapping：

   ```json
   {"fields": [{"name": "reproduction_summary"}], "required_fields": ["status"]}
   ```

4. JSON Schema object。存在 `required` 时使用它，且保留 required 中未列入 properties 的字段；没有 `required` 时，为避免漏交，全部 properties 均视为必需：

   ```json
   {
     "type": "object",
     "properties": {
       "reproduction_summary": {"type": "object"},
       "status": {"type": "string"}
     },
     "required": ["reproduction_summary", "status"]
   }
   ```

合同必须至少声明一个必需字段，重复字段和空字段名会预检拒绝。

## 回答字段：实质值与 unavailable

`case.output_contract` 的每个必需字段都必须成为 `result.json` 的顶层键。不得增加一个嵌套的 `output_contract` 来代替平铺，也不得把未知字段仅写成某个 artifact 路径。常见动态字段由执行器根据真实运行生成：

- `reproduction_summary`：真实运行数、容差对照与候选摘要；
- `candidate_comparison`：真实候选/运行对照与失败列表；
- `attribution_summary`、`intervention_summary`、`scientific_conclusions`、`difference_attribution`、`noise_floor_analysis`：真实 conclusion/effect/noise 记录。

其他案件字段通过 plan 的 `contract_values` 提供；同名字段存在时，案件特定的预注册值优先于动态默认值。它是哈希前的证据承诺，不能在看到结果后擅改。可写直接实质值，或带 evidence 的值：

```json
"contract_values": {
  "evidence_boundary": {
    "value": {
      "statement": "Evidence applies only within tested conditions.",
      "material_scope": "Organizer-synthetic materials."
    },
    "evidence": [
      {"path": "case.json", "locator": "provenance"},
      {"path": "intervention_report.json", "locator": "uncertainty"}
    ]
  }
}
```

非空数值、布尔、实质字符串、数组和对象均可；空容器、空串、`N/A/TODO/unknown/未知` 等占位不合法。只有标准的命名 artifact 字段（`runs`、`intervention_report_json/md`、`result`）可以把相对路径作为字段值；自定义回答字段只填路径会在预检被拒绝。

暂时无法回答时，字段仍须平铺，使用结构化 `unavailable`，至少有具体 `reason`，且有 `missing` 和/或 `next_steps`，可附 `evidence`：

```json
"paper_figure_comparison": {
  "unavailable": {
    "reason": "No paper PDF was provided, so figure values cannot be checked.",
    "missing": ["paper PDF and figure locators"],
    "next_steps": "Provide the paper PDF, then preregister figure comparisons.",
    "evidence": [{"path": "case.json", "locator": "provenance"}]
  }
}
```

未由动态证据或 `contract_values` 填写的字段也会得到结构化 `unavailable`，而不是伪造文本。含 unavailable 的交付不是证据完整交付；正常执行只能为 `partial`。预检拒绝时为 `unable`。

标准元数据字段 `case_id/status/execution_status/sources/uncertainty/change_records/artifacts/plan_sha256/...` 由执行器统一提供，允许但不需在 case 合同中重复声明；若声明，会照常出现在结果中且不可被 `contract_values` 覆盖。`artifacts` 是完整 artifact 路径账本，不是回答字段的替代品。

## run 字段

```json
{
  "run_id": "a_baseline_1",
  "candidate": "A",
  "role": "baseline",
  "argv": ["python3", "candidate_a.py", "--steps", "4"],
  "cwd": ".",
  "env": {"PYTHONHASHSEED": "0"},
  "timeout_seconds": 10,
  "inputs": ["material.txt"],
  "outputs": []
}
```

`run_id` 只允许 ASCII 字母、数字、点、下划线、连字符。`cwd` 相对 plan 所在目录；`inputs` 和 `outputs` 相对该 run 的 cwd，必须显式给出（无声明输出时使用空数组）。`argv` 非空且参数都是字符串，执行器不使用 shell。环境变量完整捕获：执行器只使用 allowlist 的 `PATH`、固定 locale、`PYTHONDONTWRITEBYTECODE=1` 和计划 `env`，不继承或导出其他当前环境秘密。不要在计划中放凭据或秘密。

`inputs` 必须存在。声明 `outputs` 在运行后逐项检查存在性并记录；stdout/stderr 仍由执行器无条件保存。候选最后一个非空 stdout 行必须是 JSON 对象，且包含 `metric.key` 指定的有限数值。前面可以有日志行。

每个 variant 的 baseline 至少两次，所有 baseline/variant run 的 candidate 相同，role 对应正确，run id 不重复。一个 baseline 池可服务同候选的多个变体。

## 单因素规则

合法 factor 仅 `implementation`、`parameter`、`data`、`environment`、`seed`。`changed_paths` 长度和去重后长度都必须恰好为 1，且路径以 `<factor>.` 开头。例如参数步长为 `parameter.steps`，实现选择为 `implementation.integrator`；一次改这两个字段将被拒绝。

这一检查保证**计划声明**满足单因素约束；执行器不能从任意程序反演内部真实改变量。调查者仍须审查 argv、输入、环境和代码 diff，证明除登记路径外的条件被固定。

## SHA256 封存与核验

深复制整个 plan，将 `registration.plan_sha256` 删除，然后计算：

```text
SHA256(json.dumps(plan_without_hash, sort_keys=True,
                  ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
```

其他 registration 字段以及 `case_file`、`artifact_contract`、`contract_values`、hypotheses、runs、variants、容差、目标均参与哈希。把摘要填回 `registration.plan_sha256` 即为封存。执行器的 `--seal-plan` 只在**任何实验运行之前**使用；普通执行绝不自动改计划。任何后续 plan 改动都会导致拒绝。真实 case 的字节 SHA256 另记录在 result.sources 中。

```bash
python3 scripts/controlled_attribution.py --seal-plan plan.json
python3 scripts/controlled_attribution.py --plan plan.json --output-dir output
```

## 结果与状态契约

`result.json` 始终列出 `case_id/status/execution_status/sources/uncertainty/change_records`、所有 case 回答字段、artifact 账本、哈希与执行统计。状态轴不可混用：

| 情形 | `result.status` | `result.execution_status` | 退出码 |
| --- | --- | --- | --- |
| 全部计划运行成功，声明 artifact 存在，全部回答字段有实质证据 | `success` | `complete` | 0 |
| 任一运行失败、指标/输出缺失、自定义 artifact 缺失或回答 unavailable | `partial` | `partial` | 1 |
| case/plan/schema/hash/factor/confounded 预检拒绝，0 个候选命令执行 | `unable` | `rejected` | 2 |

顶层 `status` 只能为 `success/partial/unable/refused`，绝不使用 `complete/rejected`；执行细节留在 `execution_status`。科学假设结论继续只用 `supported/falsified/inconclusive`。即使 `success/complete`，也只表示本次计划及证据交付完整，不等于论文完全复现或唯一根因成立。

自定义 artifact 应由任务命令实际生成；若不存在，写入 `missing_artifact_contract_artifacts`，不生成占位文件，也不把路径冒充回答。缺失字段写入 `missing_contract_answer_fields`。`evidence_delivery_complete` 仅在两类缺失均为空时为 true。
