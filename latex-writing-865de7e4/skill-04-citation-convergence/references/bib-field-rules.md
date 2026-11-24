# bib 字段规则（citeaudit 静态审计依据）

本文件给出 citeaudit.py 内置的各 entrytype 最小字段规则及常见样式要求。
脚本据此**只提示建议**：缺必需字段记为「缺必需字段」，缺建议字段记为「缺建议字段」，
是否补充由 Agent 判断（例如某些条目确实没有卷期页，不能编造）。

## 各 entrytype 必需 / 建议字段

「必需」列中 `author/editor` 表示二者有其一即可。

| entrytype | 必需字段 | 建议字段 |
| --- | --- | --- |
| article | author, title, journal, year | volume, number, pages, doi |
| book | author/editor, title, publisher, year | edition, isbn, doi |
| booklet | title | author, howpublished, year |
| inbook | author/editor, title, chapter/pages, publisher, year | edition |
| incollection | author, title, booktitle, publisher, year | editor, pages, doi |
| inproceedings / conference | author, title, booktitle, year | editor, pages, publisher, doi |
| manual | title | author, organization, year |
| mastersthesis / phdthesis | author, title, school, year | type, address |
| misc | （无严格必需） | author, title, year, howpublished |
| online | title | author, url, urldate, year |
| proceedings | title, year | editor, publisher, volume |
| techreport | author, title, institution, year | number, type, doi |
| unpublished | author, title, note | year |

未知 entrytype（如样式自定义类型）跳过字段检查并在报告中标注。

## 常见样式要求（提示，不强制）

- **bibtex（plain/unsrt/alpha、natbib）**：使用 `year`；`pages` 用双连字符
  `123--145`；多作者用 ` and ` 连接；标题中的专有名词用大括号保护
  （如 `{BERT}`），否则部分样式会小写化。
- **biblatex（biber）**：推荐 `date`（或 `year`）、`journaltitle`（biblatex）
  与 `url`/`urldate`（online 条目）；`edition` 用整数。
- **GB/T 7714（gbt7714 宏包）**：中文文献常需 `language={zh}`；会议论文用
  `inproceedings` 并提供 `address`/`publisher` 更稳；预印本可用
  `misc` + `note = {arXiv: xxxx.xxxxx}`。
- **IEEEtran**：`article` 必须有 `journal`、`volume`/`number`、`pages`、`year`；
  会议论文用 `inproceedings` 且 `booktitle` 写会议全称。
- 冗余键（同一文献两个键）会让同一文献在参考文献表出现两次，静态审计的
  「未被引用条目」与「重复引用」两节可辅助识别，但合并与否由 Agent 决定。

## 处置原则

1. 缺必需字段：优先从原文/PDF 核实后补全；无法核实的保持原样并在交付说明中
   标注，**不得编造字段值**。
2. 缺建议字段：仅在任务或样式明确要求时补充。
3. 未被引用的条目：可能是漏引（正文应补 \cite）也可能是备查条目（应保留），
   由 Agent 语义判断，脚本绝不自动删除。
