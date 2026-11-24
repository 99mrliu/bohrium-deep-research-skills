# paper-logic-audit-16d4414d：论文逻辑与论证审查 — 五份独立 Skill 作品（第三轮）

Bohrium Playground challenge-16d4414d（论文逻辑与论证审查：论文质量审查——发现问题，
也给出证据）参赛作品。五份 bundle 相互独立、零共享文件，重心沿题目自身给出的五个
突破方向切分，与早前投稿的切分（输入保真/统计重算/引用对账/过程质控/交付工程）
完全不同：

| Bundle | 重心 | 一句话 |
|-|-|-|
| `skill-a-claim-ledger/` | 论点层（主张抽取） | 先建主张清单再下判断：句子锚定 → 主张候选+归因提示（作者主张/转述/假设/对照设计）→ lint 门禁强制逐字 quote、合法归因、转述误判须附说明 |
| `skill-b-evidence-alignment/` | 证据层（证据支撑核查） | 主张—证据对齐：证据清单（数值/统计量/图表/设计标签/强度词）→ E1–E4 机械候选（结论超出数据/强度—设计错配/显著无统计/悬空图表引用）→ verify 门禁（证据不足条必填补什么证据） |
| `skill-c-reasoning-chain/` | 推理层（推理链完整性） | 两端锚定推理审计：设计—措辞对齐矩阵 + R1–R4 候选（因果超出设计/前提未交付/替代解释未讨论/小样本全称结论）→ 每条 finding 强制结论句+前提句双锚点 |
| `skill-d-cross-section-xcheck/` | 结构层（章节衔接一致性） | 双侧锚定跨章核查：X1–X4 确定性候选（摘要—正文数值不一致/引言承诺未交付/图表不配对/缩写未定义）→ 每条 finding 强制 side_a/side_b 双锚点 |
| `skill-e-audit-bench/` | 可验证性（增益证据工程） | 先证明协议有效再上真实案例：内置三篇带植入缺陷的合成基准（p1/p2/p3，p3 干净对照）+ 确定性评分器（召回/精确/误报/复跑 STABLE 判据），基准成绩写入 result.json provenance |

共同原则：所有引擎纯 Python 标准库（≥3.8）、确定性、零依赖；机械候选不等于结论，
定案与严重度判断留给加载 Skill 的 Agent；每条 finding 必须落到句子 id + 逐字 quote +
严重度判据 + 可执行修改建议；扫描件无文本层、章节缺失、被引文献不可得一律如实列入
未检查/待复核，不编造。

每个 bundle 都含 `examples/minimal/`（**合成示例，非正式案例**），
`sh examples/minimal/run_example.sh` 可本地端到端复跑：真实执行脚本、真实生成产物，
并演示门禁对"伪造 quote / 缺锚点 / 空话建议"的拦截。运行契约（/input、/app/work、
/app/output、result.json 含 case_id 与全部 output_contract 字段、诚实 partial）写在各
bundle 的 SKILL.md 中。
