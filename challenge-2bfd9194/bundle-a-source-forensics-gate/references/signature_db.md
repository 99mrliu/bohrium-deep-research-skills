# 魔数签名库与判定规则表

取证引擎 `scripts/forensics.py` 使用的签名与判定规则。签名按特异度从高到低匹配，先命中先生效。

## 签名库

| 类型 | 魔数（hex / 字面量） | 典型扩展名 | 备注 |
|---|---|---|---|
| png | `89 50 4E 47 0D 0A 1A 0A` | .png | 8 字节完整签名 |
| jpeg | `FF D8 FF` | .jpg .jpeg | SOI + 标记首字节 |
| pdf | `%PDF-` | .pdf | 头部 5 字节字面量 |
| zip | `50 4B 03 04`（`PK\x03\x04`） | .zip .docx .xlsx .pptx | OOXML 同为 ZIP 容器 |
| gzip | `1F 8B` | .gz | |
| sqlite | `"SQLite format 3\x00"` | .sqlite .sqlite3 .db | 16 字节字面量 |
| ole2 | `D0 CF 11 E0 A6 B1 1A E1` | .doc .xls .ppt | 老 Office 复合文档 |
| rar | `52 61 72 21 1A 07`（`Rar!`） | .rar | |
| 7z | `37 7A BC AF 27 1C` | .7z | |
| xml | 去空白后以 `<?xml` 开头 | .xml .html | 文本回退前判定 |
| text | 无 NUL 且可按 UTF-8 或 GB18030 解码 | .txt .md .csv .json … | 兜底回退 |
| unknown_binary | 以上皆不命中 | — | 扩展名无期望时仅记录 |

## 扩展名期望表（mismatch 判定）

`EXT_EXPECT`：.pdf→{pdf}；.png→{png}；.jpg/.jpeg→{jpeg}；
.zip/.docx/.xlsx/.pptx→{zip}；.gz→{gzip}；.sqlite/.sqlite3/.db→{sqlite}；
.doc/.xls/.ppt→{ole2}；.rar→{rar}；.7z→{7z}；
.txt/.md/.csv/.tsv/.log/.py/.yaml→{text, xml}；.json/.jsonl→{text}；
.xml/.html/.htm→{xml, text}。
**不在表中的扩展名不做 mismatch 判定**，只记录探测结果。

## 截断/损坏启发（结尾结构）

| 类型 | 期望结尾 | 检查窗口 |
|---|---|---|
| pdf | 尾部 1KB 内含 `%%EOF` | 最后 1024 字节 |
| zip | 含 EOCD 记录 `PK\x05\x06` | 最后 64KB |
| png | 结尾 8 字节 = `49 45 4E 44 AE 42 60 82`（IEND+CRC） | 文件尾 |
| jpeg | 结尾 2 字节 = `FF D9` | 文件尾 |

检查失败 → `corrupt_suspect`，证据记录期望描述与实际尾 16 字节 hex。

## 判定优先级

1. stat/打开失败 → `unreadable`（记录错误类型与信息）
2. 零字节 → `empty`
3. 扩展名有期望且实测类型不符 → `type_mismatch`（证据含头部 hex）
4. 结尾结构检查失败 → `corrupt_suspect`
5. 其余 → `authentic`（文本文件附编码探测：UTF-8 含 BOM / GB18030，报告替换字符 U+FFFD）

## 固定性哈希

全部文件 64KB 块流式 SHA-256；>256MB 文件同样全量哈希，每块回调，防内存峰值。
