# 账本格式：证据账本（evidence ledger）与法律状态台账（status ledger）

两种账本均为 **JSONL**（每行一个 JSON 对象，UTF-8），便于追加、审计与版本管理。

## 1. 证据账本（evidence_ledger.jsonl）

```json
{
  "schema_version": "1.0",
  "claim_id": "C1",
  "statement": "论断全文",
  "quote": "逐字引文（与来源文本逐字一致，允许空白差异）",
  "locator": {
    "file": "/app/work/patent1.txt",
    "page": 2,
    "line": 37,
    "offset": 1024,
    "source_kind": "patent_pdf_text"
  },
  "quote_hash": "sha256:<规范化引文的 SHA-256，由脚本计算>",
  "allow_ocr_tolerance": false,
  "note": "可选备注"
}
```

- `locator` 必填 `file` 与 `source_kind`；`page`（1 起，对应 pdftotext 的 `\f` 分页）、
  `line`、`offset` 至少给一个为佳；
- `source_kind` 取值：`patent_pdf_text` / `patent_pdf_ocr` / `patent_record` /
  `scientific_paper` / `official_register` / `official_gazette` /
  `aggregation_page` / `ocr_merged` / `other`；
- `quote_hash` 是账本完整性锚点：审计时重算比对，防事后篡改；
- `allow_ocr_tolerance=true` 是 OCR 容忍匹配的**事前声明**；未声明的记录即使加
  `--ocr-tolerant` 也不允许以容忍模式通过。

## 2. 法律状态台账（status_ledger.jsonl）

```json
{
  "entity": "US10000000B2",
  "status_value": "未知",
  "source_kind": "official_register",
  "query_date": "2026-11-20",
  "effective_date": "2026-01-15",
  "staleness": "登记簿数据可能滞后于实际法律事实",
  "as_register_basis": true,
  "leads_only": false,
  "downgraded": false,
  "review_advice": "到官方登记簿复核最新状态并记录查询日期",
  "statement": "截至 2026-11-20 查询，……",
  "note": "可选备注"
}
```

- `status_value` ∈ {授权, 失效, 撤回, 驳回, 审中, 未知}；
- `source_kind` ∈ {official_register, official_gazette, aggregation_page, inference}；
- 强制规则（违反即 exit 非 0）：
  - `aggregation_page`：必须 `leads_only=true` 且不得 `as_register_basis=true`；
  - `未知`：statement 不得含确定性措辞，且必须有 `review_advice`；
  - `inference`：必须 `downgraded=true` 且有 `review_advice`；
  - `query_date` 必须是合法 ISO 日期（必填）；
- 警告级（不阻断）：query_date 距今 >180 天而无 staleness；聚合页给出非未知状态
  而 note 未声明"待官方登记复核"。

## 3. 数据源清单（sources.json，license_tiers 输入）

```json
{
  "sources": [
    {"name": "国家知识产权局 CNIPA 中国专利公布公告", "url": "http://epub.cnipa.gov.cn", "access": "public"},
    {"name": "Google Patents", "url": "https://patents.google.com", "access": "public"},
    {"name": "某订阅库", "url": "https://example.invalid", "access": "login"}
  ]
}
```

## 4. 结论清单（conclusions.json，risk_grade 输入）

```json
{
  "conclusions": [
    {
      "claim_id": "C1",
      "statement": "...",
      "fields_present": ["quote", "locator", "source_kind", "status", "query_date", "sources"],
      "evidence_verified": true,
      "match_mode": "verbatim",
      "ocr_uncertain": false,
      "status_value": "授权",
      "status_query_date": "2026-11-20",
      "family_scope_known": false,
      "corpus_coverage": "partial",
      "source_count": 2
    }
  ]
}
```
