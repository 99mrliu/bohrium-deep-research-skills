# budget-aware-verification-scheduler

预算感知核验调度器——让硬性预算（64 模型请求 / 900 秒 / 16384 token）下的核验过程本身**可调度、可检查点化、可审计、可显式降级**。面向专利与技术文献检索核验场景的评测流水线，但机制与领域无关。

GitHub：<https://github.com/99mrliu/bohrium-deep-research-skills/tree/main/patent-litsearch-ad3e9357-v3/j-budget-scheduler>

## 组件

| 路径 | 作用 |
| --- | --- |
| `scripts/budget_ledger.py` | 仅追加式预算账本（JSONL + sha256 链）；`append` / `state` / `verify` |
| `scripts/plan_schedule.py` | 确定性贪心调度器；第 0 步恒为检查点写入；每个决策标注触发规则 |
| `scripts/checkpoint.py` | 检查点写入/恢复；sha256 链式完整性；篡改即拒绝续跑 |
| `scripts/degrade_plan.py` | 止损降级：只填强制契约字段，产出 `degradation_report.json` |
| `scripts/cost_report.py` | 结束成本核算（JSON + 中文 Markdown），可摘录进 result.json |
| `scripts/selfcheck.py` | 合成场景自检（27 项断言），退出码 0 表示通过 |
| `references/` | 成本模型、调度规则、检查点格式三份说明 |
| `examples/` | 端到端 walkthrough（合成示例）与全部夹具 |

所有脚本仅依赖 Python 3 标准库；退出码约定：0 正常 / 1 违反 / 2 用法错误。

## 快速开始

```bash
# 自检（合成数据，约数秒）
python3 scripts/selfcheck.py

# 端到端演示（合成夹具，写入你指定的临时目录）
# 见 examples/example_walkthrough.md 的逐条命令
```

## 设计要点

- **模型不估计成本**：成本只来自队列估计值、策略缺省值与账本实记；调度决策可从账本确定性重放。
- **可交付物先行**：任何计划的第 0 步都是诚实部分骨架的检查点写入。
- **降级是显式决策**：触发阈值后逐项列出被放弃的核验及其对 output_contract 字段的后果，绝不静默丢字段。
- **诚实优先**：部分完成必须点名局限；官方法律状态未知即声明未知；不捏造任何结论。

详细契约见 `SKILL.md`。
