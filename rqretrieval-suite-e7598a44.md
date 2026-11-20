# 科研问题驱动检索（challenge-e7598a44）三方向套件

三个**相互独立**的 Skill bundle，针对"有限快照 + 全记录筛查 + 署名文献核验"的科研检索场景，
分别覆盖检索链路的不同环节，无共享代码、无共享产物、可单独加载使用：

| 目录 | 方向 | 核心能力 |
|-|-|-|
| [rqscreen-a-allrecord-ledger](rqscreen-a-allrecord-ledger/) | 全记录筛查台账 | 多格式解析→精确+模糊去重（显式识别夹具标注的合成重复）→条款化逐条 include/exclude/uncertain 台账（PRISMA 计数）→九篇署名文献归属核验（matched/ambiguous/missing + 元数据一致性） |
| [rqplan-b-question-planner](rqplan-b-question-planner/) | 问题拆解与检索规划 | 六要素拆解 DAG（校验器强制可检索/可判据/无环）→分波次查询计划（预算+deferred）→append-only 轮次日志→逐 SQ 饱和检测与三类停止判据（evidence_sufficient / marginal_gain_low / handoff_to_human）→覆盖矩阵与缺口分类 |
| [rqfind-c-snapshot-search](rqfind-c-snapshot-search/) | 快照内检索排序 | 本地倒排索引（拉丁截尾 + CJK 二元组、字段加权）→受控预算的术语扩展（词表+规则，防发散）→布尔/短语/分面检索，逐条命中词与行号定位→署名清单 top-k 排序审计，0 命中如实判 snapshot_empty |

三个 bundle 都只依赖 Python 3 标准库、零网络，按 `case.json` 的 `output_contract` 生成诚实的
`result.json`（status/uncertainty/sources 齐全）。详见各自 SKILL.md。
