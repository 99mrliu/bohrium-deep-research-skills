# 数据格式字段级规范（identity-merge-court）

所有文件 UTF-8 编码。JSON 文件以 `\n` 结尾。`schema_version` 均为 `"1.0"`。

## 1. records.jsonl（阶段 1 建档产物）

一行一个 JSON 对象，字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| record_id | string | ✅ | 稳定唯一 id（如 R001）；全库不得重复 |
| cite_key | string | 建议 | 原标签/键（BibTeX key、EndNote 编号、CNKI 序号），原样保留 |
| source | string | 建议 | 来源库：crossref / cnki / pubmed / scopus / endnote / arxiv / bibtex ... |
| raw | string | ✅ | 原始导出片段，原样保留，归并后可回溯 |
| type | string | 建议 | journal-article / inproceedings / preprint / ... |
| title | string | ✅ | 题名（CNKI 记录放中文原题名） |
| title_original | string | 可选 | 原语种题名（当 title 为英译名时保留中文原题名） |
| authors | array | ✅ | `[{"family": "...", "given": "...", "affiliation": "..."}]`，按原顺序，全部作者 |
| year | int | 建议 | 发表年 |
| date | string | 可选 | ISO 日期 |
| container | string | 建议 | 刊名/会议名/容器 |
| volume / issue | string | 可选 | 卷 / 期 |
| pages | string | 可选 | 页码（原样，连字符样式保留） |
| article_number | string | 可选 | 文章号 |
| doi | string | 可选 | 身份 DOI（不要放关系声明中的他人 DOI） |
| pmid / arxiv / url | string | 可选 | 其他标识符 |
| version | string | 可选 | 预印本版本（v1/v2） |
| note | string | 可选 | 自由文本；**材料内关系声明放这里**（如 "Published in ..., DOI ..."） |
| translation_of | string | 可选 | 翻译关系线索：指向另一记录的 record_id / cite_key / 题名 |
| parse_warnings | array | 可选 | 上游解析警告，逐条登记 |

## 2. candidates.json（dedup_candidates.py 输出）

```json
{
  "schema_version": "1.0",
  "tool": "dedup_candidates.py",
  "record_count": 21,
  "group_count": 10,
  "evidence_grade_semantics": {"strong": "...", "moderate": "...", "weak": "..."},
  "parse_warnings": ["..."],
  "groups": [
    {
      "group_id": "G001",
      "members": ["R001", "R002"],
      "group_size": 2,
      "evidence_grade": "strong",
      "signals": [
        {"type": "same_doi", "grade": "strong", "members": ["R001", "R002"], "detail": "..."}
      ],
      "field_conflicts": [
        {"field": "pages", "values": {"R001": "210–229", "R002": "210-229"},
         "normalized_equal": true}
      ],
      "note": "候选组 >2 条时出现：signals 已按成员对给出两两证据"
    }
  ]
}
```

- `signals[].type ∈ {same_doi, same_title, translation_pair, preprint_published,
  author_year_title_jaccard}`；`grade ∈ {strong, moderate, weak}`；`members` 为该信号
  对应的记录对（>2 条组即两两证据表）。
- `field_conflicts`：原始写法存在 ≥2 种即登记；`normalized_equal` 表示规范化后是否一致。
  M2 只关心 year/volume/issue/pages/article_number 中 `normalized_equal=false` 的条目。

## 3. decisions.json（模型书写，merge_adjudicate.py 校验）

```json
{
  "schema_version": "1.0",
  "decisions": [
    {"group_id": "G001", "verdict": "merge", "canonical": "R001", "reason": "M1：……"},
    {"group_id": "G008", "verdict": "keep_separate", "reason": "M5：……"},
    {"group_id": "G009", "verdict": "human_queue", "reason": "M2：……"}
  ]
}
```

- 每个候选组恰好一条；`verdict ∈ {merge, keep_separate, human_queue}`；
- `canonical`：verdict=merge 时必填且必须是组成员；预印本-正式版组必须是正式版（M4）；
- `reason`：非空且有实质内容（≥8 字符是形式下限，内容上须含 M 规则依据与冲突解释）。

## 4. merged_records.jsonl（施加后文献表）

一行一条，包含全部未被吸收的记录；merge 组的 canonical 记录被替换为合并版，新增字段：

| 字段 | 说明 |
|---|---|
| merged_from | 被吸收成员 record_id 列表 |
| aliases | 被吸收成员的原 cite_key（供引用重定向与回溯） |
| other_identifiers | 双方标识符并集中 canonical 主字段之外的部分 `{doi: [...], pmid: [...], arxiv: [...], url: [...]}` |
| merge_exceptions | exception list：`[{"field", "canonical_value", "member_id", "member_value", "normalized_equal"}]` |
| lineage | 预印本谱系数组，格式见 references/adjudication_rules.md 的 M4 节 |

## 5. redirect_map.json

```json
{
  "schema_version": "1.0",
  "record_redirects": {"R002": "R001"},
  "cite_key_redirects": {"chen2024neuralpm": "chen2024neural"},
  "groups": {"G001": {"canonical": "R001", "absorbed": ["R002", "R003"]}}
}
```

被并 id / 原标签 → canonical 的唯一权威来源；keep_separate 与 human_queue 组**不得**出现。

## 6. residual_report.json（redirect_check.py 输出）

```json
{
  "schema_version": "1.0",
  "tool": "redirect_check.py",
  "manuscript": "路径",
  "checked_labels": ["被检索的被并标签"],
  "residual_count": 1,
  "clean": false,
  "residuals": [
    {"label": "chen2024neuralpm", "absorbed_record_id": "R002",
     "redirect_to": "chen2024neural", "line": 17, "excerpt": "……"}
  ]
}
```

`residual_count > 0` 时脚本退出码 1；修复后重跑至 `clean=true`（退出码 0）。

## 7. merge_report.json / merge_report.md

- `summary`：groups / merged / keep_separate / human_queue / records_before /
  records_after / redirects。
- `cases[]`：逐案 `{group_id, verdict, reason, members, signals, evidence_grade,
  field_conflicts, canonical?, absorbed?, exceptions?, lineage?, redirects?, follow_up?}`；
  human_queue 案附 `follow_up`（人工核查路径）。md 为同内容的人类可读版。
