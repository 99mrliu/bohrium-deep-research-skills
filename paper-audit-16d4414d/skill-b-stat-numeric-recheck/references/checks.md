# C1–C6 确定性检查规则文档

每条规则：判定式、容差、误报护栏、确认要点。所有规则的产物是**候选**；升级为 finding 前必须读原句确认。

## C1 pvalue_wording — p 值与显著性措辞冲突

- 判定：句内同时出现 p 值（`p <|=|> v`）与显著性措辞。按 0.05 阈值：`v<0.05`（op 为 `<`/`=`/`≤`）判"显著"，与否定表述（not/no/non-significant/failed to reach）冲突时报候选；`v≥0.05` 或 op 为 `>` 判"不显著"，与肯定 significant 表述冲突时报候选。
- 护栏：句内含 threshold/considered/defined/cutoff/criterion/was set at 时跳过——方法学显著性阈值定义不是结果陈述。
- 确认要点：阈值是否真是 0.05（领域可能用 0.01）；措辞是否指向该 p 值而非另一比较。

## C2 percent_fraction — 百分比与分子分母不符

- 判定：同句百分比 `p%` 与分数 `(a/b)`，`|100a/b − p| > 1.0` 个百分点时报候选。
- 护栏：容差 ±1.0pp 吸收四舍五入；拼写数字（"ninety percent"）不解析，不会误报。
- 确认要点：百分比与分数是否指同一总体（可能一个是"占处理组"、一个是"占全体"）。

## C3 ci_* — 置信区间连贯性

- C3_ci_inverted：下限>上限。C3_ci_point_outside：点估计不在 [下限, 上限] 内。C3_ci_asymmetric：两侧宽度差 >25% 半宽（minor）。
- 护栏：偏态数据/变换尺度 CI 可 legitimately 不对称，故不对称只标 minor 且提示确认。
- 确认要点：括号内是否真是 CI（可能是 SD 或范围）；点估计与 CI 是否同一量。

## C4 impossible_* — 数学不可能值

- p 值落在 [0,1] 之外（critical，无歧义）；百分比 >100% 且句内无 increase/growth/rise/fold/baseline/relative 语境（major）；mean±SD 中 SD<0（major）。
- 护栏：相对增长率可合法 >100%，有语境词时不报。
- 确认要点：基本无歧义，确认排版解析无误即可（如 "1.20" 是否本是 ".120"）。

## C5 crosssection_value — 跨章节同单位取值冲突

- 判定：同一单位（cm、mg、h 等）的取值集合在 abstract 与 results 之间不一致（对称差非空）。
- 护栏：只比对 abstract↔results；产物标记 `needs_review`，详情明确提示"逐句核对是否同一量"。
- 确认要点：这是六条规则里误报率最高的——两组不同测量常用同一单位。确认"同一量、不同值"才升级；确认是不同量则在报告写明排除理由。

## C6 direction_conflict — 效应方向与数值顺序相反

- 判定：句内有 `a vs b` 数对且有方向词。higher/greater/increased 类 + `a<b` → 冲突；lower/reduced/decreased 类 + `a>b` → 冲突。
- 确认要点：数对顺序是否与方向词主语一致（"A higher than B (a vs b)" 与 "B (b vs a) was lower" 同义）；百分比差与比值混用时人工判断。

## 严重度建议映射

| 规则 | hint | 说明 |
|-|-|-|
| C4 p 值越界 | critical | 数学不可能，直接动摇所涉结论 |
| C1/C2/C3 点估计外/C6 | major | 影响读者对结果的正确理解，需改数或改措辞 |
| C3 不对称 | minor | 可能是合法偏态，确认后再定 |
| C5 | needs_review | 未经语义确认不定级 |

最终定级必须写三维依据：是否影响主结论、是否可修正（改一处即可 vs 需重算重采）、是否影响可复现性。禁止一律标"中"。
