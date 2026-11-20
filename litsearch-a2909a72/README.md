# litsearch-a2909a72 — 学术文献检索 challenge, three independent skills

Bohrium Playground 挑战 [学术文献检索：科研检索：找到文献，也保留筛选依据](https://play.bohrium.com/challenge/challenge-a2909a72)
的三个相互独立参赛作品。每个目录是一个自足的可加载 Skill（SKILL.md + scripts + resources +
examples），从截然不同的方向解决文献检索链路上的一个核心问题，互不依赖，可分别安装到
`/skills/weekly-skill` 使用。

| 目录 | Skill | 方向 |
|-|-|-|
| [bundle-a-query-planner](bundle-a-query-planner/) | litsearch-query-planner | **多轮查询规划**：agent 写检索计划（分面+同义词+年份窗+数据库），确定性引擎执行 core-AND → 分面宽松 OR → 引用滚雪球（OpenAlex 双向）多轮检索，按边际收益停止，逐分面覆盖报告，每条候选可回溯到原始 API 响应 |
| [bundle-b-termxpand-screen](bundle-b-termxpand-screen/) | litsearch-termxpand-screen | **关键词/术语扩展 + 分级筛选账本**：缩写对检测、拼写/连字符/词形变体、内置中英科学词表（可扩展），两阶段 PRISMA 式筛选，保留与排除逐条记录决策、理由代码与证据句，输出筛选流程计数与遗漏说明 |
| [bundle-c-federated-provenance](bundle-c-federated-provenance/) | litsearch-federated-provenance | **多库联合 + 去重与来源溯源校验**：Crossref/OpenAlex/EuropePMC/arXiv 独立适配器 + 本地快照摄取 + 原始响应缓存，跨源去重聚类（DOI 精确 + 标题模糊 ≥0.92，DOI 不同不合并），逐字段合并溯源与冲突记录，DOI 抽样核验 |

三个方向不耦合：各自独立的脚本、词表与证据模型，可单独运行。所有引擎仅依赖
Python 标准库，无需安装任何包。

## 运行时契约

平台将 Skill 安装到 `/skills/weekly-skill`，用官方 DeepSeek Harness 在 3 个固定案例上运行：
输入 `/input/case.json` + `task.md`，工作目录 `/app/work`，产物 `/app/output`（含带原始
`case_id` 与全部 `output_contract` 字段的 `result.json`）。各 SKILL.md 写明了触发方式、
步骤、异常处理与自查清单；`examples/minimal_example.md` 给出基于真实冒烟测试的示意输出
（已标明为示例，非正式案例结果）。

## 目录结构

每个 bundle：

```
SKILL.md                     # 技能本体（YAML frontmatter: name/description）
scripts/                     # 引擎 + result.json 构建/校验器（stdlib only）
resources/                   # 方法学、规则/词表、自查清单
examples/minimal_example.md  # 最小调用示例（示意输出已标明）
```
