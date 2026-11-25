# 判据矩阵对齐手册（criteria-matrix-aligner）

## 判据注册表格式（extract 产物）

`criteria.json` 形如：

```json
{
  "case_id": "...",
  "criteria": [
    {"criterion_id": "c1", "text": "<逐字判据原文>", "source": "annotation_standard.inclusion[0]", "derived": false}
  ],
  "record_ids": ["..."],
  "notes": ["..."]
}
```

- `text` 一律逐字取自案例自带标注标准，脚本按序在顶层寻找 `annotation_standard`、`screening_criteria`、`criteria`、`inclusion_criteria`、`inclusion`、`exclusion_criteria`、`exclusion`；嵌套结构（如 `{"inclusion": [...], "exclusion": [...]}`、字典型判据 `{"text": ...}`）会展平，`source` 记录完整键路径。
- case.json 无标注标准时，退而取 task.md 中"标准/判据/criteria/inclusion/exclusion/纳入/排除"标题下的条目行（`source` 形如 `task.md:L12`）。
- 再不可得时，从 `research_question` / `retrieval_scope` 派生判据，`derived:true` 并写入 notes 与结果 `status.limits`——派生判据不冒充标注标准。

## 判定语义（verdict）

- `met`：记录自身证据明确满足判据；`unmet`：明确违反；`unknown`：证据缺失（如无摘要）或表述歧义。
- **unknown → pending，绝不静默排除。** 排除的唯一合法理由是至少一条判据 `unmet`。
- 每条非 `unknown` 判定必须附 `quote`：该记录标题或摘要的**逐字子串**（区分大小写、不得改写、不得拼接省略号）。`unknown` 的 `quote` 必须为 null。validate 逐格校验，编造引用必 FAIL。

## 边界约定

- **判据冲突**：标注标准内部若互相冲突（如同时纳入与排除预印本），两条均保留进注册表、各自判定；矩阵自然呈现分歧，脚本不仲裁、不合并。
- **夹具标注**：`fixture_note` 等字段是平台注入的 provenance（重复导出、冲突意见），只可用于说明记录间关系，**不得**作为 met/unmet 的判定来源，也不得作为预期答案对齐。
- **元数据缺失**：缺摘要的记录全部判据 `unknown` → pending，并在覆盖说明中点名；禁止根据标题猜测补全。
- **重复导出**：重复记录与同判据下的其他记录一视同仁地逐格判定；是否因"经同行评议"类判据而不满足，由判据原文决定，不由夹具标签决定。

## 批量矩阵调用的措辞（Agent 唯一一次模型调用）

一次性请求模型对全部记录 × 全部判据输出矩阵，提示要点：

1. 粘贴判据注册表（criterion_id + 逐字 text）与全部记录的 record_id、标题、摘要原文；
2. 要求逐格输出 `{"record_id","criterion_id","verdict","quote"}`，quote 必须是**该条记录**标题或摘要的连续子串，判不了填 `unknown` 且 quote 为 null；
3. 明令禁止引用其他记录的证据、禁止转述改写、禁止使用 fixture_note 作判定依据；
4. 要求输出纯 JSON（`{"cells":[...]}`），全量 4×N 格一次给齐，缺格由脚本按 unknown 补齐并计入 partial。

## 决定规则与排序（脚本确定性执行）

- 标签：全 `met` → keep/direct；≥1 `unmet` → exclude/none；其余 → pending/indirect。
- 分值：`round(clamp(100×met比例 − 50×unmet比例, 0, 100))`；全 unknown 为 0。
- 排序：层级 keep<pending<exclude → 分值降序 → record_id；同 (label, score) 共享名次并带 `tie_group`。

## 面向一致性的判定准则（agreement-oriented）

- 判定的参照系是**判据原文**而非模型常识：判据未要求的维度（如样本量大小、期刊声望）不得引入。
- 逐字引用先行：先找得到支持 `met`/`unmet` 的原文片段再定 verdict；找不到支持排除的原文，就只能是 `unknown`，不得"感觉不符合"而排除。
- 完成矩阵后自查：每条 `unmet` 都能指认其违反了哪一条判据原文的哪个分句；每条 `keep` 的全部判据均有原文支撑——这与 validate 的重算逻辑一致，可提前避免返工。
