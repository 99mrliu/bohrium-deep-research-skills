# 编码处置手册

目标：任何输入字节流都要么被无损解码，要么带着明确的损失记录进入台账；
**禁止静默乱码、禁止静默丢文件**。

## 判定顺序（decode_bytes）

1. BOM（`EF BB BF`）→ `utf-8-sig`，记 `bom-stripped`；
2. 严格 UTF-8 → 成功即收，零笔记；
3. 失败则依次试 `gb18030`、`latin-1`，记 `utf-8-decode-failed-fell-back`；
4. 仍失败 → `utf-8 errors=replace`，记 `lossy-replace` 并统计 `�` 个数
   （`replaced_chars`）。

每次判定连同原始字节数、行数一起写入 `ingest_ledger.json` 的对应文件条目。

## 内容级乱码（mojibake）

文件整体编码正确但个别字段是"双重错误编码"（如 `GÃ¶teborg` 应为 `Göteborg`）。
策略：

- 用模式表扫描 `title/abstract/authors/journal`，命中即在记录的
  `repair_notes` 写 `suspected-mojibake-in:<字段>`；
- **不改写原文**——修复属于下游人工决定，摄入层只保证提示不丢失；
- 下游做证据锚定时应以原文为准，避免按"修复后文本"匹配导致锚定失败。

## 审计联动

`ingest_audit.py` 的 A5 检查：凡 `encoding != utf-8` 或 `replaced_chars > 0`
的文件，必须在 `decode_notes` 留有说明，否则 FAIL。这把"编码异常是否有解释"
变成可自动复核的硬门。

## 诚实边界

- 回退解码（gb18030/latin-1）是**有损假设**，报告里如实呈现，不声称恢复原貌；
- `lossy-replace` 的文件应在 result.json 的 uncertainty 中点名；
- 若整批文件均为非 UTF-8 且无法确认原始编码，结论降级为 partial 并说明。
