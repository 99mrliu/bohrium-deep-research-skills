# 写作09｜方法与实验章节写作（product-arena-05-64faa4a2）

五个相互独立、零共享文件的 Skill bundle，五个截然不同的重心。每个 bundle 含完整
`SKILL.md`（合法 YAML frontmatter）、`scripts/`（纯 Python 标准库）、`references/`、
可一键运行的合成示例（`examples/run_example.sh`，产物在 `examples/expected/`，
均标注"合成示例，非正式案例结果"）以及 `GITHUB_URL.txt`。

| Bundle | 重心 | 一句话 |
|---|---|---|
| skill-a-evidence-atlas | 上游材料清点与事实溯源 | 扫描全部材料建参数台账（file:line 级），正文数值须能绑定台账，绑不上即标 [待确认] |
| skill-b-contract-forge | 下游交付契约与渲染工程 | 契约优先：解析 output_contract 生成 result.json 骨架，交付前门禁逐字段验收，纯 Python 渲染 SVG 预览 |
| skill-c-gap-tribunal | 缺口追问与冲突裁决 | 六要素缺口审计、多源取值冲突矩阵（双值并陈+明示裁决）、套话与静默填平检测、G 编号追问清单 |
| skill-d-repro-runbook | 可复现性工程 | 挖掘真实命令/环境/种子，章节组织为"输入→命令→输出→判断条件"步骤表，复现清单 G1–G7 核验 |
| skill-e-baseline-parity | 对照实验与统计协议可比性 | 基线身份台账、同预算核验、统计协议缺口检测、无支撑比较论断拦截 |

运行契约：输入 `/input/case.json` 与 `/input/task.md`；工作于 `/app/work`；产物于
`/app/output`，`result.json` 含 `case_id` 与 output_contract 全部字段；诚实 partial；
材料缺失、无法判断、运行失败分别说明。
