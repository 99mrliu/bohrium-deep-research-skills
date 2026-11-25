# litsearch-a2909a72-v2 — 学术文献检索 challenge, five independent skills (round 2)

Bohrium Playground 挑战 [学术文献检索：科研检索：找到文献，也保留筛选依据](https://play.bohrium.com/challenge/challenge-a2909a72)
的第二轮参赛作品：五个相互独立、零共享文件的 Skill。每个目录是一个自足的可加载 Skill
（SKILL.md + scripts + references + examples），可分别安装到 `/skills/weekly-skill` 使用。

## 与第一轮（litsearch-a2909a72）的区别

第一轮三份作品实为同一条「查询→抓取→去重→排序」管线的变体（attempt 91843/91844/91845 =
73.67 / 69.0 / 5.0，榜首约 77.7），且依赖在线 API。本题运行契约明确：案例为 source-bound
（9 篇真实文献 + 组织方本地 Crossref/EuropePMC/出版方快照 + 真实保留引用图 + 本地增量导入
状态），**无在线远程覆盖**。本轮五个方向重心错位，全部离线优先（agent 可用平台检索工具
补充抓取并保存原始响应，引擎只确定性地处理本地文件）：

| 目录 | Skill | 重心 |
|-|-|-|
| [a-snapshot-trust-gate](a-snapshot-trust-gate/) | snapshot-trust-gate | **上游数据真实性**：快照先做哈希/解析/schema 校验门，截断、重复负载、空表、坏记录全部隔离记账后才建库检索 |
| [b-refgraph-snowball](b-refgraph-snowball/) | refgraph-snowball | **引用图谱追踪**：从本地快照与参考文献导出重建保留引用图，种子双向滚雪球（≤2 跳），图结构评分逐项分解，不可解析引用显式入账 |
| [c-graded-relevance-bench](c-graded-relevance-bench/) | graded-relevance-bench | **排序/裁决质量**：0–3 级相关性 rubric 评分逐条分解、置信分层、边界队列交 agent 裁决并落账，nDCG 自洽性核验 |
| [d-incremental-import-reconciler](d-incremental-import-reconciler/) | incremental-import-reconciler | **增量导入状态对账**：对组织方本地导入状态逐条分类 ALREADY_IMPORTED/UPDATED/NEW/CONFLICT，字段级 diff 变更记录，二次执行零变更的幂等证明 |
| [e-retrieval-run-warden](e-retrieval-run-warden/) | retrieval-run-warden | **过程质量控制**：反捏造门（候选标识符必须存在于逐字节证据副本）、PRISMA 流程账目重算、契约门禁、诚实 partial，FAIL 也是可交付的审计结果 |

五个方向不耦合：各自独立的引擎、规则与证据模型，可单独运行。所有引擎仅依赖
Python 标准库，完全离线，无需安装任何包。

## 运行时契约

平台将 Skill 安装到 `/skills/weekly-skill`，用官方 DeepSeek Harness 在 3 个固定案例上运行：
输入 `/input/case.json` + `task.md`，工作目录 `/app/work`，产物 `/app/output`（含带原始
`case_id` 与全部 `output_contract` 字段的 `result.json`）。各 SKILL.md 写清触发方式、步骤、
异常处理与自查清单；`examples/minimal_example.md` 给出真实本地运行的示意输出（均已标注为
合成示例，非正式案例结果）。

## 目录结构

每个 bundle：

```
SKILL.md                     # 技能本体（YAML frontmatter: name/description）
scripts/                     # 引擎 + result.json 构建/校验器（stdlib only, offline）
references/                  # 方法学（每条规则可复核）+ 自查清单
examples/synthetic-case/     # 合成示例输入（虚构记录，保留 DOI 前缀 10.0000）
examples/synthetic-output/   # 真实本地运行产物（合成示例，非正式案例结果）
examples/minimal_example.md  # 最小调用示例与真实运行摘要
GITHUB_URL.txt               # 本目录的 GitHub 公开链接
```
