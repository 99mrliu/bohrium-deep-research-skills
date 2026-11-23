# 索引与锚点报告 JSON 结构

## index_source.py 产物（source index）

```json
{
  "tool": "index_source", "version": "1.0.0",
  "source": {"id": "SRC1", "path": "/abs/path.pdf",
             "sha256": "…", "backend": "pdftotext-layout",
             "page_count": 3, "chars": 12345},
  "pages": [
    {"page": 1, "text": "<整页原文>",
     "lines": [{"line": 1, "start": 0, "end": 42, "text": "<该行原文>"}]}
  ]
}
```

- `text` 是提取原文，不做归一化；`start/end` 是行在页文本中的字符区间（含换行符）。
- `backend ∈ {pdftotext-layout, pymupdf-text, raw-text}`，随报告保留以便复核提取质量。

## verify_anchors.py 产物（anchor report）

```json
{
  "tool": "verify_anchors", "version": "1.0.0",
  "source_id": "SRC1", "source_sha256": "…", "claims_total": 3,
  "results": [
    {"id": "A-001", "status": "verified",
     "anchors": [{"page": 1, "line_start": 8, "line_end": 9,
                  "char_start": 512, "char_end": 623}],
     "quote_words": 14, "advisories": []}
  ],
  "change_records": [
    {"id": "A-002", "kind": "dehyphenation",
     "detail": "去行尾连字符后定位成功；引文交付形态保持原文"}
  ],
  "summary": {"verified": 3, "ambiguous": 0, "not_found": 0, "gate": "pass"}
}
```

状态语义：

| status | 含义 | 处置 |
|-|-|-|
| verified | 唯一匹配，锚点可用 | 锚点写回断言 evidence |
| ambiguous | 多个候选（全部列出） | 扩引文窗口或确认后 page_hint 限定 |
| not_found | 引文非逐字或材料缺文本层 | 修复引文 / 删断言 / 记未决 |

提示码：`W_BROAD_EVIDENCE`（引文过宽）、`W_PAGE_HINT`（人工页限定已留痕）。

## 断言输入字段（JSONL，供两脚本读取）

- `id`：稳定局部 ID；
- `evidence.quote`：逐字引文（必填）；
- `evidence.page_hint`：整数，仅歧义消解后使用（可选）。

其余断言字段（subject/relation/object/qualifiers/…）本工具不消费，按任务
output_contract 组织。

## 归一化约定（可复算）

匹配 = NFKC 逐字符分解 + 空白折叠（连续空白视为一个空格，首尾不计）；
大小写敏感；去连字符仅在第二搜索空间进行（`-`+换行+小写字母 → 删除连字符换行）。
锚点偏移始终指回**原始提取文本**，与归一化无关。
