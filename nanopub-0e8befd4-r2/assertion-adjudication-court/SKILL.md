---
name: assertion-adjudication-court
description: "Adjudicate an existing scientific draft assertion-by-assertion by its supplied input_id against supplied source texts, preserving each ID and original claim and producing evidence-linked supported/contradicted/not_established/mixed component verdicts and audit artifacts. Trigger for assertion adjudication, claim-evidence court, source-time/modality/subject-object review, or corrected-claim linkage of an already drafted list. Do not trigger for initial claim extraction followed by linting, PDF/layout work, generic issue matrices, numerical calculation, literature discovery without source text, or export engineering."
---

# Assertion Adjudication Court

## Purpose and hard boundary

对**已有科研草稿断言逐 ID 裁决**。先固定 ID 与原文，再查证据、拆原子 component、判定并记录修正建议；不是从全文重新抽取断言后做 lint。每个输入 ID 必须在台账中恰好出现一次，`original_claim` 不得改写。不可静默丢弃、合并或新增输入断言。

不做PDF版面、问题矩阵、数值计算或导出工程。`review_disposition=reject`、断言 contradicted/not_established/mixed 都是正常裁决结果；只要所有 ID 完整裁决且审计通过，流程状态仍为 `success`。

随附 examples 全部都是 **SYNTHETIC / 合成样例，非正式科研结果**，不得引用为真实科研证据。

## Inputs, authority, paths, and budget

1. 读取只读 `/input/case.json` 与 `/input/task.md`，再按其中真实路径读取原始 PDF、文本和待裁决 assertions。**平台原始 case 可能只有材料路径，不能假定已有 normalized assertions/sources，也不能把草稿断言当作证据。** Agent 先逐条冻结输入 ID/原文并读取原论文，构造 `/app/work/adapted/case.json`：原样复制 case_id，将输入断言映射为唯一 `input_id`/`claim`/`compound`，将论文的忠实提取文本映射为带 `source_id`/原始 `text` 的 sources；保留实际文件路径、页码和提取不确定性。不得修改 `/input`。
2. 原任务的 output_contract 是**最高优先级**，无论其表达为散文、字段表还是 JSON Schema。工具需要 `## output_contract` 后的 JSON block 时，Agent 将全部 required fields、状态名与制品名忠实转写到 `/app/work/adapted/task.md`；适配不增删或缩窄原契约。最终 `/app/output/result.json` 必须直接对照原任务复核，保留原 `case_id` 并包含实际契约的全部字段，而非只满足适配副本。
3. 查看实际 `environment/resources.yaml`（若平台提供 `/input/environment/resources.yaml` 则优先读取该实例），确认材料挂载与限制。本 Skill 工具使用 Python 3.9+ 标准库，**最多64 requests、总计900秒**。网络不是合成样例的运行前提。
4. 所有中间快照写 `/app/work`，最终制品写 `/app/output`，或写实际 output_contract 指定的其他位置。不要写回 `/input`；不要在个人绝对路径下寻找依赖。

开始前创建 `/app/work/adjudication-ledger.partial.json`，先登记全部 ID 和原文，再逐步裁决并覆盖快照。接近请求或时间上限时，停止新增工作并立即可写地保存诚实 partial：保留每个 ID，未决项 `pending + verdict:null + components:[]`，所有契约字段仍齐全。缺 ID 是验证错误，不是合法 partial。

## Required adjudication procedure

1. **冻结输入**：记录 case_id、ID 顺序、原文和 raw source text。不得以 corrected text 替代原文。
2. **逐 ID 拆句**：`compound=false` 恰一个原子 component；`compound=true` 至少两个。每个 component 明确 claim nature、evidence basis、rationale 和 evidence。
3. **逐 component 判 disposition**：supported/contradicted/not_established。支持要有 `support`；contradicted 必须有直接相反事实的 `reverse`；只有证据缺口时是 not_established。每条 evidence 的 source 必须存在，quote 必须是该源文的精确连续子串。
4. **机械归并顶层 verdict**：component disposition 只有一种时顶层取该值；出现两种或三种时取 `mixed`。非法 mixed、单一 disposition 却 mixed 均拒绝。
5. **强制语义核查**：主客方向、主动/被动等价、模态强度、来源与测量时间层、跨来源冲突、直接测量与作者推断。跨源逐层裁决，不投票或平均。
6. **分流未知与反证**：无支持的建议/规范提议通常为 not_established；来源确实提出某建议只支持其“提议归属”；明确出现相反结果的负事实才 contradicted；长时未测试不能证明长时必然失败。
7. **修正只另存** 在非 supported 或需要改写的断言上可给出独立 `corrected_claim_ids`，链接 `corrected_claims`，并在 `change_records` 留痕。输入原文仍不变。
8. **同步记录** `sources`、`uncertainty`、`change_records`，即使为空也保留，并与 result 一致。未消解冲突和证据边界写 uncertainty，不能隐藏。
9. **状态判定**：全部 `adjudicated` 且 `audit_complete=true` 才 success；早停/未决为 partial。reject 不等于流程失败。
10. **运行 checker**：失败报告也保存。不得删除未裁决 ID、手工把报告 valid 改 true 或忽略非零退出。

