# lineage_schema — 全链溯源账本规范

本文件是 `build_lineage.py` 输出（`lineage.jsonl`、`canonical_records.json`）与
`verify_chain.py` 核验规则的权威定义。

## 1. 链模型（六段，缺一不可）

```
source_db ──→ query_id ──→ response_file + item_index ──→ record_uid
     │                                                        │
     └────────────── 台账登记（query_ledger.jsonl）              ├─→ field_extractions
                                                              │      （逐字段 raw_pointer）
                                                              ├─→ dedup_decision
                                                              │      （两级精确聚类）
                                                              └─→ canonical ──→ merge_contribution
```

- `source_db ∈ {crossref, europepmc, publisher, recordlist, jsonl, csv}`（嗅探结果为准）。
- `query_id`：来自 `query_ledger.jsonl`；若台账缺失该文件的查询，记 `null` 并说明。
- `response_file` / `item_index`：原始响应文件名 + 数组下标，全局唯一定位一条记录。

## 2. record_uid 规范

格式：`{source_db}:{response_file}:item[{item_index}]`

例：`crossref:raw_crossref_page1.json:item[0]`、`europepmc:raw_europepmc.json:item[1]`。
要求：同一 case 内唯一、确定性生成（不依赖运行时刻）、可被模型在仲裁时直接引用
（ exclusions 文件即以 record_uid 为键）。

## 3. field_extractions 与 raw_pointer 规范

每个提取字段记录四项：

| 键 | 含义 |
|---|---|
| `extractor` | 提取规则名，形如 `crossref.DOI`、`europepmc.journalInfo`、`publisher.year`，可据此查库 |
| `raw_pointer` | 可机读的原始定位（见下） |
| `raw_excerpt` | 原始值的字符串前 200 字符，供人眼快速核对 |
| `value` | 归一化后的字段值（脚本内部比对使用） |

raw_pointer 语法（`verify_chain.py` 按此解析）：

- **JSON 路径**：`message.items[3].DOI`、`resultList.result[0].journalInfo.volume`；
  段为 `键` 或 `键[下标]`，逐段下钻。
- **JSONL 行**：`line[7].doi`（第 8 个非空行的 `doi` 键）。
- **CSV 行**：`row[2].Title`（DictReader 第 3 行的列）。
- **字符偏移**（纯文本/HTML 响应兜底）：`char[120:260]`，对原始文件文本切片。

核验规则：指针必须可解析，且解析值的前 200 字符与 `raw_excerpt` 完全一致；
任何不一致即为断链（`field_chain_broken`），写入 `chain_gaps.jsonl`，**不得静默修补**。

## 4. dedup_decision：两级精确聚类（本 bundle 的边界）

本 bundle **只做标识，不做模糊去重**（模糊去重是方向 A `identitymerge-dedup-engine`
的领域）。两级规则均为确定性精确匹配：

| 层级 | 规则 | 归一化 |
|---|---|---|
| Tier1 `tier1_identifier_exact` | DOI / PMID / PMCID 任一相同即并簇 | DOI 小写化并剥离 `https://doi.org/` 前缀与尾部句点；PMID/PMCID 取数字串 |
| Tier2 `tier2_title_exact` | 归一题名完全一致（≥8 字符）即并簇 | 小写、非字母数字折叠为空格、连续空白折叠 |

- 簇内按材料文件名序 + item 下标排序，**首成员为 adopted**，其余成员
  `dedup_decision.status = "duplicate_of"`、`canonical` 指向簇号；首成员 reason_code
  记聚类依据（`unique` / `tier1_identifier_exact` / `tier2_title_exact`）。
- 相似但未达精确条件（题名词项 Jaccard ≥ 0.8）的记录对一律进
  `unresolved_pairs`，只标识、不并簇，交模型仲裁；**绝不臆断**。
- canonical 字段合并：按字段顺序（doi, pmid, pmcid, title, authors, journal,
  year, volume, issue, pages, abstract, publisher, type）取簇内首个非空值；
  每个 canonical 字段记录 `from_record` + `raw_pointer`，保证字段级可回链；
  每条记录的 `merge_contribution` 记录它向 canonical 贡献了哪些字段。

## 5. 丢弃原因码表（verify_chain C2 校验的合法集）

| reason_code | 触发条件 | 出处 |
|---|---|---|
| `duplicate_of` | 记录并入某 canonical（dedup_decision.status） | build_lineage |
| `relevance_excluded` | 模型仲裁判定不相关（exclusions 文件声明） | 模型判断输入 |
| `unparsed` | item 非 dict / 提取报错 / 无法解析 | build_lineage |
| `withdrawn` | 检出撤回/撤销痕迹（`withdrawn`/`retracted` 真值键、`relation.update-to`、pubType 含 Retraction） | build_lineage |

其他任意原因码均视为非法处置（断链）。

## 6. canonical_records.json 结构

```json
{
  "canonicals": [
    {"canonical_id": "C001", "cluster_basis": "tier1_identifier_exact",
     "members": ["crossref:raw_crossref_page2.json:item[1]", "..."],
     "fields": {"doi": {"value": "...", "from_record": "...",
                        "raw_pointer": "...", "raw_excerpt": "..."}, "...": {}}}
  ],
  "unresolved_pairs": [{"record_a": "...", "record_b": "...",
                        "title_similarity_jaccard": 0.0, "note": "..."}],
  "skipped_files": [{"file": "...", "reason": "..."}],
  "stats": {"raw_records": 0, "canonicals": 0, "discarded": 0,
            "unresolved_pairs": 0}
}
```

## 7. 确定性要求

- 输出不含时间戳、不含绝对路径；遍历顺序固定（材料按文件名排序，item 按下标）；
  JSON 写入一律 `sort_keys=True`。
- `verify_chain.py` C4 对 `build_lineage.py` 双跑比对 SHA-256，不一致即断链
  `nondeterministic_replay`。
