# 版本谱系（version lineage）信号与裁决规则

同一篇论文常以多种版本形态散落在不同数据库：预印本（preprint）、会议版（conference）、期刊版（journal）、增补版（supplement）。
`identity_merge.py` 对每条成员记录判定版本，再对合并组给出谱系。

## 1. 成员级信号（按优先级裁决）

| 版本 | 触发信号（任一即可） | 优先级 |
|---|---|---|
| supplement | 标题含 `supplement`/`supplementary`/`appendix`/`supporting information`；relation 字段含 `supplement` | 1（最先判） |
| preprint | DOI 前缀 ∈ {10.48550, 10.1101, 10.2139, 10.31234, 10.26434}；venue 含 arxiv/biorxiv/medrxiv/ssrn/preprint/chemrxiv/osf；pub_type 含 preprint | 2 |
| conference | venue 含 proceedings/proc./conference/workshop/symposium/conf.；pub_type 含 proceedings/conf | 3 |
| journal | pub_type 含 journal；或存在 venue | 4 |
| unknown | 以上皆无 | 5 |

## 2. 合并组谱系规则

- 组内成员版本集合写入实体 `lineage`（升序去重）；代表记录（元数据最全，同分时按版本优先级 journal > conference > preprint > supplement > unknown）决定实体 `kind`。
- 组内版本种数 > 1 → `flags` 加 `version_chain`（即该实体横跨多个版本形态，属于版本谱系合并）。
- 代表选择只决定展示字段（title/venue/year 等）；**所有成员字段（含冲突）原样保留在 `members[]` 与 `merge_evidence.conflicts`，不丢弃**。

## 3. 典型情形与处置

| 情形 | 处置 |
|---|---|
| 期刊版 + arXiv 预印本（同作者、标题含副标题差异） | 合并；`lineage=[journal, preprint]`；`version_chain`；代表取期刊版 |
| 期刊版 + 会议版（同 DOI、标题差异大） | 强制合并（same_work_different_title）；双标题留证；`version_chain` |
| 同名不同文（同标题、不同作者/年份） | 不合并；标注 distinct_same_title，不入任何版本链 |
| 缺 DOI 缺年份的残缺记录 | 独立实体，`incomplete_record`，不参与版本合并 |

## 4. 诚实性约束

- 版本信号只用于**合并组内部**的谱系标注，不作为跨组合并理由（跨组必须走 blocking + 打分 + 阈值）。
- 解析不出的引用目标保留为 stub，不会为了凑版本链而补造"期刊版存在"之类的断言。
- 所有版本判定均可由台账 `lineage` 字段 + 成员 locator 回指原始语料复核。
