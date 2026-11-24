# 台账与报告格式说明（字段级）

所有文件均为 UTF-8 文本。JSONL = 每行一个独立 JSON 对象，不允许注释、不允许
尾随逗号；空行被忽略。脚本对未知字段一律忽略（如示例中的 `_example_note`），
但不得依赖未知字段传递判定信息。

## 1. entries.jsonl（verify_entries.py 的输入）

每行一个文献条目：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | string | 是 | 条目唯一标识，报告以此索引 |
| title | string | 是 | 文献标题，按文献库原文抄录 |
| authors | list[string] | 建议 | 作者列表；第一作者取 `authors[0]`。姓名格式建议"姓, 名"或"姓 名"，姓的提取规则：含逗号取逗号前，否则取首个空白分隔词 |
| year | int/string | 建议 | 发表年份，按原文抄录 |
| venue | string | 否 | 期刊/会议名（不参与机器比对，供人读） |
| doi | string | 否 | DOI；缺失或为空即走"无 DOI"分支 |
| pmid | string | 否 | PubMed ID（保留字段，不参与比对） |
| type | string | 否 | 条目类型（如 journal-article），供人读 |

示例（合成数据）：

```json
{"id": "E1", "title": "基于虚构晶格材料 HNX-3 的热电转换效率研究", "authors": ["林, 晓风", "陈, 雨桐"], "year": 2023, "venue": "合成材料学报（虚构）", "doi": "10.55001/fakej.2023.001", "type": "journal-article"}
```

原则：字段只抄不造——文献库里没有的字段就不要出现。

## 2. snapshot.json（verify_entries.py 的可信快照输入）

模拟"组织方提供的可信元数据快照"。规范形式为对象：

```json
{
  "snapshot_id": "SYNTH-SNAPSHOT-0001",
  "records": [
    {
      "doi": "10.55001/fakej.2023.001",
      "title": "基于虚构晶格材料 HNX-3 的热电转换效率研究",
      "authors": ["林, 晓风", "陈, 雨桐"],
      "year": 2023,
      "venue": "合成材料学报（虚构）",
      "type": "journal-article"
    }
  ]
}
```

- 顶层也接受裸的记录数组 `[ {...}, ... ]`（等价于只有 records）。
- records 内每条至少应有 doi 或 title 之一，二者皆无的记录被忽略。
- DOI 索引按 casefold 匹配；标题索引按 NFKC+大小写折叠+去标点+空白折叠
  归一化后匹配。
- 快照是核验的**唯一**依据；脚本不联网。

## 3. claims.jsonl（claim_anchor_audit.py 的输入）

每行一条论断台账：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | string | 是 | 论断唯一标识 |
| claim | string | 建议 | 论断内容（人读；报告原样转录） |
| source | string | 是 | 来源文件名，相对 --sources 目录；禁止 `..` 路径逃逸 |
| quote | string | 是 | 从来源正文**逐字复制**的引文；归一化规则为 NFKC+空白折叠，因此换行、连续空格不影响匹配，但任何字符改动都会导致 FAIL |
| locator | string | 否 | 页码/节号等定位符；若提供，报告其是否出现于来源 |

示例（合成数据）：

```json
{"id": "C1", "claim": "HNX-3 在 320 K 下 ZT 达到 1.42", "source": "fake_paper_alpha.txt", "quote": "在 320 K 时，HNX-3 的无量纲热电优值 ZT 达到 1.42，较基线材料提升约 37%。", "locator": "第 3 节"}
```

## 4. verification_report.json（verify_entries.py 的输出）

| 字段 | 说明 |
| --- | --- |
| tool / version / generated_utc | 工具标识与时间戳（SOURCE_DATE_EPOCH 可控，缺省 1970-01-01T00:00:00Z） |
| verification_basis | 核验依据声明（仅输入快照、未联网） |
| entries_file / snapshot_file / snapshot_record_count | 输入回执 |
| summary | total 及六个状态各自的计数 |
| results[] | 逐条目结果，字段见下 |

results[] 每项：

| 字段 | 说明 |
| --- | --- |
| id / title | 条目回执 |
| status | verified_identity / metadata_conflict / not_found_in_snapshot / not_checked / suspected_fabricated / invalid_input |
| reason | 机器可读的判定理由（如 doi_match_and_fields_consistent、invalid_doi_syntax、title_matches_record_with_different_doi） |
| evidence | 证据对象：matched_by（doi/title）、snapshot_doi、claimed_doi、警告文本等 |
| conflicts[] | 冲突字段表：{field, entry_value, snapshot_value}，field ∈ title/year/first_author |
| note | 可选；by_title 表示无 DOI 按标题确认 |

退出码：存在 suspected_fabricated / metadata_conflict / invalid_input 任一即 1，
否则 0。verification_report.md 为同内容的人读版。

## 5. anchor_report.json（claim_anchor_audit.py 的输出）

| 字段 | 说明 |
| --- | --- |
| tool / version / generated_utc / audit_basis | 同上 |
| sources_dir / ledger_file | 输入回执 |
| summary | total / pass / fail / error 计数 |
| results[] | 逐条结果，字段见下 |

results[] 每项：

| 字段 | 说明 |
| --- | --- |
| id / claim / source | 台账回执 |
| status | PASS / FAIL / ERROR |
| char_offset | PASS 时 quote 在归一化后来源文本中的命中偏移；否则 null |
| diagnosis | FAIL 时：paraphrase_or_minor_alteration / cross_segment_splice / source_mismatch；ERROR 时：source_file_not_found / source_unreadable / missing_source_field / missing_quote_field / source_path_escapes_sources_dir / json_decode_error / ledger_line_not_an_object |
| evidence | FAIL 时含 best_window_offset、best_window_similarity（与最相似等长窗口的相似度）、closest_window_60（最相似窗口前 60 字符）、diagnosis_label（中文诊断）；PASS 且提供 locator 时含 locator_found_in_source |

退出码：存在 FAIL / ERROR 任一即 1，全部 PASS 为 0。anchor_report.md 为同
内容的人读版。

## 6. source_registry.json（source_registry.py 的输出）

| 字段 | 说明 |
| --- | --- |
| tool / version / generated_utc | 同上 |
| sources_dir / file_count / total_bytes | 目录回执与总量 |
| files[] | {path, bytes, sha256, type, note?}；type ∈ txt/md/json/bib/ris/csv/pdf/unreadable/unknown_binary；pdf 恒带 note: binary_not_parsed |
| warnings[] | 人读警告（hash_failed、json_parse_failed、类型推断等） |

用途：固化输入指纹。任何"来源到底是什么"的争议，以 registry 中的 SHA-256
与字节数为准。
