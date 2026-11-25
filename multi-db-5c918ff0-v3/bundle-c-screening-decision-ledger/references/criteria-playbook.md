# 资格标准编译手册（criteria-playbook.md）

本手册规范"模型步骤 3"：如何把 task.md 的任务文本编译成 `criteria.json`，
以及"模型步骤 5/7"的判定证据规则。

## 1. 从任务文本到标准：框架

先用 PICO/SPIDER 把研究问题拆开，再决定每条标准的归属：

- **P**opulation（人群）：如"≥18 岁成人慢性失眠"。
- **I**ntervention / **E**xposure（干预/暴露）：如"合成肽 NX-3"。
- **C**omparator（对照）：如"安慰剂"。
- **O**utcome（结局）：如"入睡潜伏期 sleep latency"。
- **S**tudy design（研究设计，SPIDER 中为 Study type）：如"仅 RCT"。
- 其他维度：发表年份、文献类型、语言、场景（SPIDER 的 Setting）、
  研究现象（PI 定性场景）。

拆出的每个可判维度 → 一条标准。

## 2. 纳入与排除必须分开登记

- `kind: "inclusion"`：记录必须满足才可纳入（如"RCT"、"成人"、"NX-3 vs
  安慰剂"、"结局含 sleep latency"）。判 exclude 时引用 inclusion 标准 id 是
  合法的——语义是"未满足该纳入标准"。
- `kind: "exclusion"`：命中即排除（如"年份超出 2015–2025"、"综述/社论"）。
- 同一句话若同时含纳入面与排除面，拆成两条，各带自己的 `source_quote`。

## 3. 机器可判 vs 判定标准

标准若能从结构化字段确定性求值，给 `machine` 块，由脚本 `prescreen` 落账：

| machine.type | 字段 | 参数 | 触发 |
|---|---|---|---|
| `year_range` | `year` | `min`/`max`（含端点） | 年份越界 → exclude |
| `document_type` | `doc_type` | `exclude_types` 列表 | 类型（小写）含任一条目 → exclude |

纪律：

- 仅 `kind: "exclusion"` 且带 `machine` 块的标准会被脚本预判；纳入标准
  一律由模型判定。
- **字段缺失不自动排除**：记录无年份/无类型字段时该标准不适用，记录保持
  pending 交模型判定。
- 语义判断（"是否真 RCT"、"人群是否成人"、"是否有安慰剂组"）**不得**伪装成
  机器标准——Crossref 的 `type: journal-article` 不能区分 RCT。

## 4. 每条标准必须引用 task.md 原文

- `source_quote` 必须是 task.md 的**原文片段**（逐字子串），这是标准可追溯性
  的唯一锚点。
- **最常见失败模式：臆造标准**。模型不得加入 task.md 中没有的标准（例如自行
  追加"排除非英文文献""要求样本量 ≥30"）。若任务文本确实模糊，可在
  `definition` 中写明解释，但 `source_quote` 仍须锚定原文，且整个
  criteria.json 顶层标 `"derived_needs_confirmation": true`。
- task.md **没有**给出明确标准时：不要编造。编译你能找到的最小集合（可能
  只来自 research_question），标 `derived_needs_confirmation: true`，让
  finalize 以 partial 如实上报并要求人工二次确认登记。

## 5. 判定证据规则（模型步骤 5/7）

1. **逐字引用规则**：`evidence_quote` 必须是该记录 `normalized.jsonl` 中
   `title` 或 `abstract` 字段的**逐珠子串**（脚本核验；记录文本已经过 NFC、
   去 HTML、折叠空白——引用前以 normalized.jsonl 为准，不要凭原始材料记忆
   抄写）。引用要短而准：一个能支撑判定的分句即可。
2. **include/exclude 必须引用 ≥1 个 criterion id**；borderline 可只标相关
   标准。
3. **title-only 降级**：记录 `has_abstract=false` 时，判定只能基于标题，
   judgment 标 `"basis": "title-only"`；脚本也会在 basis 缺省时按记录自动
   标注。此类判定在报告的局限节列出。
4. **insufficient_evidence**：连标题都不足以支撑任何倾向时，判
   `"decision": "borderline"` 且 `"evidence_status": "insufficient_evidence"`
   （无需 evidence_quote）。`insufficient_evidence` 用在 include/exclude 上
   会被 validate-judgments 拒绝——没有逐字证据就不许硬判。
5. **拿不准就进边界队列**：borderline 不是失败，而是纪律。误纳/误排的代价
   高于一次集中裁定。边界裁定（步骤 7）用 `borderline_decisions.json`
   一次性批量完成，每条给 `decision`（include|exclude）、`criterion_ids`、
   `evidence_quote`（同样逐字核验）与 `rationale`。
6. **rank**：只对倾向纳入的记录给整数 rank（candidate_set 按 rank 排序，
   缺 rank 按稳定序）。
