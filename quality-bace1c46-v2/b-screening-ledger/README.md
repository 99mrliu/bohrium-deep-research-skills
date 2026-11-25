# b-screening-ledger

文献检索**筛选过程**质量审计技能（skill 名：`screening-decision-ledger`）。

把检索—去重—筛选—排序—PRISMA 流程计数变成可审计台账：每条 include/exclude/uncertain
决定都带标准条款 id、中文理由和经机器核验的原文证据引句；不记录理由就什么都不排除，
也绝不发明候选。离线快照专用，无网络、无“最新发表”断言。

- 入口说明：`SKILL.md`
- 标准目录：`references/screening_criteria.md`
- 流程与不变量：`references/prisma_flow.md`
- 脚本：`scripts/init_ledger.py` → `scripts/apply_decisions.py` →
  `scripts/flow_check.py` → `scripts/build_result.py`（仅 Python 3 标准库）
- 可运行合成示例：`examples/`（synthetic，非正式案例结果）
