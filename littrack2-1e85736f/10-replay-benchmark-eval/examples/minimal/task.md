# 任务：时间回放基准与增量质量度量（合成示例 case-1e85736f-syn-010）

> 本案例为**合成数据（synthetic）**，仅用于演示与自测，所有文献均为虚构。

## 输入

- `case.json`：含 case_id、时间窗口（2026-11-01 ~ 2026-11-24，两端含）、材料与输出目录、output_contract。
- `materials/snapshot_prev.json`：t_prev（2026-11-14）增量导入状态，6 条记录。
- `materials/snapshot_now.json`：t_now（2026-11-24）当前快照，12 条记录。
- `materials/candidate_new_items.json`：某追踪运行给出的候选新增清单（待评测对象）。
- `materials/run_history.json`：历史运行 run1 的指标记录（回归基线）。

## 要求

1. 对齐两份快照（DOI / arXiv / 标题归一化匹配），构造增量真值：
   - t_now 有而 t_prev 无，且 published 在窗口内 → `new`；
   - published 早于窗口起点（晚入库旧文献）→ `backfill`；
   - published 晚于窗口终点 → `out_of_window`。
2. 用真值评测候选清单：precision / recall / duplicate_rate / false_alert_rate /
   backfill_misclassification，TP/FP/FN 逐条列出并带 locator。
3. 与 run_history 基线对比，按默认阈值标记回归项。
4. 产出 `output/eval_report.md` 与 `output/result.json`（含 output_contract 全部字段）。

## 边界

- 只做测量，不产出自己的 new_items 作为主结果。
- 若材料只有单份快照，无法构造真值，须诚实降级 partial 并说明缺什么。
