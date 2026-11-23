---
name: dualpass-scoring-calibrator
description: >-
  面向文献阅读 benchmark 的双通道评分校准器：对 T1 问答/解析/翻译/抽取和 T2 benchmark-DRAFT 出题工单执行机判、盲态复评、Cohen's kappa 一致性量化与书面裁决，并维护可审计 result.json。Use when a task requires calibrated scoring, inter-rater agreement evidence, disagreement adjudication, or executable rubric checks for reading-comprehension benchmark items.
---

# Dual-Pass Scoring Calibrator

## 用途与适用条件

本技能用于交付“不同人看同一份输出应得到同一结论”的证据链，而不是只给一次机器判分。它支持：

- **T1**：阅读问答、解析、翻译、抽取；对自己产出的答案做自评、盲态复评与校准。
- **T2**：benchmark-DRAFT 出题；起草题卡，并校准题卡评分规则的可执行性，即同一作答能否被两位评分者判成同一分数。

核心产物包括：`rubric.json`、两轮 `pass*_scores.json`、`disagreements.json`、Cohen's kappa、逐条书面裁决、`final_scores.json`、`agreement_report.md` 和最终 `/app/output/result.json`。

## 运行时契约

1. 平台将本技能安装在 `/skills/weekly-skill`；官方 DeepSeek Harness 会在 3 个隐藏固定案例上各运行 3 次。
2. 每个案例的输入为 `/input/case.json`、`/input/task.md` 以及 `/input` 下的源材料；源材料可能是真实 PDF，也可能是段落/表格文本，revision2 案例为段落/表格文本。
3. `case.json` 含有 `case_id` 与 `output_contract` 字段集；必须运行时动态读取，不得把隐藏案例字段、答案或格式预写死。
4. 工作目录为 `/app/work`；最终交付目录为 `/app/output`。
5. `/app/output/result.json` 必须包含：`case_id`、`output_contract` 声明的全部字段、`status`、`status_reason`、`sources`、`uncertainty`、`change_records`。
6. contract 字段填不了时填 `null`，并在 `uncertainty` 说明原因；不得编造值。
7. `status` 只能诚实使用“成功”“部分完成”“无法判断”“拒答”。`partial`/“部分完成”必须说明局限；有 pending 分歧时不得标“成功”。
8. 预算为 64 次模型请求、900 秒。必须先尽早写合法部分 `result.json`，再增量完善，避免超时后无交付。
9. 技能包约束：UTF-8 文本、无符号链接；平台上限为 50 个文件、单文件 500KB、总 2MB。
10. 本技能不包含任何隐藏案例预制答案；仓库内示例均为合成示例，不得把示例内容迁移到真实案例。

## 依赖

- Python 3.8+，脚本仅使用标准库。
- `pdftotext` 可选；存在时用于抽取 PDF，缺失时记录 `pdftotext_missing` 并继续处理可读文本，不崩溃。
- 无网络、无第三方包、无其他 bundle 文件依赖。

## 工单识别

- `task.md` 含“出题”“题卡”“benchmark”“DRAFT”“草拟”“4 道/4道”“四道”任一标记时判为 **T2**。
- 否则判为 **T1**。
- T2 题卡至少覆盖：任务、材料范围、参考答案、评分规则、证据锚点、难度、授权。五核心字段为任务、材料范围、参考答案、评分规则、证据锚点。

## 工作流程

### 0. 先初始化合法结果

```bash
python3 /skills/weekly-skill/scripts/score_pass.py --init \
  --case /input/case.json --output-dir /app/output
```

### 1. 编译 rubric

```bash
python3 /skills/weekly-skill/scripts/rubric_compile.py \
  --case /input/case.json --task /input/task.md \
  --source-root /input --output /app/work/rubric.json
```

### 2. 起草评分对象与通道 1 语义理由

在 `/app/work/agent_items.json` 写 T1 答案或 T2 题卡。每个证据对象使用：

```json
{"source":"relative/path.txt","locator":{"line_start":7,"line_end":10},"quote":"源文原句"}
```

在 `/app/work/pass1_semantic.json` 给每个 `item_id.correctness` 写 0/1/2 与非空 `justification`。机判维度由脚本给分；语义档没有理由会被拒绝。

### 3. 通道 1 评分

