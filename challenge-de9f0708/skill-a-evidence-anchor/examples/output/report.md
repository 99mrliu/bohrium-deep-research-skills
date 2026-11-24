# 审查报告：MOCK-ANCHOR-001

> 合成示例输出，非正式测评结果。所有论文内容、机构、人物均为虚构。

## 锚定统计

| 指标 | 数值 |
| --- | --- |
| findings 总数 | 6 |
| 锚定通过 verified | 4（exact=2, normalized=2, cross_page=0） |
| absence 跳过 | 1 |
| 锚定失败自动降级 | 1 ['F-006'] |

## Findings

| id | type | severity | page | match_level | verdict_status |
| --- | --- | --- | --- | --- | --- |
| F-001 | fact_error | major | 3 | exact | 确认 |
| F-002 | fact_error | critical | 2 | normalized | 确认 |
| F-003 | fact_error | critical | 2 | exact | 确认 |
| F-004 | norm_issue | critical | — | skipped_absence_claim | 确认 |
| F-005 | insufficient_evidence | major | 3 | normalized | 确认 |
| F-006 | fact_error | minor | 2 | none | 待复核 |

## 详情

### F-001 [fact_error / major] verdict=确认

- 位置：mock_paper.txt 第 3 页 / References
- quote：'Nature. 1897;512(7515):45-52.'
- match_level：exact；found_on_pages=[3]
- evidence：本地规则 ref-metadata-consistency：Nature 第 512 卷对应 2014 年，年份 1897 与卷号 512 不可能同时成立；主题'quantum photosynthesis ... deep-sea bacteria'亦与期刊常规范围不符，疑似元数据编造或张冠李戴。
- suggestion：要求作者提供该文献的 DOI 或原文；若无法提供，删除或替换该引用。

### F-002 [fact_error / critical] verdict=确认

- 位置：mock_paper.txt 第 2 页 / Methods
- quote：'We enrolled 120 adult participants (aged 18 to 65 years)'
- match_level：normalized；found_on_pages=[2]
- evidence：本地规则 sample-size-consistency：Methods 声称入组 120 人，与 Results 表 1 的分析人群 n = 102 不一致（见 F-003），两处数字必有一处错误。
- suggestion：核对原始入组记录，统一 Methods、Results 与 Table 1 的样本量，并说明 18 例差异去向（剔除/脱落）。

### F-003 [fact_error / critical] verdict=确认

- 位置：mock_paper.txt 第 2 页 / Results
- quote：'analysis population (n = 102)'
- match_level：exact；found_on_pages=[2]
- evidence：本地规则 sample-size-consistency：Table 1 标注分析人群 n = 102，与 Methods 的 120 人（F-002）矛盾；正文又称 58 of 102 达到 EASI-75，分母口径同样为 102。
- suggestion：同 F-002：统一样本量并补充受试者流程图（screened/enrolled/analyzed）。

### F-004 [norm_issue / critical] verdict=确认

- 位置：mock_paper.txt 第 — 页 / 全文
- quote：（空：absence 类 finding）
- match_level：skipped_absence_claim；found_on_pages=[]
- evidence：本地规则 ethics-statement-required：研究涉及 human participants（Methods 2.1 明确成人受试者每日口服研究药物 12 周），但全文检索不到 ethics/institutional review board/IRB/consent/知情同意/伦理 等任何伦理审批或知情同意声明（absence 类 finding，quote 为空，锚定核验记 skipped_absence_claim，需人工复核全文确认）。
- suggestion：补充伦理委员会审批编号与知情同意声明；无法补充时应说明豁免依据。

### F-005 [insufficient_evidence / major] verdict=确认

- 位置：mock_paper.txt 第 3 页 / Conclusion
- quote：'ZX-101 definitively causes durable remission'
- match_level：normalized；found_on_pages=[3]
- evidence：本地规则 causal-claim-support：结论段使用 definitively causes 的强因果表述，但该句无任何引用或数据支撑，且与 Discussion 自述的 open-label 设计局限（limits the strength of any causal interpretation）直接冲突。
- suggestion：将因果表述降级为关联性表述（如 was associated with），或补充随机对照证据引用。

### F-006 [fact_error / minor] verdict=待复核

- 位置：mock_paper.txt 第 2 页 / Methods
- quote：'We enrolled 130 adult participants'
- match_level：none；found_on_pages=[]
- evidence：Agent 草稿：凭印象记录入组 130 人，需在锚定核验中确认。
- suggestion：核对入组人数。
- 复核理由：锚定核验未通过：quote 未逐字出现在声称位置（file=mock_paper.txt, page=2）
