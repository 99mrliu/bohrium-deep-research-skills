---
name: controlled-attribution-lab
description: >-
  将数值复现中“结果对不上”转化为预注册、可证伪的单变量干预实验；执行两个候选方法，按基线噪声给出 supported、falsified 或 inconclusive 的受控归因证据。
---

# Controlled Attribution Lab

## 何时使用

当真实论文、图表或目标数值与候选实现的结果不一致，需要区分实现、参数、数据、环境或随机种子因素时使用。本 Skill 产出**受控干预证据**，不是把同一管道重跑多次，也不是靠放宽容差或更换容差工具制造一致。

**边界：** 只能写“受控证据支持/未支持”，不得自动宣称已证明唯一根因。结论仅 `attributable only within tested conditions`。相关、同时变化或事后挑选的变体不构成单因素因果证据。

## 正式材料与诚实声明

1. 阅读 `/input/case.json`、`/input/task.md`、真实 PDF、两个候选数值方法及其输入。先定位论文目标、图表、材料体系、参数来源与候选实现，再设计干预。plan 必须用 `case_file` 指向真实 case；执行器从该文件读取 `case_id` 和 `output_contract` 的全部回答字段。
2. 正式数据通常由组织方合成，**不是作者原代码，也不是全量 PMLB**。不得把组织方合成材料描述为作者官方实现或完整原始数据。
3. 若 `/input` 没有原始数据仓库，必须在 `sources`、`uncertainty` 和报告中明确写“未提供原始数据仓库”，列出检查位置，并说明因此不能核验原始仓库历史、完整数据或作者环境。
4. 论文没有报告的步长、迭代上限、随机种子、噪声、初始化、求解器细节等，只能标为“本实验自行设定”，不得写成论文事实。建立“论文明确报告 / 任务材料给出 / 自行设定”三列表。
5. 必须实际运行候选 A 和候选 B。A 崩溃、超时、无指标或未达目标时，仍须运行 B；记录失败而不是用 B 代替 A 的证据。
6. 对论文目标采用**事前容差**比较，并做要求的图/表逐项对照。禁止看到结果后修改论文目标、容差、假设方向或变体。没有论文容差时，在 pre-registration 中声明任务容差或自行设定及依据。
7. 严格区分正式 `case.output_contract`（字段回答合同）与 `plan.artifact_contract`（产物路径账本）。case 合同支持 list、mapping、`fields/required_fields` 和 JSON Schema；每个必需字段都平铺在 result 顶层。字段可含执行器生成的实质证据或 plan 中有 evidence 的 `contract_values`；无法回答时写带 reason、missing/next_steps 的结构化 `unavailable`。未知回答字段绝不能只填 artifact 路径，只有标准 `runs/intervention_report_json/intervention_report_md/result` 字段可用路径值。标准 `case_id/status/sources/uncertainty/change_records` 等也允许写入 case 合同。

## 目录纪律与 900 秒保底

- `/input`：只读。不得编辑、移动、清理或在其中生成缓存。
- `/app/work`：解包文本、中间日志、抽取的表格、临时脚本和实验输出。
- `/app/output`：最终的 `runs/`、`intervention_report.json`、`intervention_report.md`、`result.json` 及要求的图表。
- 其他环境可将输入、中间和输出分别映射到等价的只读、工作、最终目录，但报告中要写明映射。

按总预算 900 秒设计：0–120 秒定位材料并冻结目标；120–240 秒写假设、预测 signatures、plan 并封存 SHA256；240–650 秒运行全部基线和变体；650–780 秒计算噪声、对照图表并报告；780–900 秒只做核验与保底。时间不足时先保存已成功运行、失败记录、诚实 `status: "partial"`、缺失项和现有报告，不得为了完整状态省略 B 或编造指标。

## 必做工作流

### 1. 固定比较对象

记录 case、材料版本、两个候选的代码路径与 SHA256、论文页码/图号/表号/方程、目标值、单位、指标定义和事前数值容差。图表至少对照趋势、关键点、误差和单位；不能仅比较一个最终标量。若 PDF 无法抽取图值，说明方法、分辨率和读数不确定性。

### 2. 先注册假设与预测 signatures

为每个可证伪假设在运行前写：

- `hypothesis_id`、单一 factor、唯一 `changed_path`、明确干预；
- 指标方向：`increase`、`decrease` 或 `unresolved`；
- 可观察预测 signatures（数值、输出结构、图表变化）及会证伪它的结果；
- 对应的 baseline、变体、输入、输出和重复运行。

