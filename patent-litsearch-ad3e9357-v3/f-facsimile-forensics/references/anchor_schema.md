# 锚点记录模式（anchor_schema.md）

## 1. 锚点记录（anchor record）

`page_anchor.py locate` 与差异台账中每个值所附的锚点均为如下对象：

```json
{
  "field": "publication_number",
  "file": "FX-2099-0123456-A1_frontpage.pdf",
  "file_sha256": "<64 hex>",
  "page": 1,
  "line_span": [4, 4],
  "byte_span": [123, 141],
  "byte_span_basis": "page_text_utf8",
  "quote": "US 2099/0123456 A1",
  "match_type": "exact"
}
```

| 字段 | 含义 |
| --- | --- |
| `field` | 被锚定的书目字段名 |
| `file` | 来源文件相对路径（以清点输入目录为根） |
| `file_sha256` | 来源文件全文的 SHA-256（与清单一致） |
| `page` | 页码（整数，1 起）；跨页匹配时为 `"N-M"` 字符串 |
| `line_span` | 提取文本层内的行区间 `[起, 止]`（含端点，1 起）；跨页匹配时为 `null` |
| `byte_span` | `[起, 止)` UTF-8 字节区间，基准见 `byte_span_basis` |
| `byte_span_basis` | `page_text_utf8`（单页文本）或 `joined_pages_text_utf8`（按 `\n` 拼接的跨页文本） |
| `quote` | 源文本中切出的逐字引文；容差匹配时保留原始空白/换行 |
| `match_type` | `exact` / `whitespace_collapsed` / `page_boundary_merged` / `page_boundary_merged+whitespace_collapsed` |

## 2. 定位输出（locate output）

```json
{
  "generated_by": "page_anchor.py locate",
  "field": "...", "value": "...",
  "file": "...", "file_sha256": "...",
  "policy_applied": {"allow_whitespace_collapse": false, "allow_page_boundary_merge": false},
  "candidate_count": 2,
  "anchors": ["...所有候选锚点，绝不静默择一..."],
  "violations": []
}
```

## 3. 核验规则（verify）

`page_anchor.py verify` 对每条锚点依次核验：

1. `file_sha256` 与 pages JSON 一致；
2. `quote` 逐字出现在所述页文本（跨页锚点为拼接文本）中；
3. 若给出 `byte_span`，按 `byte_span_basis` 切片必须还原出 `quote`。

任一失败 → 退出码 1 并指明锚点序号与原因（用于拒绝伪造或陈旧锚点）。

## 4. 确定性约定

- 行号、字节区间均针对**提取文本层**（`extracted/<sha256>.pages.json` 中的文本），
  不是传真影像的像素坐标；文本层一旦固定，锚点即确定。
- 提取方法（poppler 或标准库回退）不同可能导致文本层空白略有差异；
  同一案例内应固定使用同一次清点产出的 pages JSON，锚点方可复验。
