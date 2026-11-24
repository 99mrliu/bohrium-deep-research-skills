# 双轨执行、去重与 PRISMA 筛选纪律

（本文件所有示例均为合成示例/虚构内容。）

## 1. 轨道判定与扫描范围

- 文档类型由文件前 matter 的 `doctype:` 标记判定：`patent` → patent 轨，
  `paper` → npl 轨；无标记的文件记入 `files_skipped` 并说明原因——
  绝不凭文件名猜测类型。
- `meta.files_scanned` 是召回声明的分母：任何"零命中"结论都必须以它佐证
  （"扫描了 N 个文件"而非"没有相关内容"）。

## 2. 去重键（dedup_key）

| 轨 | 首选键 | 退化键 | 规范化 |
| --- | --- | --- | --- |
| patent | `FAM:` + 同族号 | `PUB:` + 公开号 | 去空白、大写；公开号去非字母数字 |
| npl | `DOI:` + DOI（小写） | `TITLE:` + 标题 | 标题去标点、压缩空白、casefold |

- 去重单位 = 筛选单位：决策打在去重后的 record 上（`doc_id` 即 dedup_key），
  record 的 `members` 保留所有原始命中文档，`locators` 保留各自的 file+line。
- 示例：pat_EX1001 与 pat_EX1002 共享虚构同族号 EXFAM-2026-0001，
  合并为一条 `FAM:EXFAM-2026-0001` 记录；`raw_hits=3` 与
  `records=2` 之差即 `duplicates_removed=1`，由脚本重算。

## 3. 筛选决策纪律

- `decisions.json` 每条为 `{doc_id, decision: include|exclude, reason}`；
  每条去重后记录都必须有一条决策，缺失 → 退出 2 并逐条列出。
- `exclude` 必须给出 `reason`：无理由的排除无法审计，视同未完成筛选。
- 决策依据应可追溯：include 理由指向 matched_terms/locators 中的证据；
  exclude 理由说明与研究问题的哪一条标准不符（体系不符、无实施例、纯背景等）。

## 4. PRISMA 计数语义（全部由脚本重算）

| 阶段 | 字段 | 定义 |
| --- | --- | --- |
| identification | patent_hits / npl_hits / raw_hits | 原始命中按轨计数 |
| identification | duplicates_removed | raw_hits − 去重后记录数 |
| identification | records_after_dedup | 进入筛选的记录数 |
| screening | records_screened | = records_after_dedup（全记录决策制） |
| screening | query_excluded | 查询层被 exclusion_terms 拦下的文档数 |
| screening | no_match_scanned | 扫描过但未覆盖全部概念块的文档数 |
| screening | excluded / excluded_by_reason | 筛选层排除数及按理由分布 |
| included | total / records | 纳入记录及其筛选理由 |

**绝不采信调用方数字**：`report` 的计数一律由 decisions + hits 重算；
`--claim counts.json` 只用于对账，任何键不一致 → 退出 3 并打印
`MISMATCH: 键: 自报 x ≠ 重算 y`。修正方向永远是改自报数字，不是改脚本。

## 5. 遗漏说明（omissions_note）写法

强制覆盖五个维度（模板由 `prisma_screen.py` 生成，需结合案例改写，禁止留空）：

1. **召回范围**：扫描文件数、原始命中、去重后记录。
2. **未覆盖概念块**：整个语料中没有文档命中的块——提示检索式与语料的主题错位。
3. **零命中词项**：逐个列出未命中任何文档的词项——同义词表扩充的直接线索。
4. **排除分布**：查询层排除（命中排除词）+ 筛选层排除（按理由聚合）。
5. **残余风险**：字面词组匹配的固有盲区（未列入词表的表述、上下位概念），
   以及如需扩充召回的下一步动作。

写法要点：遗漏说明是**证据**而非套话——每一条都应能指回
`hits.json`/`prisma.json` 中的具体字段。
