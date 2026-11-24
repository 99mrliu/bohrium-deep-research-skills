# 过程质量控制报告(process-qc-guard)

- case_id: `synthetic-qc-guard-001`
- 工具: `qc_guard.py` v1.0.0
- 最终状态: **success**

## 交付前自查门(pre-delivery self-check gate)

| 检查项 | 结果 | 证据 | 说明 |
|---|---|---|---|
| `contract_completeness` | **PASS** | `result.json` | 缺失=无;未声明的 null=无 |
| `artifact_hashes` | **PASS** | `result.json#artifacts` | 全部 4 个产物哈希一致(qc_report.md 为报告本身,其哈希于门后写入,不参与本检查) |
| `count_conservation` | **PASS** | `work/normalized_records.json;work/merged_records.json` | per_source 合计=9,规范化总数=9,合并成员合计=9 |
| `decision_log_completeness` | **PASS** | `work/decision_log.json` | 日志条目=7;队列对=1;均含 reason_code=是 |
| `arbitration_queue_resolved_or_explicit` | **PASS** | `work/arbitration_queue.json` | 仲裁队列为空(全部已决或无候选) |
| `replay_stable` | **PASS** | `work/replay_verdict.json` | verdict=STABLE,differing=无 |
| `honest_partial` | **PASS** | `result.json` | success 且无待决/未解字段 |

## 重放一致性(replay consistency)

- 判定: **STABLE**
- 比对产物文件数: 20
- 差异文件: 无

## 阶段账本摘要(逻辑序号,无墙钟)

| seq | 事件 | 阶段 |
|---|---|---|
| 0 | `run_plan_written` | `-` |
| 1 | `stage_completed` | `intake` |
| 2 | `stage_completed` | `normalize` |
| 3 | `stage_completed` | `identity` |
| 4 | `stage_completed` | `coverage` |
| 5 | `gate_completed` | `report` |
| 6 | `stage_completed` | `report` |
| 7 | `run_plan_written` | `-` |
| 8 | `stage_skipped` | `intake` |
| 9 | `stage_skipped` | `normalize` |
| 10 | `stale_detected` | `identity` |
| 11 | `stage_completed` | `identity` |
| 12 | `stage_skipped` | `coverage` |
| 13 | `stale_detected` | `report` |
| 14 | `gate_completed` | `report` |
| 15 | `stage_completed` | `report` |
| 16 | `replay_completed` | `-` |
| 17 | `stale_detected` | `report` |

## 预算包线(budget envelope)

- 模型请求上限 64 / 时限 900s;本流水线全部阶段为脚本化执行(0 模型请求)。
- 唯一模型判断点: identity 阶段模糊重复对仲裁,单次批量请求(队列空则 0 次)。
- 详见 `references/budget-and-checkpoints.md`。

## 备注

- `qc_report.md` 自身的 sha256 写入 `result.json.artifacts`,但不参与 `artifact_hashes` 自查(避免自引用)。
- 全部产物不含墙钟时间与绝对路径;账本仅使用逻辑序号。
- 状态语义: `success`=全部通过;`partial`=诚实降级(原因见 `result.json.uncertainty`);`input_error`=输入非法。