将完整计划写入 JSON，排除 `registration.plan_sha256` 字段后按 UTF-8、排序键、紧凑 JSON 计算规范 SHA256，并把哈希填回该字段；详见 `references/plan_schema.md`。哈希必须绑定 case_file、contract_values、artifact_contract、hypotheses、predicted signatures、runs、variants 和容差等全部计划内容。执行器逐字核验，哈希不符即拒绝，不能看结果后重封计划。旧 `plan.output_contract` 仅作为 artifact 路径映射的向后兼容别名，绝非正式 case 回答合同。

### 3. 运行 baseline + variants

每个 variant 相对其明确列出的 baseline **只能改变一个科学 factor**，合法值为：

- `implementation`
- `parameter`
- `data`
- `environment`
- `seed`

`changed_paths` 必须恰好含一个不同路径，且以 `<factor>.` 开头。重复计数同一个路径不是多个科学 factor；重复项同样判为 confounded/非法并拒绝。跨 baseline 再改第二个字段、同时换实现和参数、或改变未声明工作目录/输入，都不得做强归因。

每个候选至少做 3 次 baseline（最低可为 2 次，但须标记不确定性），使用已注册的 seed/环境。所有变体运行失败也保留 stdout、stderr、退出码、超时、env、cwd 和 argv。执行器不得因 A 失败停止 B。

### 4. 先估计 noise floor，再判方向

对同一 variant 的 baseline 数值指标计算两两绝对差的最大值，加 plan 中事前声明的 `noise_epsilon` 得 noise floor。效应为变体中位数减 baseline 中位数：

- `abs(effect) <= noise_floor`：`inconclusive`；
- 方向与事前 `increase/decrease` 一致且超过 noise floor：`supported`；
- 方向相反且超过噪声：`falsified`；
- `unresolved` 不预设方向；超过噪声只能支持“存在可检测干预效应”，不能识别唯一根因；
- 运行失败、有效重复不足或指标缺失：相关假设 `inconclusive`，且 `result.status: "partial"`、`execution_status: "partial"`；计划/hash 违规则预检零执行，`result.status: "unable"`、`execution_status: "rejected"`，不得强归因。

在 `references/protocol.md` 规定的框架中报告 `supported/falsified/inconclusive`、noise floor、baseline/variant 原值、效应和全部限制。

### 5. 回到复现问题，而非只做变体

最终报告必须分别回答：两个候选是否达到论文目标的事前容差；哪些图表一致/不一致；哪个受控干预改变差异；哪些假设未支持或不确定；剩余差异能否由现有测试区分。受控证据只支持测试条件内的因素贡献，不排除未测因素。

## 执行器

```bash
python3 scripts/controlled_attribution.py \
  --plan /app/work/plan.json \
  --output-dir /app/output
```

计划格式见 `references/plan_schema.md`。执行器实际使用 `subprocess.run(argv=..., cwd=..., env=..., timeout=...)`，逐项保存 stdout/stderr，从 stdout 最后一个非空行解析 JSON 数值指标。它输出：

- `preregistered_plan.json` 与 `plan.sha256`；
- `runs/index.json` 及每次运行的 argv/env/cwd/stdout/stderr/exit/timeout/JSON metric；
- `intervention_report.json`、`intervention_report.md`；
- `result.json`，包含真实 case 的 `case_id`、case `output_contract` 的**全部顶层回答字段**、合法的 `status`、`execution_status`、`sources`、`uncertainty`、`change_records`、artifact 账本、哈希和结论；不额外嵌套 `output_contract`。

顶层 `status` 只能为 `success/partial/unable/refused`。全部运行成功且 artifact 与回答证据完整时为 `success/complete`；运行、artifact 或回答不完整时为 `partial/partial`；hash/case/schema/非法 factor/confounded 预检拒绝时为 `unable/rejected` 且零命令执行。退出码依次为 0、1、2。科学假设仍可为 supported/falsified/inconclusive，与上述状态轴独立。

## 最小示例与自检

`examples/synthetic/` 给出一个真实单因素参数 bug、两个实际候选、材料文本、case/task、有效预注册计划和一个 confounded 负例。执行：

```bash
bash examples/synthetic/run_example.sh /absolute/verification/output
```

预期三项结论依次为 supported、falsified、inconclusive；负例退出码 2、零命令执行。详见 `examples/synthetic/expected.txt`。这是机制示例，不是真实论文复现或全量数据结论。
