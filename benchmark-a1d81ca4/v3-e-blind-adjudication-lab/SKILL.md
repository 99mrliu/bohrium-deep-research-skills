---
name: v3-e-blind-adjudication-lab
description: 从真实段落或表格推导并交付恰好四道 source-conditioned benchmark-DRAFT 固定题，保留 reference answer、0/1/2 rubric、证据、来源、不确定性和变更记录；在实际 human verdict 存在时可增加独立盲审、裁决及描述性自动—人工比较。没有人审verdict时主任务仍可成功，盲审明确标记未开展，绝不伪造。
---

# Blind Adjudication Lab

## 主任务与可选增强

**PRIMARY（必须完成）**：从实际提供的段落/表格推导并交付**恰好四道**真实 source-conditioned `benchmark-DRAFT` 固定题。每题必须有稳定 item ID、问题/prompt、由 agent 从实际来源推导的 `reference_answer`、完整 0/1/2 rubric 和精确 evidence refs；交付还必须保留 sources、uncertainty、change_records，以及 `case.json` 原始 `output_contract` 要求的其他诊断字段。

**OPTIONAL（仅在实际材料存在时）**：若提供了真实独立 human reviewer verdict，可再进行匿名盲审、显式裁决、自动—最终比较、failure/probe 转化。人审不是四题主任务的前置条件。

- 没有实际 verdict：必须记录 `review_status="not_conducted_no_human_verdicts"`，adjudication/agreement 用明确的 `status="not_applicable"` 对象；不计算 human kappa，不伪造 verdict、final、reviewer 或 adjudicator。这**不阻止**完整四题库 `status="success"`。
- 提供了实际 review artifacts 但不完整或有 unresolved：review 部分保持 `review_status="partial"`、agreement 保持 partial，uncertainty 明确缺失，不声称完成 calibration；主任务状态独立判断，完整四题库仍可 `status="success"`。
- 实际独立 review 完整时：`review_status="conducted"`；保留原有严格 review 质量检查和 disagreement/mismatch 诊断。

无绑定契约字段或四题科学交付不完整仍使主任务 `partial`；不得把 optional review 字段的 `not_applicable` 当成主任务缺失。

## 触发与非触发

**触发：**

- benchmark-a1d81ca4 revision2 的四个固定 case 需要从实际段落/表格形成并导出 benchmark-DRAFT，即使没有任何人类评审。
- 已有实际 human verdict，需要独立盲审、0/1/2 三维判断、逐对分歧和 source-grounded 显式裁决。
- 需要比较 automatic/final labels 并把 mismatch 转为失败分类和带原 retest item IDs 的 targeted probe。
- 需要检查 reviewer identity、candidate author、automatic score 泄漏，或区分主题库完成状态与 review partial/not conducted。

**不要触发：**

- 只需要 recurrent source-index、source blueprint、通用 scoring-engine、run-ledger 或任务编排流水线。
- 想在没有真实评审记录时模拟“人类”分数，或用 reviewer agreement/kappa 证明科学答案为真。
- 输入无法形成恰好四道 source-conditioned 题；不得猜测科学内容补齐。

## 实际输入、目录与交付契约

DeepSeek 实际任务中从 `/input` 只读获取：

- `/input/case.json`：**权威机器输入**，含 `case_id`、固定 case 说明和原始 `output_contract`。
- `/input/task.md`：任务说明 prose；可帮助理解科学任务，但**不是 output contract 来源**，不得覆盖 case。
- `/input/materials.json`：真实材料映射；段落、表格及定位必须可追溯到实际所给源。
- item bank、raw candidate outputs、auto scores、source evidence 的实际路径由 materials 指定。`examples/input` 的四题、源文、verdict、裁决和 automatic scores 全为**合成流程夹具**，不能冒充真实 benchmark 结果。

脚本直接解析 `--case /input/case.json`，从不读取 task JSON。支持以下 `case.output_contract` 形态，字段均原样输出在 result 顶层，不增加替代包装层：

1. `list[str]`；
2. `{"fields": list[str]}`；
3. `{"fields": list[{"name": ...}]}`；
4. 直接 `field -> description/schema` map；
5. JSON-schema 风格 `{"properties": {...}}`；
6. 兼容 `{"required_top_level_fields": list[str] 或 list[{"name": ...}]}`。

