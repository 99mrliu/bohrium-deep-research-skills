# 论文逻辑与论证审查报告

共 4 条 finding（critical 1 / major 2 / minor 0 / suggestion 1；待复核 0）。

按修复优先级排序：

## 1. [CRITICAL] F02 — reasoning_chain

- 位置：S0014
- 原文：> These results prove that Compound Y cures root rot.
- 类型：insufficient_evidence / 状态：confirmed
- 依据：S0018（Methods）表明设计为单盆单剂量观察；S0014 用 prove/cures 的因果强表述，设计证据上限只到关联。
- 定级理由：主结论影响=单盆单剂量的相关结果无法支撑治愈这一因果强主张；可修正性=moderate_rewrite；可复现性影响=结论强度超出他人复现时可达证据
- 修改建议（downgrade_strength）：将 S0014 的 'prove ... cures' 降级为 'is associated with reduced root rot incidence in this single-pot setup'，并在 Discussion 增补替代解释段。

## 2. [MAJOR] F01 — stats_report

- 位置：S0009
- 原文：> The difference was statistically significant (p = 0.31).
- 类型：factual_error / 状态：confirmed
- 依据：S0011（Methods）定义显著性阈值为 p < 0.05；S0009 报告 p = 0.31 却声称 statistically significant，p 值与措辞直接冲突。
- 定级理由：主结论影响=直接否定主结论的统计依据；可修正性=easy_single_edit；可复现性影响=不影响实验可复现性，只影响表述
- 修改建议（rewrite）：将 S0009 改为 'The difference was not statistically significant (p = 0.31).'，或在重算后更正 p 值并同步摘要。

## 3. [MAJOR] F04 — citation_support

- 位置：S0005
- 原文：> Biochar improves water retention in sandy soils [1].
- 类型：insufficient_evidence / 状态：confirmed
- 依据：S0005 以单篇 [1] 支撑领域级背景命题；工作单核对发现该命题通常由综述支撑（待人工获取原文复核）。
- 定级理由：主结论影响=背景命题，不直接影响主结论；可修正性=easy_single_edit；可复现性影响=不影响
- 修改建议（add_citation）：在 S0005 的 [1] 之外补引一篇 2019 年后的沙土-生物炭综述支撑该背景命题，或将该句改写为不加引用的常识性表述。

## 4. [SUGGESTION] F03 — academic_norm

- 位置：S0021
- 原文：> Future work should address this.
- 类型：suggestion / 状态：confirmed
- 依据：S0021 的 future work 未指明对象、数量与检验方式，不可执行。
- 定级理由：主结论影响=无影响；可修正性=easy_single_edit；可复现性影响=无影响
- 修改建议（rewrite）：将 S0021 具体化为可检验的下一步，例如 'replicate across three soils and two doses'，指明对象与数量。

