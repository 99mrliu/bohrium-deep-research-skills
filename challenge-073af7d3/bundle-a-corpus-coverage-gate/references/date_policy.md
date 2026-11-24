# 日期策略（date policy）—— print / online / preprint 的取舍与溯源

语料中同一篇文献常携带多个年份：印刷年（year_print）、在线首发年（year_online）、
预印本年（year_preprint），或仅有一个无来源的通用年份（year）。趋势分析对年份极其敏感——
把"在线 2023 / 印刷 2024"的论文错放一年，足以伪造或抹平一个趋势拐点。因此本技能要求：
**每条 canon 记录的 year 必须记录其来源字段（date_provenance），冲突取舍必须遵循显式策略。**

## 可选策略

| 策略 | 优先序 | 适用场景 |
|---|---|---|
| `print`（默认） | year_print → year_online → year_preprint → year | 与正式出版记录对齐；计量学惯例 |
| `online` | year_online → year_print → year_preprint → year | 关注成果首次进入正式出版系统的时点 |
| `preprint` | year_preprint → year_online → year_print → year | 关注思想最早公开时点；前沿感知最快 |
| `earliest` | 取所有可用年份字段的最小值 | 最保守的"最早公开"口径；溯源附加 `(earliest)` |

策略选择规则：`/input/task.md` 有指定时从其指定；否则用默认 `print`。
所选策略必须写入 `ingest_report.json.date_policy` 并回链进 `result.json.provenance`。

## 冲突解决

- 策略按优先序取**第一个可用**字段；缺失字段自动跳过，不视为错误。
- 同一记录 print 与 online 不一致时，**不仲裁谁"正确"**，只按策略取舍；未选中的字段仍保留在
  canon 记录中（year_print/year_online/year_preprint 三列并存），供敏感性分析复用。
- 三个分源字段全缺时退到通用 `year`；通用年份是自由文本正则抽取时，溯源记为
  `year:freetext_regex`，可信度最低，应在 uncertainty 中声明。
- 全部字段缺失：`year = null`，`date_provenance = "missing"`；该记录计入
  `records_without_year` 与 `year_missing_rate`。缺失率 >0.2 时门禁给 warn。

## 溯源记录格式

`date_provenance` 取值枚举：

| 取值 | 含义 |
|---|---|
| `year_print` / `year_online` / `year_preprint` | 来自对应分源字段 |
| `year` | 来自记录中的单一通用年份字段 |
| `<field>(earliest)` | earliest 策略下多字段取最小值 |
| `year:freetext_regex` | txt/md 兜底中正则抽取 |
| `missing` | 无任何年份信息 |

## 对下游分析的约束

- 趋势表（第 3 步）必须声明所用策略；换策略重跑是对结论稳健性的廉价检验。
- 右删失评估基于选定策略后的 year；若末年大量记录仅有 preprint 年份，
  应怀疑出版延迟造成的假删失，并在 uncertainty 中说明。
