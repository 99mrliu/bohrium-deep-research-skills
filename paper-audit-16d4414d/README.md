# paper-audit-16d4414d：论文逻辑与论证审查 — 五份独立 Skill 作品

Bohrium Playground challenge-16d4414d（论文逻辑与论证审查：论文质量审查——发现问题，也给出证据）参赛作品。五份 bundle 相互独立、零共享文件，重心各不相同：

| Bundle | 重心 | 一句话 |
|-|-|-|
| `skill-a-text-fidelity-gate/` | 上游输入保真 | 审查前先证明审查对象是真的：PDF/文本抽取体检 → 保真证书（pass/degraded/fail）→ 句子锚定 → 逐字 quotecheck |
| `skill-b-stat-numeric-recheck/` | 统计数值机审 | 文本内可重算的数值主张全部确定性重算：p 值 vs 措辞、百分比 vs 分数、CI、不可能值、跨章节口径、方向冲突（C1–C6） |
| `skill-c-citation-support-auditor/` | 文献引用层 | 引用对账（引而未列/列而未引/断号）机判定案；被引文献支持度只立案不定案，取不到原文一律待复核 |
| `skill-d-audit-process-qc/` | 审查过程质控 | 原子检查点、覆盖台账、预算安全网（40/56）、复跑 STABLE/DRIFT、finalize 诚实门禁（有未检查项禁止 success） |
| `skill-e-severity-revision-compiler/` | 下游交付工程 | 三维定级依据 + 空话词表门禁 + 修复优先级队列 + 编译 report.md / result_fields.json |

共同原则：所有引擎纯 Python 标准库（≥3.8）、确定性、零依赖；工具只产出候选与证书，判断留给 Agent；每条 finding 必须带句子 id + 逐字 quote + 严重度 + 可执行修改建议；截断/无文本层/材料缺失如实列入未检查项，不编造。

每个 bundle 都含 `examples/minimal/`（**合成示例，非正式案例**），`sh examples/minimal/run_example.sh` 可本地端到端复跑，产物真实生成。
