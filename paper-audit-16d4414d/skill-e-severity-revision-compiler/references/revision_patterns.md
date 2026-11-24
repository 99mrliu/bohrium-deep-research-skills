# 可执行修改建议写法（revision patterns）

每条 revision 必须回答三个问题：改哪一句（sentence id）、做什么操作（revision_op）、改成什么样（具体文本或具体补什么）。空话词表见引擎 VAGUE_PATTERNS，命中即 lint 拒绝。

## 七种操作类型与模板

### rewrite（改写既有句）
模板：将 {sid} 的 '{原片段}' 改为 '{新片段}'，{原因半句}。
例：将 S0009 的 'statistically significant (p = 0.31)' 改为 'not statistically significant (p = 0.31)'，使措辞与 p 值一致。

### downgrade_strength（降结论强度）
模板：将 {sid} 的 {强表述} 降级为 {与证据上限相称的表述}；同步检查摘要/结论中同主张句。
例：将 S0014 的 'prove that X cures Y' 降级为 'is associated with lower Y incidence in this setup'；同步检查 S0003（摘要同主张句）。

### add_citation（补/换引用）
模板：在 {sid} 补引 {具体文献类型与范围}；或将现引 {n} 替换为 {更对口来源}。
例：在 S0005 补引一篇 2019 年后的沙土-生物炭综述替代单篇 [1]，使领域级背景命题由综述支撑。

### add_data（补数据/分析）
模板：为支撑 {sid} 的主张，需补 {具体数据/分析}，放在 {章节}。
例：为支撑 S0022 的剂量主张，需在 Results 补三个剂量组的均值±SD 与趋势检验。

### insert（插入新句/段）
模板：在 {位置} 插入：'{建议文本}'，用于 {目的}。
例：在 Discussion 末段插入局限性句：'single-soil, single-dose design limits generalization'，回应 S0014 的外推。

### delete（删除）
模板：删除 {sid} 的 {片段}，因为 {理由}；检查 {关联处} 是否需要同步。
例：删除文献表第 [4] 条（正文从未引用），或反之在正文需要处补引。

### recheck（需重算/复核后才能定稿）
模板：{sid} 的 {数值/统计量} 需按 {方法} 重算；重算前该句结论标待复核。
例：S0009 的 p 值需按 Methods 所述检验重算；重算前主结论标待复核。

## 六类检查项的建议侧重

| category | 建议重心 |
|-|-|
| fact_check | rewrite/recheck：改错值或重算 |
| citation_support | add_citation/delete/downgrade_strength：让引用与命题相称 |
| method_design | add_data/insert：补设计要素或如实承认局限 |
| stats_report | rewrite/recheck：数值、措辞、阈值三者一致 |
| reasoning_chain | downgrade_strength/insert：降强度、补替代解释讨论 |
| academic_norm | rewrite/delete：规范局部表述 |

## 反模式（lint 必拦，人工也应拒收）

- "建议补充论证 / 建议加强逻辑 / 进一步完善"——没有对象、没有操作、没有目标文本；
- 建议长度 <30 字——几乎不可能说清三要素；
- 通篇只有 downgrade_strength 或只有 rewrite——操作类型应与问题类型匹配；
- revision 与 finding 不同句——建议改 A 句而问题在 B 句，是定位漂移。
