# 字段、证据与结果规范

## 1. 物理块输入（`layout-evidence-input/v1`，文件名自取）

顶层示例：

```json
{
  "document_id": "doc-123",
  "synthetic": false,
  "source": {
    "source_id": "pdf-text-blocks",
    "origin": "case PDF page blocks",
    "extraction": "PyMuPDF x.y or pdftotext -bbox-layout; record actual facts"
  },
  "pages": [
    {
      "page": 1,
      "width": 600,
      "height": 800,
      "extraction_status": "text",
      "block_order": ["h", "left-a", "left-b", "right-a", "fig", "f"],
      "unresolved": [],
      "blocks": [
        {
          "block_id": "left-a",
          "role": "body",
          "column": 1,
          "bbox": [40, 80, 280, 180],
          "lines": ["first physical line", "second-"]
        }
      ]
    }
  ]
}
```

约束：

- `document_id` 是文档标识，不替代竞赛 `case_id`。
- `source` 是溯源说明；脚本另外计算输入文件的 SHA-256。
- `pages` 必须按物理页顺序排列且 `page` 为一基连续页码；不一致时记问题并按数组位置索引，不能静默交换页面。
- `block_order` 必须含本页全部块 ID，不能重复、遗漏或引用不存在块；全文档 `block_id` 唯一。
- `lines` 是原始物理行字符串数组，不含换行/换页符。也可给 `text`，脚本按 LF 拆行，但为了明确物理行号，优先 `lines`。
- `bbox` 用 `[x0,y0,x1,y1]` 数值，保留提取器单位。多正文块缺 bbox 会产生 `BBOX_MISSING`。
- `extraction_status`：`text`、`ocr`、`no_text_layer`。OCR 页若真正完成字符核对，可设 `ocr_verified: true`；否则不可设。
- `unresolved` 可携带页级 `{code,severity,message}`；严重级别通常为 `review`、`blocking` 或 `error`。

## 2. 查询输入

```json
{
  "case_id": "original-case-id",
  "synthetic": false,
  "expected_failure": false,
  "queries": [
    {"query_id": "claim-a-exact", "query": "raw text", "mode": "exact"},
    {"query_id": "claim-a-folded", "query": "text after declared folding", "mode": "fidelity"}
  ]
}
```

- `case_id` 必须来自原 `/input/case.json`，示例中的合成 ID 不可用于正式结果。
- 一个暂断言可给 exact 与 fidelity 两个查询，以保留失败和候选恢复过程。相同 `query_id` 不应重复。
- `mode` 缺省为 `fidelity`，正式审计建议显式写出。空查询不合法。
- `expected_failure: true` 仅用于预期的负例演示，不是把正式失败变成成功。

## 3. 索引核心字段

索引 schema 为 `layout-evidence-index/v1`：

| 字段 | 含义 |
|---|---|
| `status` | 无 issues 为 `ok`；否则 `needs_review` |
| `text` | 仅 included 块按声明顺序组成的规范化 LF 阅读流 |
| `pages[].blocks[].included` | 是否进入当前阅读流 |
| `pages[].blocks[].reading_index` | included 块在本页的零基阅读序号；排除块为 `null` |
| `pages[].blocks[].input_index` | 声明 `block_order` 中位置，包括非正文块 |
| `pages[].blocks[].text` | 该块原始 `lines` 以 LF 连接，不受 quote 折叠覆盖 |
| `pages[].blocks[].lines[].line` | 一基物理行号 |
| `document_char_start/end` | 当前阅读流的零基 code-point 半开区间 |
| `page_char_start/end` | 当前页阅读流的零基 code-point 半开区间 |
| `block_char_start/end` | 块在阅读流中的边界；排除块为 `null` |
| `issues` / `uncertainty` | 未决版面、OCR、分页或坐标问题 |

偏移测量的是 Python 3 字符串 Unicode code point。某些用户感知字符由多个 code point 组成；本工具不转为 grapheme、字形或字节下标。

## 4. 定位报告核心字段

定位报告 schema 为 `layout-evidence-locations/v1`。`locations[]` 每项：