`case_id` 与 `status` 无论是否在 contract 中重复声明，均自动置于结果顶层。`item_bank`/`benchmark_draft` 等映射到原四题库，`items`/`questions` 等映射到四个完整 item records，`reference_answers` 和 `rubrics` 映射到逐题记录，sources/evidence 映射到真实 source document，diagnostics/summary 映射到主任务与 review 的分离状态。无法识别的字段不猜造内容，保留 null 并使主任务 partial。可选 adjudication/agreement 在无人审时是非 null、`not_applicable` 的 typed object。

仅使用 `/app/work/blind-adjudication` 保存中间物。若开展 optional review，盲审包位于 `work/.../prepare/review_packets`；私密身份 key 位于包树之外的 `work/.../prepare/private/private_key.json`，不得发给评审或复制进最终交付。最终写 `/app/output/result.json`；支撑文件以普通文件写到 `/app/output`，不要链接 work 中私密材料。

启动后、任何耗时推导或复核前，先写早期部分结果，保证原 contract 每字段和 `case_id` 在顶层；无人审初始化也写入准确的 review 状态：

```bash
python3 scripts/finalize.py --case /input/case.json \
  --output-dir /app/output --early-partial
```

## PRIMARY：无人审也可成功的四题工作流

### 1. 固化真实来源与四题

从实际段落/表格提取恰好四道 source-conditioned benchmark-DRAFT 题。每题保留稳定 item ID、问题、由 agent 推导的 scientific reference answer、0/1/2 rubric、精确 source ID/locator。表格保留行、列和脚注；数值、单位、样本量、否定与未测量范围不可省略。参考答案由来源推导，不能由评审多数票替代。

如果真实来源缺失、定位不唯一、题目不足/超过四道或 item ID 重复，保留早期 partial 并在 uncertainty 说明具体缺口；不得猜测内容补齐。这里的 primary item bank 不要求 candidate output、automatic score、reviewer identity 或 human verdict。

### 2. 无人类 verdict 时直接 finalize（完整主路径）

```bash
python3 scripts/finalize.py \
  --case /input/case.json \
  --item-bank /app/work/blind-adjudication/item_bank.json \
  --source-evidence /app/work/blind-adjudication/source_evidence.json \
  --output-dir /app/output
```

此命令验证四题的 prompt、reference answer、0/1/2 rubric、evidence refs 与 sources；不改写科学内容。成功结果包含四个完整 items、原始 item bank、sources、uncertainty、change records、summary/diagnostics，同时 adjudication/agreement 明确 not applicable、 human verdict 为空、human kappa 不计算。`status=success` 只陈述四题主交付完成，不陈述有人审或科学答案经人类认证。

## OPTIONAL：仅在实际 verdict 存在时的盲审增强

### 1. 准备并分发独立盲审包

只有确实要收集独立 review 时才需要 candidates、auto scores 和至少两名 reviewers：

```bash
python3 scripts/prepare_review.py \
  --item-bank /app/work/blind-adjudication/item_bank.json \
  --candidate-outputs /app/work/blind-adjudication/candidate_outputs.json \
  --auto-scores /app/work/blind-adjudication/auto_scores.json \
  --source-evidence /app/work/blind-adjudication/source_evidence.json \
  --reviewers /app/work/blind-adjudication/reviewers.json \
  --output-dir /app/work/blind-adjudication/prepare
```

每位评审只拿自己的 packet。alias 是有顺序和输入身份决定关系的确定性标识，不是访问控制，也不是密码学安全匿名。不得向评审透露 private key、其他评审 verdict、自动分数、评分器名、评审身份或 candidate author。包中 `actual_answer` 是实际提交答案，`reference_answer/rubric/source_evidence` 供源证据判断。

### 2. 收集真实独立 verdict 并强制裁决

每名真实评审独立提交 JSONL；每行必须有 packet alias、item ID、0/1/2 总评分、三个 0/1/2 维度、具体 comments、source refs 和带时区提交时间。没有真实 verdict 时不能由 DeepSeek 补造。

```bash
python3 scripts/adjudicate.py \
  --review-manifest /app/work/blind-adjudication/prepare/prepare_manifest.json \
  --human-verdicts /app/work/blind-adjudication/verdicts_1.jsonl \
  --human-verdicts /app/work/blind-adjudication/verdicts_2.jsonl \
  --adjudications /app/work/blind-adjudication/adjudications.jsonl \
  --deadline '2026-12-31T23:59:59+08:00' \
  --output-dir /app/work/blind-adjudication/adjudication
```

