# 阅读15｜文献知识图谱构建（product-arena-10-760d1a0b）— 五方向参赛作品

本目录收录围绕“文献知识图谱构建”的五个相互独立、零共享文件的 Skill 作品。
每个子目录即一份完整 bundle（`SKILL.md` + `scripts/` + `references/` + 标注为
合成示例的 `examples/`），均已在本地端到端跑通各自示例。

| 目录 | 重心 | 核心确定性机制 |
|-|-|-|
| `01-source-provenance-kg` | 上游语料真实性与证据地址保真 | 输入宽容解析、段落哈希台账、逐字引文/地址/归属机器核验、机械覆盖率 |
| `02-crossdoc-identity-kg` | 跨篇实体身份裁决 | 规范化候选键 + 三态合并门（MERGE / KEEP_DISTINCT / UNDECIDED）与阻断规则 |
| `03-conditioned-relation-kg` | 关系语义与条件约束 | 受控关系词表、作者声音分级、比较条件 lint、冲突全保留 |
| `04-executable-query-kg` | 可执行查询与图形化交付 | 确定性查询 DSL、快照哈希复核、依赖零外的 SVG/CSV/Markdown 导出 |
| `05-incremental-change-kg` | 增量更新与变更审计 | 稳定语义 ID、基线封存、ADD/MERGE/KEEP_DISTINCT/UPDATE_EVIDENCE/CONFLICT 变更集 |

五份 bundle 分别把主要确定性逻辑放在输入层、实体层、关系层、查询层与版本层，
而非同一管道的变体。各目录的 `GITHUB_URL.txt` 指向自身位置。

运行契约：Skill 安装于 `/skills/weekly-skill`；读取 `/input/case.json`、`task.md`
与 `corpus-manifest.json`、`material.json`、`primary-material.json`、
`secondary-material.json`；工作于 `/app/work`；`/app/output/result.json` 含
`case_id` 并动态镜像全部 `output_contract` 字段，诚实标注 partial。