```bash
python3 /skills/weekly-skill/scripts/score_pass.py \
  --case /input/case.json --task /input/task.md --rubric /app/work/rubric.json \
  --items /app/work/agent_items.json --semantic /app/work/pass1_semantic.json \
  --source-root /input --output /app/work/pass1_scores.json
```

机判包括引文归一化后逐字核验（NFKC、fi/fl 连字、断词连字符、空白折叠，且必须位于声称锚点内）、字段齐备计数和诚实标记检查。

### 4. 盲态通道 2 与 kappa

另起独立判断，不向通道 2 展示 pass1 分数或理由；写 `/app/work/pass2_semantic.json` 后运行：

```bash
python3 /skills/weekly-skill/scripts/blind_rescore.py \
  --case /input/case.json --task /input/task.md --rubric /app/work/rubric.json \
  --items /app/work/agent_items.json --semantic /app/work/pass2_semantic.json \
  --source-root /input --pass1 /app/work/pass1_scores.json \
  --output /app/work/pass2_scores.json \
  --agreement-out /app/work/agreement_raw.json \
  --disagreements-out /app/work/disagreements.json
```

脚本先落盘 pass2，再读取 pass1 比较，输出逐维一致率、Cohen's kappa 与全部分歧。

### 5. 书面裁决并清零 pending

为每个分歧写 `{item, dimension, pass1, pass2, final, rationale, evidence_anchor}`。无理由或无锚点会被拒绝并保持 pending。

```bash
python3 /skills/weekly-skill/scripts/adjudicate.py \
  --case /input/case.json --pass1 /app/work/pass1_scores.json \
  --pass2 /app/work/pass2_scores.json --agreement /app/work/agreement_raw.json \
  --disagreements /app/work/disagreements.json \
  --adjudications /app/work/adjudication.json --items /app/work/agent_items.json \
  --source-root /input --final-out /app/work/final_scores.json \
  --report-out /app/work/agreement_report.md --result /app/output/result.json
```

### 6. 导出

确认 `/app/work/agreement_report.md`、`/app/work/final_scores.json` 和 `/app/output/result.json` 存在；result 中的 contract 字段已填或显式为 `null` 且有不确定性说明。

## kappa 解读

| Cohen's kappa | 一致性 | 处置 |
|---:|---|---|
| < 0.4 | 差 | 规则或评分者理解不稳定，应修订锚点并升人工复核 |
| 0.4 ≤ κ < 0.6 | 中 | 逐项检查分歧，补充行为锚点 |
| 0.6 ≤ κ < 0.8 | 良 | 可交付，但须保留分歧裁决链 |
| ≥ 0.8 | 优 | 仍须报告残余风险，不能等同真值 |

N < 30 时 κ 对单个分歧高度敏感；若只有一个评分类别，κ 可能数学退化，脚本会报告观察一致率和退化原因。

## 异常处理

| 异常 | 处理 |
|---|---|
| `case.json` 或 contract 畸形 | 保留可写字段为 `null`，标“无法判断”或“部分完成”，记录 uncertainty |
| PDF 无法抽取或无 `pdftotext` | 记录 `pdftotext_missing/failed`，仅使用可读文本，不伪造引文 |
| 引文不在锚点内 | evidence_anchoring 降档，列入机器 verdict |
| 语义档缺 justification | 当轮评分拒绝接受，返回明确错误 |
| pass1/pass2 分歧无有效裁决 | 标 pending；result 只能“部分完成” |
| κ 退化或小样本 | 报告一致率、退化原因和残余风险，必要时升人工 |

## 交付前自查

- `disagreements.json` 中每项均已被接受裁决覆盖，`pending_count = 0`。
- 每个 `final` 都有非空 `rationale` 和可定位 `evidence_anchor`。
- `agreement_report.md` 存在，含一致率、κ、分歧处置统计与残余风险。
- `result.json` 含全部动态 contract 字段；填不了的字段为 `null` 且不编造。
- `status` 与实际完成度一致；任何 pending 均不得标“成功”。

## 限制

双通道通常来自同一模型、同一源材料，因此共同错误可能仍一致；κ 是一致性下界和规则可执行性信号，不是真值保证。机器核验能证明“引文是否在锚点内”，不能单独证明语义答案正确。