每个总分或维度分歧、任何非二元 verdict、缺失有效 verdict 的项目均需真实显式 adjudication：`status=resolved` 时含 final score、rationale、带 `evidence_note` 的具体 source refs；`status=unresolved` 时 final score 必须为 null 并写明原因。迟到记录排除，重复 alias/item 全部排除并要求独立重交，缺失/无效 ID/坏维度全部可见。脚本 review 数据状态非成功时写 review `partial` 并退出 3；输入级错误退出 2。该 partial 是 **review 状态**，不再自动阻断 primary item-bank success。

### 3. 描述性自动—最终比较与失败转化

```bash
python3 scripts/agreement.py \
  --auto-scores /app/work/blind-adjudication/auto_scores.json \
  --adjudication /app/work/blind-adjudication/adjudication/adjudication.json \
  --output-dir /app/work/blind-adjudication/agreement
```

仅比较同一套 0/1/2 标签，不重标定、不填补。raw agreement 分母是有已解决 final 的 comparable items；混淆矩阵保留自动为行、最终为列；unresolved/missing 单列且不进分母。Cohen kappa 使用 `po=matches/n`、`pe=sum_c(auto_count_c/n*final_count_c/n)`、`(po-pe)/(1-pe)`；至少四个 comparable 且两方各出现至少两个类别、`1-pe != 0` 才报告算术值。即使可算，四题固定组仍标注 synthetic/low-N descriptive，不能声称 DSH 成绩、统计信度或科学真值。无人审时 kappa 是 `not_computed_no_human_verdicts`，不是 0。

每个 auto != final 自动产生一个可搜索 failure，含分类、观测/期望行为、证据、原 final、具体 fix；再产生 targeted probe，含 reason、expected fix、pass condition、原 `retest_item_ids` 和 held-out variation 要求。失败分类见 `references/failure_taxonomy.md`。

### 4. 带实际 review artifacts 的 finalize

```bash
python3 scripts/finalize.py \
  --case /input/case.json \
  --item-bank /app/work/blind-adjudication/item_bank.json \
  --source-evidence /app/work/blind-adjudication/source_evidence.json \
  --adjudication /app/work/blind-adjudication/adjudication/adjudication.json \
  --agreement /app/work/blind-adjudication/agreement/agreement.json \
  --failures /app/work/blind-adjudication/agreement/failures.json \
  --targeted-probes /app/work/blind-adjudication/agreement/targeted_probes.json \
  --output-dir /app/output
```

完整四题且 contract 全部绑定时主任务 success。review complete 需要四题及时有效记录、所有触发的裁决完成、无 unresolved/missing final、无未处理质量问题，并且每个 mismatch 恰有一个 failure/probe。任何 incomplete/unresolved 只令 `review_status=partial` 并写入 uncertainty/summary/change_records；final score 不得填补，主任务不因它下降。

## 依赖、失败状态与验收

- 仅依赖 Python 3 标准库；示例外壳需要 bash。无 pip、网络、git、凭据或提交步骤；bundle 内无本地机器绝对路径。
- `prepare_review.py` 输入错误退出 2；`adjudicate.py` review partial 退出 3、输入错误退出 2；`agreement.py` 对 unresolved 写 review partial；`finalize.py` 分开计算 primary 与 optional review 状态，未解决不会被假装完成。
- 动态 contract 绑定：`item_bank/draft_item_bank/benchmark_draft/benchmark_item_bank`、`items/questions/benchmark_items/draft_items`、`reference_answers/rubrics`、`sources/source_evidence/evidence`、`uncertainty/change_records/summary/diagnostics` 都有非空主任务产物。unknown field 仍为 null + primary partial。
- 详细协议见 `references/review_protocol.md`；失败修复与 retest 见 `references/failure_taxonomy.md`。

## 可运行示例（从 bundle root 调用）

先进入本 bundle 根目录，即包含 `SKILL.md`、`run_example.sh`、`scripts/`、`examples/` 的目录，然后运行：

```bash
bash run_example.sh
# 或把全部生成物放到调用者指定的相对/任务临时目录：
bash run_example.sh example-output
```

脚本依次验证：

1. **no-human primary path**：四题导出 success、original contract 全字段非 null、review 未开展且无 human kappa；
2. 所有动态 contract shapes；
3. 完整保留的 synthetic positive adjudication（ disagreement、mismatch failures/probes）；
4. blinding leak negative control；
5. unresolved negative control（review partial/kappa undefined，但完整四题主任务仍 success）；
6. 静态审计。

所有生成物仅留在临时或调用者指定目录，不提交到 skill。
