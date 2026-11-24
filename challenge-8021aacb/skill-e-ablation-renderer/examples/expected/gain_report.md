# 同稿双程对照报告（内部消融）

> **声明**：基线是 `base_pass.py` 生成的机械消融（无锚定、无判据、无操作化），
> 用于量化本 Skill 管线的自身增量；它**不代表平台的基础 Agent**，
> 平台的官方对照由组织方运行，本报告不替代之。

| 指标 | 机械基线 | Skill 管线 | 增量 |
|---|---|---|---|
| findings | 6 | 5 | -1 |
| verifiable_rate | 0.0 | 1.0 | +1 |
| actionable_rate | 0.0 | 0.8 | +0.8 |
| severity_rated | 0.0 | 1.0 | +1 |
| dimension_coverage | 6 | 6 | +0 |

## 读法

- 可核验率：finding 带逐字引文与位置，评审可独立复核的比例；
- 可执行率：action 为操作动词 + 对象，可直接执行的比例；
- 维度有效覆盖：六维中有 finding 或有 how_checked clearance 的维数（满分 6）。

