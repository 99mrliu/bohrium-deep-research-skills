# Spec、执行与平台契约

## 带哈希的信封

规格文件为 UTF-8 JSON，顶层严格为：

```json
{
  "spec_sha256": "64 lowercase hex characters",
  "spec": {}
}
```

`spec_sha256 = sha256(canonical_spec(spec))`，规范序列化是 `json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` 后编码 UTF-8。Decimal 在实现中序列化为十进制字符串。无哈希、额外信封键、格式错误或哈希不符均在任何候选和 Oracle 运行前拒绝，退出码 2。

推荐先生成不含信封的 body，再放入信封并计算 hash。必须避免“跑完后改 tolerance 而不重算 hash”。报告的 `spec_sha256` 与 `frozen_tolerances` 可审计。

## 正式 spec 的必要内容

- `spec_version: "1.0"`。
- `case_file`、`task_file`、`paper_materials`：实际路径；命令行 `--case` 可覆盖 case_file。
- `paper_target`：论文独立读取的目标或 null。
- `oracle.type/parameters/tolerances`，二次方程还要有 `scaling_factors`。
- 至少两个不同 `candidates`。`id` 仅允许字母、数字、点、下划线、连字符且不可重复。
- 每项 `argv` 显式列出可执行程序与全部参数，禁止 shell 字符串和固定文件名猜测；`cwd` 可解析且必须存在。
- `timeout_seconds > 0`。剩余全局预算更短时，实际 timeout 更短并单独记录。
- `output.mode` 为 `last_json_line` 或 `json_file`；后者必须给 `output.path`。
- 可选 `source_path` 和 `author_code` 用于来源审计；未知来源不能自动标作者代码。
- 可选 `contract_values` 只能填已有证据的输出值。
- 可选 `evaluation_mode: "synthetic"` 强制 partial。

模板可使用 `{spec_dir}`、`{work_dir}`、`{output_dir}`、`{json_out}`、`{a}`、`{b}`、`{c}`、`{scale}`。`{json_out}` 是运行器为该候选该试验分配的 `/app/work` 下路径，不是默认候选协议：只有 argv 显式传给支持它的候选才有意义。`{a/b/c}` 是缩放后系数。任一未知占位符在运行前拒绝。

## 目录、时间和失败

正式分配：

| 路径 | 权限与用途 |
|---|---|
| `/input` | 只读；case、task、PDF、候选及声明的输入，不写 spec/日志 |
| `/app/work` | 中间 spec、每候选试验目录、JSON 文件输出及临时证据 |
| `/app/output` | 最终 oracle_report.json、oracle_report.md、result.json |

本地验证必须显式指定允许的可写 work/output 目录，不能使用平台路径假装已部署。总预算最多 900 秒，每候选后立即写 partial 产物。候选非零退出、timeout、启动失败、stdout/stderr 有错误信息、JSON 缺行/解析错误、数值失败均不阻止其他候选。运行器保存 stdout/stderr 于 JSON/Markdown；解码错误用 replacement character 保留可见性，JSON 文件若非 UTF-8 则明确失败。

候选启动用 argv 数组与独立进程组，stdin 为 DEVNULL；timeout 时杀进程组。退出码 0 只说明进程结束。`run` 的退出语义：0=报告完成（可 partial/候选失败），2=非法 spec，1=运行器自身错误。

## `oracle_report.json`

关键分区：

- `spec_sha256`、`frozen_tolerances`：事前冻结证据。
- `paper_vs_oracle`：论文目标与独立数学结果，含 `matched/mismatched/not_provided`。
- `candidates[].trials[]`：实际 argv、cwd、stdout、stderr、退出码、时间、解析状态与 parsed output。
- `independent_expected` 和 `candidate_vs_oracle`：真值计算、误差、容差界限、残差或搜索轨迹。
- `candidate_vs_paper`：候选直接与论文目标在相同事前容差下比较，单独标 matched/mismatched/not_provided，不改变 Oracle expected。
- `scaling_metamorphic`：二次方程实际缩放因子与通过情况。
- `sources`、`uncertainties`、`oracle_limitations`：来源与能力边界。
- `completion_status`：执行流程为 `complete` 或 `partial`；`complete` 只表示本轮执行结束，不表示所有候选通过或任务证据齐全。`status` 与 `result.json` 的任务状态一致，且只使用合法结果枚举。

Markdown 是便于阅读的摘要，JSON 才是完整证据。数学 Oracle 通过不等于论文复现。

## `result.json` 平铺规则

假设 case 为：

```json
{"case_id":"c1","output_contract":{"reproduction_summary":"...","candidate_comparison":"..."}}
```

结果顶层至少有：

```text
case_id
reproduction_summary
candidate_comparison
status
sources
uncertainty
change_records
```

不能再嵌套成 `{"result":{"reproduction_summary":...}}` 或只保留 `output_contract`。支持以下输入并取字段名去重后的并集：直接字段 mapping；字符串或带 `name`/`key` 项的 list；`fields`、`required_fields` 的 list 或字段 mapping；JSON Schema object 的 `properties` 与 `required`。容器自身的 `fields`、`properties`、`required`、`type` 等不会误作输出字段。契约本身可以要求 `case_id/status/sources/uncertainty/change_records`，运行器直接填标准值。运行器额外提供 `overall_oracle_status`、报告路径和 spec 哈希等审计字段。

`spec.contract_values` 已知值优先于通用默认值，但它不证明正式完成。仍未由自动审计填充的契约字段会显式标 `not_populated_by_oracle_runner`，加入 `missing_required_evidence` 并使状态保持 `partial`；正式 agent 必须补真实证据，而不是删掉字段。

顶层 `result.status` 只允许 `success/partial/unable/refused`，不允许 `complete`。`case_id` 不可用或存在致命 `run_error` 时为 `unable`；否则候选/执行/来源/证据任何缺口及 synthetic 均为 `partial`，全部执行和证据门槛满足才是 `success`。论文目标 mismatch 是独立比较结论，不属于执行失败条件。

## 正式完成门槛与证据

`_witness` 是可选对象；以下键必须含非空对象或数组，且 case_id 可用、两个候选均完成并通过、case 与来源加载成功、所有契约字段已有证据、无运行错误时，才允许 `success`：

- `materials_environment_parameters`
- `two_candidate_materials_reviewed`
- `paper_table_figure_comparisons`
- `difference_attribution`
- `raw_data_repository_status`

没有 raw data/仓库时也应如实记录“缺失”，非空记录能说明已审计此缺口，但不意味着补齐材料。除了 witness，最终报告正文仍须逐项比较论文表图、列出材料/环境参数并解释候选-论文及论文-数学差异。witness 只是防漏字段，不是可随意断言的“完成按钮”。

合成示例始终 partial。它只有两个组织方候选和文本 fixture，明确不冒充真实 PDF、作者代码、原始数据或仓库。
