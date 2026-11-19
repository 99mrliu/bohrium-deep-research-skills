# bohrium-deep-research-skills

Bohrium Playground 挑战 [深度研究 Agent：文献综述：综合证据，也说明边界](https://play.bohrium.com/challenge/agent-f8fb8bda) 的三个相互独立参赛作品。每个目录是一个自足的可加载 Skill（SKILL.md + scripts + resources + examples），分别从不同方向解决"深度研究"链路上的一个可核验性问题：

| 目录 | Skill | 方向 |
|-|-|-|
| [deeprq-decompose-planner](deeprq-decompose-planner/) | 问题拆解与检索规划引擎 | 六要素拆解树、依赖 DAG 波次检索计划、append-only 哈希链运行日志（可复跑） |
| [evidence-ledger-pdf](evidence-ledger-pdf/) | 证据回链核验器 | PDF 本地解析建页级语料索引、逐字引用块账本、结论引用核验门与回链率 |
| [conflict-gap-synth](conflict-gap-synth/) | 冲突证据与研究空白分析器 | 研究比较矩阵、方向冲突检出与裁定依据、A/B/C/D 证据分级、覆盖驱动空白分析 |

三者互不依赖，可单独安装到 `/skills/weekly-skill` 使用；详见各目录 SKILL.md。
