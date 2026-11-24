# 导出格式签名表（sniff_parse.py 的判定依据）

格式判定以**内容签名优先、扩展名仅作提示**。任何判定都会写入 `ingest_ledger.json` 的
`format` 字段，供复核者重验。

| 格式标签 | 内容签名 | 常见来源 | 解析要点 |
|---|---|---|---|
| json-array | 首个非空白字符为 `[` 且整体 `json.loads` 成功 | Scopus/自研导出 | 元素必须是对象；非对象元素整体隔离（quarantine） |
| json-object | 首字符 `{` 且解析成功 | API 单条响应 | 自动下探 `records/references/results/items/data` 键 |
| json-lines | 整体解析失败但前 20 个非空行逐行 `json.loads` 成功 | 流水线中间产物 | 单行解析失败只隔离该行，不影响其他行 |
| csv / tsv | `csv.Sniffer` 在 4KB 样本内识别分隔符 | PubMed CSV、Excel 导出 | 首行必须为表头；字段数不齐的 ragged 行隔离 |
| ris | 存在 `^[A-Z][A-Z0-9]  - ` 形态的标签行 | WoS、EndNote、Zotero | 按 `TY`…`ER` 分组；无 `TI` 的块隔离并留摘录 |
| nbib | RIS 形态且含 `PMID- ` 行 | PubMed 纯文本导出 | 与 RIS 同管线解析 |
| plain-text | 以上皆不匹配 | 复制粘贴的题录列表 | 不猜测结构，整文件隔离并标注原因 |

## 字段归一映射

解析后统一为 `title / authors / year / journal / doi / abstract / pmid` 七个规范字段，
候选键见 `sniff_parse.py` 的 `NORM_KEYS`。归一后另派生：

- `doi_norm`：小写、去 `https://doi.org/` 前缀，用于跨库精确匹配提示；
- `field_status`：`ok / missing-title / missing-abstract / missing-doi`（可叠加），
  供下游纳排环节按边界情形处理，**缺失不等于排除**；
- `repair_notes`：如 `suspected-mojibake-in:title`，提示疑似乱码字段，只登记不改写原文。

## 已知局限

- 不解析 BibTeX（`.bib`）与 EndNote XML 的深层结构；遇到时按 plain-text 隔离并在
  报告注明，由操作者补转换后重跑；
- RIS 多行续行（同一标签跨行）未做拼接，摘要被截断的风险记入 `field_status` 之外的
  quarantine 摘录，复核者可对照原文；
- 乱码检测基于常见 UTF-8→Latin-1 误转模式（`Ã¶` 等），只提示、不自动修复。
