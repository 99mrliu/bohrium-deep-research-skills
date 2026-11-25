---
name: quantitative-claim-reconciler
description: 用于从表格、图注和公式的显式源操作数建立量值证据台账，复算 share、ratio_percent_change、relative_cpu_time_change、sum_reconciliation 与 residual，并核对完整行列标题、统计单位、计数对象、分母、百分点与相对百分比、panel units、残差/head graph 及直接报告/计算结论。遇到缺操作数、除零、分母混淆或对账不平须停止或标未决。不用于版面索引、通用覆盖率、通用 lint、RDF 导出、图片像素测量，也不用于猜测缺失数值。
---

# Quantitative Claim Reconciler

唯一目标是让量值断言可定位、可复算、可审计。只使用来源中明确给出的操作数；未知即未知，不做单位、分母、人数或图形的隐式推断。

## 触发与不触发

触发：要求核对表格/图注/公式中的量值语义；区分 mentions、unique identifiers、people；确认比例分母、相对百分比与百分点；检查 panel units、head graph 的直接值与 residual；从源操作数复算并保留证据链。

不触发：仅做版面坐标/索引、字段覆盖统计、格式 lint、RDF 导出，或要求从曲线/柱长读数而没有明确图注数值。若任务仅属这些方向，不要强行复算。

## 输入、契约与优先级

先读取平台原始 `/input/case.json`、`/input/task.md` 与实际材料路径。原始 case 可能只有 `case_id`、PDF/草稿文件路径和任务说明，**不得假定平台已提供结构化的 `sources/evidence/assertions`，也不得用示例数据代替论文阅读**。Agent 须先按任务阅读原文、图表与草稿，建立 `/app/work/adapted/case.json`：原样复制 case_id，以实际转录和证据填充 `sources/evidence/assertions`，所有计算操作数使用十进制字符串；禁止 NaN/Infinity、隐式补零与 null 猜测。适配工作记录须列出原始文件路径与映射，不得把适配文件写回 `/input`。

脚本需要任务适配文件中的 `OUTPUT_CONTRACT_START` 与 `OUTPUT_CONTRACT_END` 之间含一个 `json` fenced block。若原 `/input/task.md` 已经提供机器可读 output_contract，则直接提取；若以散文或 JSON Schema 声明，则 Agent 忠实转写为 `/app/work/adapted/task.md`，其中 `required_result_fields` 与 `required_calculation_fields` 必须完整覆盖原契约。原任务只要求 result.json 时，不得自行要求 calculations 成为正式顶层字段；它仅是本技能的审计副产物。适配不得增删、缩窄或改写原科学问题，原 task 始终优先于本 Skill 示例。

`environment/resources.yaml` 只支持示例中的简单 YAML 键值结构；`max_requests` 不得超过 64，`max_seconds` 不得超过 900，默认工作目录 `/app/work`，默认产物目录 `/app/output`。若平台在 `/input/environment/resources.yaml` 或 `environment/resources.yaml` 另提供资源清单，先读取并采用实际路径。

优先级：原 `/input/task.md` 的 output_contract > 忠实适配副本 > CLI 默认值 > 非契约资源默认值。资源文件不能删除 task 要求的字段。未实现的契约字段应报错并由 Agent 按原契约交付，不得编造值。完整适配 schema 见 [task-io.md](references/task-io.md)。

## 执行流程

1. 读 references/quantitative-evidence.md，为每条直接量值记录完整来源、行列或 panel 定位、统计单位、对象和分母范围。
2. 读 references/calculation-reconciliation.md，逐条选择受支持的运算；明确直接报告还是计算结果。
3. 使用 `/app/work` 保存逐步台账，使用 `/app/output` 保存 `calculations.json` 和 `result.json`。不得把临时文件写入输入目录。
4. 在断言处理前写出 honest partial；每处理一条立即原子更新两个产物与 work ledger。失败时保留已完成结果，将当前断言标为 `pending`/`unresolved`，说明原因并返回非零。
5. 验证每条计算断言的全部 evidence IDs 均存在，且操作数与 evidence 的显式数值一致。不同统计对象、单位或分母范围不可相除；不静默换算。
6. `result.json` 必须保留输入原 `case_id`、task 要求的全部字段，以及注册字段中的 `sources`、`uncertainty`、`change_records`。task 若要求这些字段则绝不可省略。
7. 最多 64 requests、900 秒；脚本不发网络/模型请求，记录 `external_requests_used: 0`。超限或数值无法确定时标未决，不猜数。

## 标准命令与产物

在 Skill 根目录执行正式任务。先完成上述原文阅读与适配；若原始输入已经符合工具形状，可将前两个参数直接指向 `/input`，否则使用忠实适配副本：

```bash
python3 scripts/quant_ledger.py \
  --case /app/work/adapted/case.json \
  --task /app/work/adapted/task.md \
  --resources environment/resources.yaml \
  --work-root /app/work \
  --output-root /app/output
```

运行后再以原 `/input/task.md` 审计实际产物，适配校验不能替代原契约复核。

产物：

- `/app/work/work_ledger.json`：逐步、可恢复的 honest partial 台账。
- `/app/output/calculations.json`：操作数、公式、精确分数、舍入、直接/计算 provenance 和 evidence 校验。
- `/app/output/result.json`：原 case_id、断言结果、sources、uncertainty、change_records 及实际 output_contract 要求的字段。

复现合成正例（SYNTHETIC，非正式结果）：

```bash
rm -rf /tmp/quantitative-claim-reconciler-positive
python3 scripts/quant_ledger.py \
  --case examples/synthetic/input/case.json \
  --task examples/synthetic/input/task.md \
  --resources examples/synthetic/environment/resources.yaml \
  --work-root /tmp/quantitative-claim-reconciler-positive/work \
  --output-root /tmp/quantitative-claim-reconciler-positive/output
python3 -m json.tool /tmp/quantitative-claim-reconciler-positive/output/calculations.json
python3 -m json.tool /tmp/quantitative-claim-reconciler-positive/output/result.json
```

真实正负回归与期望产物比较：

```bash
python3 tests/test_quant_ledger.py
```

单独运行两个负例；两者都应退出 2，且已保存部分产物：

```bash
python3 scripts/quant_ledger.py --case examples/negative_unbalanced/input/case.json --task examples/negative_unbalanced/input/task.md --resources examples/negative_unbalanced/environment/resources.yaml --work-root /tmp/qcr-unbalanced/work --output-root /tmp/qcr-unbalanced/output
python3 scripts/quant_ledger.py --case examples/negative_division_zero/input/case.json --task examples/negative_division_zero/input/task.md --resources examples/negative_division_zero/environment/resources.yaml --work-root /tmp/qcr-zero/work --output-root /tmp/qcr-zero/output
```

Python 要求为 3.9+，仅标准库。无网络、第三方包、个人绝对路径或外部 bundle 依赖。所有示例数值均为 **SYNTHETIC 合成数据，非正式结果**。
