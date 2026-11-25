# 快照字段结构参考（Crossref / EuropePMC）

本文件描述两类离线 API 响应快照的 JSON 结构，以及材料包中常见的不一致模式。
所有取值必须**防御式**进行（逐层 `isinstance` 检查，缺失即跳过，绝不抛异常）。

## 1. Crossref works 快照

典型形状（单条 work 或 work-list）：

```json
{
  "status": "ok",
  "message-type": "work" | "work-list",
  "message": {
    "DOI": "10.xxxx/yyyy",
    "type": "journal-article",
    "title": ["..."],
    "container-title": ["..."],
    "author": [{"family": "...", "given": "..."}],
    "issued": {"date-parts": [[2023, 4, 11]]},
    "items": [ ... ]              // 仅 work-list 时存在
  }
}
```

字段提取规则：

| 目标字段 | 路径 | 说明 |
|---|---|---|
| 标题 | `message.title[0]` | 数组，取第一个非空串 |
| 期刊/容器 | `message["container-title"][0]` | 数组 |
| 首作者姓 | `message.author[0].family` | `given` 为名 |
| 年份 | `message.issued["date-parts"][0][0]` | 三级嵌套，任一层缺失则年份为空 |
| DOI | `message.DOI` | 大小写不敏感，比对时 casefold |
| 类型 | `message.type` | 如 journal-article / posted-content(preprint) |

识别规则：顶层存在 `message`，且其中含 `items` 或 `title`/`DOI`/
`container-title` 之一 → crossref 风味。有 `items` 按列表提取，否则把
`message` 本身当单条 work。

## 2. EuropePMC 快照

典型形状：

```json
{
  "hitCount": 1,
  "resultList": {
    "result": [
      {
        "title": "...",
        "authorString": "Zhang W, Okoro A",
        "pubYear": "2023",
        "doi": "10.xxxx/yyyy",
        "pubType": "journal-article",
        "journalInfo": {"journal": {"title": "..."}}
      }
    ]
  }
}
```

字段提取规则：

| 目标字段 | 路径 | 说明 |
|---|---|---|
| 标题 | `resultList.result[].title` | 单串 |
| 首作者姓 | `resultList.result[].authorString` | 逗号/` and ` 切分后取第一段的第一个词 |
| 年份 | `resultList.result[].pubYear` | 字符串 |
| 期刊 | `resultList.result[].journalInfo.journal.title` | 深嵌套 |
| DOI | `resultList.result[].doi` | 可能缺失 |
| 类型 | `resultList.result[].pubType` | 可能缺失 |

识别规则：顶层存在 `resultList`（dict）→ europepmc 风味。两者都不是 →
generic（不参与交叉核对）。

## 3. 常见不一致模式

1. **改名下载**：文件名被改成 `paper (1).pdf`、乱码或 DOI 形式，与内容无关。
   → 文件名不可信，必须以正文文本层与快照元数据核对为准。
2. **预印本 vs 正式发表版本对**：同一研究两个 DOI（或同 DOI 不同年份/类型），
   快照是正式版、正文是预印本（或反之）。→ 年份/类型/期刊字段不一致，
   判 mismatch，记 version_conflicts，由模型做语义归因（措辞保持推测）。
3. **重复增量导入**：同一文献被多次入库，快照列表里出现两条归一化标题相同
   的记录（可能 DOI 不同）。→ 记入 duplicates，不合并、不删除。
4. **缺失 DOI**：快照记录无 DOI（EuropePMC 常见）或正文未印 DOI。
   → 该字段不参与核对；仅靠标题+作者+年份核对的结论置信度更低，
   可在 note 中说明。
5. **年份语义混杂**：issued（在线发表）与 print 年份不同；快照年份与正文
   版权年差 1。→ 年份不匹配即如实报 mismatch，不做"四舍五入"式原谅。
6. **DOI 内嵌年份**：`10.5555/xxx.2021` 这类 DOI 会让"年份出现在正文中"
   的检查假命中。→ 年份检索前必须先剥离 DOI/URL（crosscheck.py 已实现）。
7. **无文本层扫描件**：pdftotext 输出为空。→ unverifiable，不是 mismatch。
8. **仅摘要条目 / 非拉丁文字标题**：正文层缺乏可比对锚点或归一化失真。
   → 弃权（abstain → unverifiable），见 veracity_rules.md。