- `status`：`matched`（恰好一个）、`ambiguous`（多个）、`not_found`（零个）、`invalid`（查询错误）。
- `match_count` 与 `matches[]`：所有匹配按计划声明阅读顺序返回；不做“最佳匹配”语义排序。
- `matches[].page` / `block_id` / `line`：首段的一基页/行和块 ID。
- `matches[].line_offset_start/end` 及 `offset`：首段在原物理行的零基半开区间；`offset` 携带单位、基点和区间语义。
- `matches[].document_char_start/end`：整个 raw source excerpt 在阅读流中的边界，包含被 fidelity 折叠掉的原始连字符/换行。
- `matches[].page_char_start/end`：仅整个匹配在同一页时有值；跨页为 `null`。
- `matches[].source_excerpt`：原样截取阅读流；保真匹配时它可能与 query 不完全相同。
- `matches[].fidelity_variant`：保真匹配采用的投影，`hyphen_removed` 或 `hyphen_retained`；同一 raw range 的两个候选只保留一个匹配。
- `matches[].segments[]`：逐段列出 page、block、reading_index、line、行内/document/page offsets 和原文 text。跨行/跨栏/跨页必须以此复核。
- `spans_blocks` / `spans_pages`：所有涉及块/页，不能只看根级首个位置。
- `unresolved_distortions`：索引问题和匹配未决问题的合集；同时复制到 `uncertainty`。
- `semantic_entailment`：始终为 `not_evaluated`。匹配不证明句子为真、不支持 claim、不构成 entailment。

退出码：`0` 表示请求的命令和正向定位均无未决项；`1` 表示输入/运行错误或断言失败；`2` 表示报告已写出但有 `ambiguous`、`not_found`、`invalid` 或索引未决问题。退出码 2 不是“没有产物”，必须读取 JSON。

## 5. `sources`、`uncertainty`、`change_records`

- `sources[]`：至少记录实际 PDF（或可访问路径）、提取器/块 JSON、查询和当前报告关系。能给 SHA-256 就给；不能取得时写未知，不编造。
- `uncertainty[]`：推荐 `{code, severity, page?, block_id?, query_id?, message}`。必须覆盖无文本层、未核 OCR、未确认顺序、异常字符、歧义和合同字段未完成原因。
- `change_records[]`：记录规范化 LF、角色筛选、显式 block_order、fidelity 搜索尝试、部分结果更新时间等。索引脚本只读源文件，`source_modified: false`。不要把匹配折叠描述成修改原 PDF。

## 6. 最终 `/app/output/result.json`

先读取 `/input/task.md` 的真实 `output_contract`，再生成结果；本规范不覆盖合同。要求：

1. `case_id` 从 `/input/case.json` 原样复制，不写成 `document_id`，不用示例 ID 替换。
2. 合同列出的**全部实际字段**必须出现，名字和类型依合同；本文件的 `locations` 等只是证据数据建议。若合同不支持某结构，把机器定位详情留在 `/app/work` 并按合同引用/摘要。
3. 未恢复字段用合同允许的空值或空容器，并在 uncertainty 指明。禁止填入看似合理但未经定位的文字。
4. 无论成功或 partial，都维护 `sources`、`uncertainty`、`change_records`，若合同已为它们定义类型则严格采用合同类型。若合同限制额外字段，优先合同并将同等信息放入对应合同字段和 work 报告。
5. 启动即写 partial，并在重要阶段原子替换。应在内容中明确 partial/未完成状态（按合同状态字段）；不能仅因 JSON 完整就标 complete。
6. 完成前逐项检查合同字段齐全、case_id 相等、所有证据 offsets 可复核、扫描与歧义未决没有被隐藏。

## 7. SYNTHETIC 示例与正式结果隔离

`examples/` 下所有输入、断言和 `expected/` 输出都是手工构造的 **SYNTHETIC** 回归材料，不是正式 case 结果。样例输出中的 `synthetic: true`、`formal_result: false` 用于提醒；它们只证明脚本对这些输入行为可复现，不证明对真实 PDF 的语义、OCR 或版面恢复准确率。
