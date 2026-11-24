# 任务（合成示例 synthetic-demo-001）

> **合成示例声明**：本任务与全部材料均为人工构造的演示数据，不代表真实文献追踪案例。

汇总窗口 **2026-W47**（2026-11-16 至 2026-11-22）内三个来源的新增题录：

| 源 | 材料 | 说明 |
| --- | --- | --- |
| crossref_a | `materials/source_a.json` | Crossref 风格快照，正常 |
| eupmc_b | `materials/source_b.json` | Europe PMC 风格快照；第 1 次运行时为截断文件（parse_error），第 2 次运行前被修复版覆盖 |
| publisher_c | `materials/source_c.json` | 出版商简单风格快照，空窗口 |

要求：

1. 全程离线，只读取本地固化材料，不得发起网络请求，不得编造 DOI 或元数据；
2. 每条产出题录必须给出 locator（文件 + JSON 路径）；
3. 失败按故障分类处置：可恢复重试 / 跳过并降级 / 阻断，退避计划确定性记录；
4. 断点续跑：重跑时已完成的「源 × 窗口」直接跳过；
5. 幂等投递：重跑零二次推送；
6. 不可用源进入 `degraded_sources` 并说明原因，`status` 诚实标 `partial`，
   `uncertainty` 明确缺失覆盖；
7. 最终写出 `result.json`，包含 `case.json` 中 `output_contract` 列出的全部字段。