完整规则见 [references/verdict-logic.md](references/verdict-logic.md)，字段与状态机见 [references/audit-fields.md](references/audit-fields.md)。

## Output artifacts

除非实际 output_contract 另有规定，在 `/app/output` 仅交付：

- `adjudication-ledger.json`：逐 ID 原文、component verdict、证据、修正链接、sources/uncertainty/change_records。
- `adjudication-report.json`：checker 生成的覆盖、逻辑、证据与状态验证结果；失败也保留。
- `result.json`：原 case_id、success/partial、契约全部字段、真实计数与制品路径。

所有为 UTF-8 JSON 文本；只写契约制品和 `/app/work` 必要快照。不生成PDF、版面文件、问题矩阵、计算表或导出包。

## Checker CLI and complete local verification

在 Skill 根目录执行以下命令。`SKILL_DIR` 可由调用方设置为解包后的本目录；不要改成个人机器路径。

### 实战制品校验

```bash
export SKILL_DIR="$(pwd)"
mkdir -p /app/work /app/output
python3 "$SKILL_DIR/scripts/check_adjudication.py" \
  --case /app/work/adapted/case.json \
  --task /app/work/adapted/task.md \
  --ledger /app/output/adjudication-ledger.json \
  --result /app/output/result.json \
  --report /app/output/adjudication-report.json
```

退出码0表示所有结构与语义约束通过；退出码1表示验证失败且 report 已保存；usage/I/O 等错误也会非零退出。checker 验证 ID 一次覆盖、原文不变、component/verdict 逻辑、反向证据、corrected links、源与 quote、修正/变化记录、实际契约字段和 partial/success 状态机。

### 合成正例：重新真实生成 expected result/report

```bash
cd "$SKILL_DIR"
python3 scripts/check_adjudication.py \
  --case examples/synthetic/input/case.json \
  --task examples/synthetic/input/task.md \
  --ledger examples/synthetic/expected/adjudication-ledger.json \
  --result examples/synthetic/expected/result.json \
  --report examples/synthetic/expected/adjudication-report.json \
  --emit-result
```

`--emit-result` 只用于可复现实例：先从台账生成已知契约字段，再立即验证 result 并生成 report。实战不得用生成动作绕过实际契约校验；未知必需字段会被拒绝。

### 合法 early partial 正例

```bash
cd "$SKILL_DIR"
python3 scripts/check_adjudication.py \
  --case examples/synthetic/input/case.json \
  --task examples/synthetic/input/task.md \
  --ledger examples/synthetic/partial/adjudication-ledger.json \
  --result examples/synthetic/partial/result.json \
  --report examples/synthetic/partial/adjudication-report.json \
  --emit-result
```

### 必须非零的两个负例

```bash
cd "$SKILL_DIR"
! python3 scripts/check_adjudication.py \
  --case examples/synthetic/input/case.json \
  --task examples/synthetic/input/task.md \
  --ledger examples/synthetic/negative/skipped-id/adjudication-ledger.json \
  --result examples/synthetic/negative/skipped-id/result.json \
  --report examples/synthetic/negative/skipped-id/adjudication-report.json \
  --emit-result

! python3 scripts/check_adjudication.py \
  --case examples/synthetic/input/case.json \
  --task examples/synthetic/input/task.md \
  --ledger examples/synthetic/negative/invalid-mixed/adjudication-ledger.json \
  --result examples/synthetic/negative/invalid-mixed/result.json \
  --report examples/synthetic/negative/invalid-mixed/adjudication-report.json \
  --emit-result
```

检查器仅使用 Python 3.9+ 标准库。负例报告分别记录 skipped ID 和非法 mixed；不能用合法 partial 的语义为这两类错误放行。四组运行合计无网络请求，预算远低于64 requests/900秒。
