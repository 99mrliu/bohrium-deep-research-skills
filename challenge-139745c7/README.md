# challenge-139745c7 科研文件智能检索 — 五方向独立 Skill 作品

本目录包含 5 份相互独立、零共享文件的 Skill bundle，围绕"科研文件智能检索"
（文件已在库中，如何被准确找到、定位到章节、按条件筛出并给出可回链证据）
从五个截然不同的重心切入：

| Bundle | 重心 | 一句话 |
|-|-|-|
| `lib-forensics/` | 上游数据真实性 | 魔数识别真实类型、sha256 副本归组、权限/损坏/加密隔离与恢复记录，作答只引用过审文件 |
| `section-pinpoint/` | 章节级定位 | 全库切成"文件 › 物理页 › 章节 › 段落"锚点，命中只落到段落并带逐字锚点句与字符区间 |
| `queryforge/` | 过滤条件执行 | 提问编译为查询 JSON，硬过滤绝不放宽并留淘汰轨迹，条件无法满足如实 no_match |
| `replay-custody/` | 过程质量控制 | 哈希链保管日志 + 逐字引文核验门 + result.json 契约检查 + REPLAY.md 第三方重放 |
| `handoff-renderer/` | 下游交付工程 | manifest 完整性自检、人读/机读双格式、SVG 结构图与纯 Python 渲染的真实 PNG 预览 |

每份 bundle 内含：`SKILL.md`（合法 YAML frontmatter + 运行契约）、
`scripts/`（Python ≥3.9 标准库，零第三方依赖）、`references/`、
`examples/`（**合成示例**，含 `run_example.py` 可本地端到端跑通）、
`GITHUB_URL.txt`。

运行契约统一约定：输入 `/input/case.json` + `/input/task.md`；工作目录
`/app/work`；交付 `/app/output`（含 result.json：case_id +
output_contract 全部字段 + 诚实 status/uncertainty）；先写骨架
result.json 再增量填充，partial 如实标注边界。
