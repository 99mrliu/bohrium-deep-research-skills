# code-exec-9ec929fe-v3：科研代码生成与执行（第三轮，五个独立方向）

对应 Playground 挑战 `challenge-9ec929fe`「科研代码生成与执行：科研数据分析」。本目录包含五份相互独立、零共享文件的 Skill bundle，重心各异，覆盖链路的不同位置；每份含完整 `SKILL.md`（合法 YAML frontmatter）、`scripts/`、`references/` 与可本地端到端运行的合成最小示例（示例数据为合成，输出标注为示例，不冒充正式案例结果）。

| Bundle | 重心 | 一句话 |
|-|-|-|
| `a-direct-analysis-engine` | 端到端确定性执行引擎 | 一条命令把 /input 变成可复核的 /app/output（建档、清洗、统计、图、SQL、双通道 verify），Agent 只裁决歧义 |
| `b-stat-assumption-tribunal` | 统计推断合规裁决 | 前提检验不过关不许报 p 值，自动改判非参数检验并给出理由；口径（ddof/四分位/缺失策略）全部显式化 |
| `c-figure-render-forge` | 下游渲染工程 | 图与数据字典绑定（轴=字段+单位）、确定性渲染、图下数据随附、QC 独立重算图中声明 |
| `d-sqlite-query-foundry` | 数据库查询正确性 | 只读执行 + EXPLAIN QUERY PLAN + 行数对账（基线 COUNT/扇出预警）+ 独立重构复核聚合 |
| `e-incremental-delivery-governor` | 预算治理与诚实交付 | 900s/64 请求预算内：首分钟落盘契约骨架，阶段日志、检查点哈希链，finalize 只接受 complete 或有理由的 partial |

运行契约（五份一致）：Skill 安装于 `/skills/weekly-skill`；输入 `/input/case.json` + `task.md` + 数据材料；工作区 `/app/work`；交付 `/app/output/result.json`，含 `case_id` 与 `output_contract` 全部字段、诚实 `status`、`anomalies`、含输入 sha256 的 `provenance`；partial 必须逐项说明限制。

第三轮与第二轮（`code-exec-9ec929fe/`）的关系：v2 五份均为“门禁/检查”型（契约门、环境移植、静默错误审计、运行取证、图保真清单），不直接产生计算结果；v3 转为“直接完成工作 + 可独立复核”的工程化工具，重心重新错位于执行、统计、渲染、查询、交付过程五个不同环节。

各 bundle 的公开链接即其目录（与 `GITHUB_URL.txt` 第一行一致）。
