# bohrium-deep-research-skills

Bohrium Playground 挑战 [深度研究 Agent：文献综述：综合证据，也说明边界](https://play.bohrium.com/challenge/agent-f8fb8bda) 的三个相互独立参赛作品。每个目录是一个自足的可加载 Skill（SKILL.md + scripts + resources + examples），分别从不同方向解决"深度研究"链路上的一个可核验性问题：

| 目录 | Skill | 方向 |
|-|-|-|
| [deeprq-decompose-planner](deeprq-decompose-planner/) | 问题拆解与检索规划引擎 | 六要素拆解树、依赖 DAG 波次检索计划、append-only 哈希链运行日志（可复跑） |
| [evidence-ledger-pdf](evidence-ledger-pdf/) | 证据回链核验器 | PDF 本地解析建页级语料索引、逐字引用块账本、结论引用核验门与回链率 |
| [conflict-gap-synth](conflict-gap-synth/) | 冲突证据与研究空白分析器 | 研究比较矩阵、方向冲突检出与裁定依据、A/B/C/D 证据分级、覆盖驱动空白分析 |

三者互不依赖，可单独安装到 `/skills/weekly-skill` 使用；详见各目录 SKILL.md。

## 文献翻译（product-arena-01-5a9928c1，阅读03）

挑战 [文献翻译：科研阅读：回答问题，也给出依据](https://play.bohrium.com/challenge/product-arena-01-5a9928c1) 的三个相互独立参赛作品，位于 [translation-5a9928c1/](translation-5a9928c1/)。每个目录是一个自足的可加载 Skill（SKILL.md + scripts + references + examples），三方向重心错位、零共享文件：

| 目录 | Skill | 方向重心 |
|-|-|-|
| [a-termbase-gate](translation-5a9928c1/a-termbase-gate/) | 术语表门禁翻译 | 上游术语治理：从原文抽取候选术语、锁定唯一译名与禁用变体，机检审计标题/摘要/正文/图注/结论中译名一致，违例阻断交付 |
| [b-bilingual-align](translation-5a9928c1/b-bilingual-align/) | 长文分段与双语对照渲染 | 下游对照工程：跨页/跨栏分段（连字符修复、页眉页脚剔除）、稳定段号、锚点对齐（漏译/重复/错位显式登记）、纯 stdlib 双语并排 HTML 渲染 |
| [c-fidelity-audit](translation-5a9928c1/c-fidelity-audit/) | 译文保真核验与人工接管 | 过程质量控制：数字/单位/引用/图表编号/否定与限定五类不变量核验，阻断项拦截交付，未决项全部进入人工确认清单 |

三者互不依赖，可单独安装到 `/skills/weekly-skill` 使用；各目录 examples/ 内为合成示例（非正式案例结果），详见各 SKILL.md。
