# anchor-schema.md — claim card 与源索引模式（SYNTHETIC EXAMPLE 配套规范）

本文件定义 source-weld-verifier 的两种数据格式：`claims.json`（页级主张卡）
与 `source_index.json`（源索引，由 `scripts/source_index.py` 生成）。
两者共同支撑"页面上每句话都能焊回源材料"的可核验性目标。

## 1. claims.json —— 页级主张卡

顶层为 `{"claims": [...]}`（裸数组也可接受）。每条 claim card：

```json
{
  "claim_id": "c1",
  "slide_text": "The module retained 91% of initial efficiency after 1000 hours.",
  "strength": "established",
  "locator": {
    "file": "synthetic_paper_alpha",
    "pdf_page": 1,
    "printed_page": 1,
    "section": "Abstract",
    "exhibit": "Figure 1"
  },
  "anchor": "retained 91 percent of its initial efficiency after 1000 hours",
  "notes": "可选：该 claim 服务的页码/叙事角色等"
}
```

### 字段语义

| 字段 | 必填 | 语义与纪律 |
|-|-|-|
| `claim_id` | 是 | 唯一标识；审计报告按此回指。 |
| `slide_text` | 是 | 将要写上幻灯片的句子。**其中每个数字 token 都会被扫描**，必须在所焊文档的数字注册表中按数值出现（`98.6` 这类凭记忆漂移出的数字会被 `number_not_in_source` 拦下）。 |
| `strength` | 是 | 证据强度分级：`established`（多证据/作者主结论）、`preliminary`（单组数据/作者自陈待验证）、`contextual`（背景、他人工作、动机性陈述）。`preliminary`/`contextual` 的 `slide_text` 触发强度措辞门（见 strength-lexicon.md）。 |
| `locator.file` | 是 | 源索引中的 `doc_id`（材料文件名去扩展名、非字母数字转 `_`）。 |
| `locator.pdf_page` | 是 | pdftotext 分页后的 1 基页码（txt 材料按 `\f` 切页同约定）。锚定核验以此页为准。 |
| `locator.printed_page` | 建议 | 文档印刷页码，供人读；不参与机检，可为 `null`。 |
| `locator.section` | 建议 | 节名（应能在节标题注册表中找到）。 |
| `locator.exhibit` | 建议 | 图表 label（如 `Figure 2`、`Table 1`，应对应题注注册表条目），无则 `null`。 |
| `anchor` | 是 | **逐字摘自源材料的引文**，是 claim 的焊接点。允许跨行（脚本做空白压缩）与跨 PDF 断词（脚本做 `-\n` 连字符修复）；不允许同义改写、不允许凭记忆重述。 |

缺必填字段或 `locator` 非对象/缺 `file` → schema 错误，审计脚本 exit 2。

## 2. source_index.json —— 源索引

```json
{
  "index_version": 1,
  "materials_dir": "/abs/path",
  "doc_count": 3,
  "parse_ok": 3,
  "docs": [
    {
      "doc_id": "synthetic_paper_alpha",
      "source_file": "synthetic_paper_alpha.txt",
      "sha256": "…",
      "kind": "text | pdf",
      "parse_status": "ok | unparseable",
      "parse_method": "direct-read | pdftotext-layout | pdftotext-plain",
      "page_count": 3,
      "pages": [{"page": 1, "char_start": 0, "char_end": 1234, "chars": 1234, "text": "…"}],
      "captions": [{"doc_id": "…", "label": "Figure 1", "page": 2, "text": "…"}],
      "sections": [{"doc_id": "…", "page": 1, "heading": "1. Introduction"}],
      "numbers": [{"doc_id": "…", "value": "91", "unit": "percent", "page": 1, "context": "…"}]
    }
  ]
}
```

- `pages[]`：逐页文本 span，页码即 `locator.pdf_page` 的参照系。
- `captions[]`：Figure/Table 题注注册表，用于核对"图表引用对错 caption"。
- `sections[]`：节标题注册表，用于核对 `locator.section`。
- `numbers[]`：数字注册表。数字连同紧随的可选单位与所在页、上下文一并登记；
  转录纪律要求数字**连同单位与条件**逐字抄录（如 "1000 hours at 85 degrees
  Celsius"），不得凭记忆补单位。
- `parse_method` 必须如实记录：PDF 走 `pdftotext-layout`（失败重试后为
  `pdftotext-plain`），纯文本为 `direct-read`。目录含 PDF 而 PATH 无
  pdftotext 时，建索引直接 exit 2，绝不臆造内容。

## 3. 审计状态与退出码

锚定五态 + 两个扩展态：

| 状态 | 含义 | 修复动作 |
|-|-|-|
| `verified` | 声明页内逐字命中，数字与措辞合规 | — |
| `page_mismatch` | 引文真实存在于其它页 | 把 `pdf_page` 改成报告给出的 `found_page` |
| `not_verbatim` | 归一化后全文档未命中 | 回原文重新逐字摘录，或删除该 claim |
| `doc_missing` | `locator.file` 不在索引中 | 核对 doc_id（以 source_index.json 为准）或补建索引 |
| `quote_empty` | anchor 为空 | 补逐字引文；无引文的句子不许上页 |
| `number_not_in_source` | slide_text 数字不在源数字注册表 | 回源核对数字、单位与条件；删改漂移数字 |
| `strength_overclaim` | 弱强度 claim 用了过强词 | 换成弱措辞，或把 strength 升档并补强证据 |

退出码：`0` 全部 verified；`1` 存在任何非 verified（stdout 逐项清单 +
`audit_report.json` 含回链率 `linkage_rate = verified/total`）；
`2` 用法/IO/schema 错误。
