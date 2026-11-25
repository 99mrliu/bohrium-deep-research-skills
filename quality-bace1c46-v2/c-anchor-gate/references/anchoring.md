# 锚定与门控参考（references/anchoring.md）

## 1. 锚点语法

锚点形如 `p<页>.¶<段>`，例如 `p2.¶3` 表示第 2 页第 3 段。

- **页码跟随抽取层，而非印刷页码（folio）**。即：`pdftotext` 输出的第 N 个换页符分隔块就是第 N 页，txt 文件同理。印刷页眉/页脚里的页码不参与编号。这样做是因为门控只能对抽取文本工作，锚点必须与机器可见的文本一一对应；审稿人按抽取层页码 Ctrl-F 一定能命中。
- 段号：页内按**一个或多个连续空行**切分后的顺序号，从 1 开始。空段（仅空白）不计入。
- 页号、段号均为 1-based 整数。锚点大小写敏感，规范形式为小写 `p` 与 `¶`；门控在解析定位符时容忍 `P2.¶3`、`p2.para3`、`page 2 para 3` 等写法并归一到规范形式，无法解析的定位符按"未命中"流程处理（进入全篇搜索，可能判 repaired_locator 或 abstain_unverifiable）。

## 2. 归一化规则（quote 与段落文本使用同一套）

按顺序执行：

1. **NFKC**：`unicodedata.normalize("NFKC", s)`，折叠全角/半角、兼容字符、各种 Unicode 引号与破折号的兼容形式。
2. **断行连字符重接**：把 `-\n` 及其间的空白去掉（`hyph-\nen` → `hyphen`），消除 PDF 抽取的行尾断词。先做这个再折叠空白。
3. **空白折叠**：所有连续空白（含换行、制表）折叠为单个空格，首尾去空白。
4. **casefold**：`str.casefold()`，大小写不敏感比较。

归一化只用于**匹配**；写入 result.json / evidence_table.md 的 quote 保留模型提交的原始形态（便于人读），定位符写规范形式。

## 3. 匹配算法（gate.py 对每条判断行）

输入行：`{doc_id, claim_id, judgment, quote, locator, rationale}`。

1. 若 `doc_id` 在 index 中标记 `no_text_layer` 或 `missing` → `abstain_no_text_layer`。
2. 归一化 quote。空 quote → `abstain_unverifiable`（reason: empty quote）。
3. 解析 locator 为 (page, para)。若可解析且该段存在：
   a. quote 是该段归一化文本的子串 → **verified**。
   b. 否则取该段与下一段的拼接文本（中间补一个空格再归一化），quote 是其子串 → **verified_span**（final_locator 记为 `pX.¶Y-¶Y+1`）。
4. 若 locator 不可解析或 (3) 未命中：对**同篇文档**全部段落做子串搜索：
   - 在某一段命中 → **repaired_locator**，final_locator 为实际命中段锚点；若该段与声称页不同，change_records 记录 `{"type":"locator_repair","old_locator","new_locator","claim_id","doc_id"}`。
   - 在相邻两段拼接命中 → **verified_span**，同样记录 locator repair（old→span）。
   - 多处命中时取第一个，并在该条记录的 note 中列出全部命中锚点。
5. 全篇无命中 → **abstain_unverifiable**，reason 说明"quote 在文档抽取文本中无子串命中，疑似转述或杜撰"。**不放行**。

### 五种裁决

| verdict | 含义 | 进入 evidence_records? |
|---|---|---|
| verified | 逐字命中声称段落 | 是 |
| verified_span | 逐字命中相邻两段拼接 | 是 |
| repaired_locator | 摘录真实但定位标错，已修复并留痕 | 是（用修复后定位） |
| abstain_unverifiable | 摘录无处可寻（转述/杜撰/空 quote/图表） | 否（进 abstentions） |
| abstain_no_text_layer | 文档无可用文本层 | 否（进 abstentions） |

## 4. 弃权规则

- 宁可弃权，不可放行无法验证的摘录。弃权不是失败：`status=partial` 是诚实结果。
- 图表、公式、扫描图像中的内容：摘录无法被子串匹配验证时一律 `abstain_unverifiable` 并在 reason 注明来源类型。
- 模型对自己的判断没有把握时，应主动把 judgment 写成 `uncertain` 并给出最窄的可验证摘录；门控只关心摘录真实性，不评价判断内容对错。

## 5. 为什么逐字摘录门控优于转述

- **可回溯性**：审稿人（或下游机器）必须能 Ctrl-F 回到原文。转述打破了字符串层面的可检索性，核验成本从 O(一次搜索) 变成 O(读整节)。
- **可机械验证**：子串匹配是确定性的、零模型成本的判定；转述是否"忠实"需要再一次模型判断，引入新的幻觉面。
- **幻觉拦截**：编造内容在归一化子串匹配下几乎必然无命中，会被拦在 abstain_unverifiable；转述则给编造内容提供了伪装通道。
- **定位错误的可修复性**：逐字摘录即使 locator 标错，仍能通过全篇搜索修复（repaired_locator）并留痕；转述无法区分"定位错"与"内容假"。
