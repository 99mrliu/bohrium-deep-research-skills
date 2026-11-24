# 引用核查协议

## 两层模型与诚实规则

| 层 | 内容 | 定案权 |
|-|-|-|
| 文本内 | cited-not-listed、listed-not-cited、断号、重复条目 | 引擎候选 + 读原句确认即可定案 |
| 文本外 | 被引文献是否支持所引句子 | 只有读到被引原文（至少标题+摘要）才能定案；否则待复核 |

诚实规则（引擎写入 worksheet.json 顶部，不可协商）：
- 无法获取被引原文时，引用支持度一律 `待复核`，写明"需要人工获取原文"；
- 禁止凭文献标题语气猜测"不支持"——标题相像不等于支持，标题不像也不等于不支持；
- 只允许对文本内确定性缺陷直接定案。

## 引用功能分类（worksheet 的 function_guess）

| 类别 | 线索词 | 核查重点 |
|-|-|-|
| support | showed/demonstrated/found/reported/established/表明/证实 | 所引句命题与被引文献结论是否同向同强度 |
| contrast | however/in contrast/unlike/相反 | 是否准确转述了对立结果，有无断章取义 |
| method_source | using/following/as described/依据 | 方法是否真源自该文献，版本/参数是否一致 |
| background | widely/known/reviewed/已知 | 是否为公知常识；常识性命题配单篇引用通常无碍 |
| mention | 无线索 | 低优先级，抽查即可 |

## 强主张标记（strong_claim_with_citation）

句内出现 cures/eliminates/proves/demonstrates/establishes/causes/leads to/治愈/根除/证明了 类强动词且带引用。这类句子是"引用不支持观点"的高发区：论文正文把一个只能支持相关或初步证据的引用，用来支撑决定性表述。核查优先级最高。

## 外部取证流程（平台工具可用时）

1. 从 reference_entry 提取标题关键词与年份；
2. 用可用的检索/浏览工具查该文献的标题与摘要；
3. 比对三点：命题主体是否相同、方向是否相同、强度是否相同；
4. 三同 → 通过；任一不同 → 定案 `citation_support`，evidence 写明被引文献实际内容与你读取的来源；
5. 检索不到或只能看到标题 → `待复核`。

## 严重度映射

| 情形 | 严重度 |
|-|-|
| 关键结论的引用不支持该结论 | critical/major（视是否动摇主结论） |
| 引而未列（读者无法追溯证据） | major |
| 强主张引用待复核 | 标待复核，不定级 |
| 列而未引、断号、重复条目 | minor |
| 混用引用格式 | minor / norm_issue |

定级写三维依据：是否影响主结论、是否可修正（删/补一条引用 vs 需要重做论证）、是否影响可复现性（证据链断裂即影响）。
