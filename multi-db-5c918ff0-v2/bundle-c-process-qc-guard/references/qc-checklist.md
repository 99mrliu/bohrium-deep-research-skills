# 交付前自查门(Pre-Delivery Self-Check Gate)检查清单

本清单枚举 `scripts/qc_guard.py` 在 report 阶段末尾、交付 `/app/output` 之前
**必须**逐项执行的检查。每项给出 PASS 判据与证据指针(evidence pointer)。
任一 FAIL → `result.json.status` 保持/降级为 `partial`,并在 `uncertainty`
中给出精确原因;绝不带 FAIL 交付 success。

检查结果汇总于 `/app/output/qc_report.md` 的"交付前自查门"表格。

| # | 检查项 id | PASS 判据 | 证据指针 |
|---|---|---|---|
| 1 | `contract_completeness` | `case.json.output_contract` 中每个字段都作为顶层键出现在 `result.json`;值为 `null` 的字段必须已列入 `unresolved_contract_fields` 并附原因(绝不捏造) | `result.json` |
| 2 | `artifact_hashes` | `result.json.artifacts` 中每个 `path` 存在且重新计算的 sha256 与登记值一致。例外:`qc_report.md` 是报告本身,其哈希在门后写入 `result.json.artifacts`,不参与本检查(避免自引用) | `result.json#artifacts` |
| 3 | `count_conservation` | `sum(per_source_counts) == total == len(records)`(normalize 产物),且合并记录成员数合计等于规范化记录总数(identity 产物):无任何记录被静默丢弃或复制 | `work/normalized_records.json`;`work/merged_records.json` |
| 4 | `decision_log_completeness` | `decision_log.json` 每条条目都含 `decision` 与 `reason_code`;`arbitration_queue.json` 中每个 `pair_id` 都在日志中有对应条目 | `work/decision_log.json` |
| 5 | `arbitration_queue_resolved_or_explicit` | 仲裁队列为空(无候选或全部已决);**或**存在待决对且 `status == "partial"` 并在 `uncertainty` 中逐对显式声明。模糊重复对**绝不自动合并** | `work/arbitration_queue.json`;`result.json#uncertainty` |
| 6 | `replay_stable` | `work/replay_verdict.json` 存在,`verdict == "STABLE"`,且其 `case_sha256` 与当前 `case.json` 的 sha256 一致 | `work/replay_verdict.json` |
| 7 | `honest_partial` | 若 `status == "success"`:无待决仲裁对、无未解契约字段;若 `status == "partial"`:`uncertainty` 非空且精确说明原因;骨架状态(运行刚开始写出的 partial)亦属诚实中间态 | `result.json` |

## 与阶段不变量的关系

自查门是**交付前**的最后一道闸;阶段不变量(stage invariants)是**运行中**
每阶段的即时校验,二者互补:

- intake: `every_discovered_material_classified`(所有发现的材料均被分类,无一静默丢弃)
- normalize: `record_counts_conserved`(各源计数之和 = 规范化总数)
- identity: `every_pair_decision_logged_with_reason_code`、
  `merge_partition_conserves_records`、`queued_pairs_all_logged`
- coverage: `coverage_matrix_recomputes_from_merged_records`
- report: `all_contract_fields_present`

任一阶段不变量失败 → 该阶段检查点标记 `invariant_failed`,流水线抛出
`QCFailure`,顶层兜底写出诚实 partial 并以退出码 2 结束。
