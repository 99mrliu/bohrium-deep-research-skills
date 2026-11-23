# 保真判定规则（fidelity rules）

本文件定义机检项、判定阈值与处置矩阵，是 `scripts/quote_audit.py` 与
`scripts/num_drift.py` 的判定依据。两脚本实现本文件，判定冲突时以本文件为准。

## 1. 机检项定义

### 1.1 quote_audit.py（引文保真）

| 机检项 | 定义 | 判定 |
|---|---|---|
| verbatim_ok | quote 经归一化（见 normalization-spec.md）后为某页文本子串；或页内最佳模糊匹配 ratio ≥ 0.95 | 通过。若归一化改变了原始 quote，标注 `normalized: true` |
| near_match | 页内最佳模糊匹配 0.80 ≤ ratio < 0.95 | 警告：必须人工核对差异来源（断词、标点、个别字替换），未核对前不得作为 supported 的证据 |
| not_found | 所有页最佳匹配 ratio < 0.80 | ERROR：疑似编造或严重改写，禁止进入最终结果 |
| page_drift | quote 实际命中页（或印刷页）与标注 page 不符 | ERROR：修复页码或剔除该证据 |
| page_missing | 证据条目未标注 page | 警告：定位链不完整，补齐页码后方可交付 |
| page_invalid | 标注 page 无法解析为整数 | 警告：修复字段格式 |

阈值常量：`VERBATIM_THRESHOLD = 0.95`，`NEAR_THRESHOLD = 0.80`
（与 quote_audit.py 源码保持一致）。

### 1.2 num_drift.py（数值漂移）

| 机检项 | 定义 | 判定 |
|---|---|---|
| ok | 论断中的每个数值在所引 quote 中存在等价值（等价规则见 normalization-spec.md §3） | 通过 |
| value_mismatch | 论断数值与 quote 中最近数值接近（相对差 ≤ 5%）但不相等 | ERROR：疑似四舍五入改写（如 78% → 78.2%），论断数值必须改回原文值 |
| missing_in_quote | 论断数值未出现在所引 quote 中，且与 quote 内任何数值都不接近 | ERROR：疑似外推或来源不明；该数值不得进入结论，论断相应降级 |
| no_evidence | 论断含数值但没有任何 evidence quote | 警告：数值无法机检，须先补证据 |

## 2. 处置矩阵（修复 / 降级 / 剔除）

| 机检结果 | 首选处置 | 次选处置 | 禁止行为 |
|---|---|---|---|
| verbatim_ok | 直接采用 | — | — |
| near_match | 人工核对后按原文修正 quote 使成为 verbatim_ok | 降级：该证据仅支撑 partially_supported，并在 uncertainty 中说明差异 | 禁止不改 quote 直接当 supported 证据 |
| not_found | 回原文重新检索正确 quote；找不到则剔除该证据 | 剔除并将对应论断降级为 insufficient_evidence | 禁止保留、禁止"润色"原文冒充 verbatim |
| page_drift | 以实际命中页更正 page（并写 change_records） | 若实际页与论断语境不符，剔除 | 禁止沿用错误页码 |
| value_mismatch | 论断数值改回原文值 | 删除该数值表述，降级论断 | 禁止保留改写后的数值 |
| missing_in_quote | 为数值另找真实出处并换 quote | 删除该数值或判 insufficient_evidence | 禁止把无出处的数值写进结论 |

所有修复、降级、剔除都必须写入 result.json 的 `change_records`：
何时、哪条证据、原值、新值、原因（机检项名称）。

## 3. 与支持度判定的衔接（简明规则）

保真门只管"quote 是否真实、定位是否正确"，支持度判定在其之后：

- supported：verbatim_ok 证据与论断在比较对象、方向、条件、数值上完全一致。
- partially_supported：论断可拆子判断中部分有 verbatim_ok 证据，或证据只覆盖
  论断的条件子集（如只报了转化率未报选择性）。
- contradicted：存在 verbatim_ok 证据与论断在同一条件下直接冲突（含数值冲突，
  如论断 90% 而原文 54%）。
- insufficient_evidence：未找到证据、证据未通过保真门且无法修复、或原文明确
  "未考察/未报告"（未报告 ≠ 反驳）。
- 主题相关 ≠ 支持；unsupported extrapolation 是 insufficient_evidence，
  不是 contradicted。
- 冲突来源：并列双方原话与定位，给出 qualified verdict，不单方取舍。

## 4. 复合论断拆解（简明规则）

- 按"事实 / 比较 / 因果 / 范围"四类拆子判断，每类至少一条证据，不遗漏、不重复。
- 保留比较词（较/高于/显著）、否定词（未/无/不）、限定条件（温度、压力、样本）。
- 每条子判断独立走保真门；任一子判断证据 not_found 且无法修复时，
  整条论断至多为 partially_supported。
