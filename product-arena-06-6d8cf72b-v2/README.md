# 阅读10｜文献总结与结构化笔记（v2）

题目：`product-arena-06-6d8cf72b`。本目录包含五个相互独立、零共享文件的 Skill bundle；旧题目录保持不动。

| Bundle | 独立重心 | 可核验产物 |
|---|---|---|
| [argument-loom](argument-loom/) | 章节原生“主张—证据—推理—限制”论证结构 | 论证图、章节笔记、锚点与拓扑审计 |
| [scope-mesh](scope-mesh/) | 结论适用条件、例外与反外推 | 八维 scope mesh、普遍结论审查、合同审计 |
| [numerical-replication-desk](numerical-replication-desk/) | 数值参数、单位与可执行复算 | Decimal 验证账本、派生对照 SVG、负例回归 |
| [visual-evidence-atlas](visual-evidence-atlas/) | 原始页面、图表区域与直接视觉证据 | 区域图谱、HTML/Markdown 预览、视觉状态审计 |
| [semantic-coverage-forge](semantic-coverage-forge/) | 逐问题直接作答与语义遗漏控制 | answer matrix、语义审查、权威合同回链 |

每个 bundle 均包含完整 `SKILL.md`、`scripts/`、`references/`、`GITHUB_URL.txt` 和真实执行的**合成示例**。示例不代表平台正式案例答案。各 bundle 使用 Python 标准库；真实论文处理仅调用平台提供的 PDF 文本、渲染及 OCR 工具。正式运行读取 `/input/case.json`、`/input/task.md` 与实际材料，在 `/app/work` 工作，向 `/app/output` 写出含真实 `case_id` 和全部 `output_contract` 声明字段的 `result.json`，并诚实记录 `partial`、来源、不确定性与变更。

## 本地验证摘要

- Argument Loom：合成与非合成回归、状态降级、闭合合同响应覆盖、诚实失败均通过。
- Scope Mesh：24 项测试通过，覆盖组合 schema、未知关键字拒绝、普遍量词与记录归属。
- Numerical Replication Desk：9 个测试方法通过，13 个合成计算全部匹配；支持有符号 SVG 与区域化引文核对。
- Visual Evidence Atlas：11 个测试方法通过，覆盖不可读区域、跨 PDF 页码、直接单元格证据与 caption-only 负例。
- Semantic Coverage Forge：14 个测试方法通过，覆盖 case 合同权威、sidecar 证据、checked scope 与闭合直接回答合同。

所有 bundle 均通过严格 UTF-8、文件数不超过 50、单文件不超过 500KB、总量不超过 2MB、无符号链接、无二进制及无本机路径检查。合成 SVG 已实际渲染目检；机器结构校验不被表述为科学真值验证。
