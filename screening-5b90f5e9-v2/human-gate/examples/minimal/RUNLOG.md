# 最小示例运行记录（合成示例）

> 本示例的判定、标注者标签与"人工决定"全部为**合成演示数据**；
> 真实场景 human_decisions.csv 必须由研究者本人填写。

## 输入

- `decisions.json`：10 条合成判定，覆盖全部触发器——rec-005 无摘要（T1）、
  rec-006 语种不符（T2）、rec-004 人群部分重叠（T3）、rec-008 双标注者
  冲突（T4，A=included/B=excluded）、rec-007 纳入建议无证据片段（T5）、
  rec-009 标准歧义（T6）；其余 4 条无触发器。
- `human_decisions_complete.csv`：6 行队列全覆盖，含 2 条带理由的推翻
  （rec-005→needs_fulltext、rec-007→excluded）。
- `human_decisions_partial.csv`：故意残缺——rec-007 推翻无理由（V4 拒）、
  rec-003 不在队列（V1 拒）、rec-009 未决定。

## 实际执行与结果（2026-11-24，Python 3，macOS arm64）

```text
TRIAGE queued=6 auto=4 (P1=2 P2=2 P3=2)
MERGE COMPLETE:   accepted=6 confirmed=4 overridden=2 unresolved=0 rejected=0   exit 0
MERGE INCOMPLETE: accepted=4 confirmed=3 overridden=1 unresolved=2 rejected=2   exit 3
EXAMPLE PASS
```

退出码 0；重跑结论一致。

## 产物目检结论（output/）

- `review_queue.json`：队列 6 条按 P1→P3 排序，每条带 queue_reasons 与
  `suggestion_status=pending_human_confirmation`；auto_accepted 4 条登记
  `auto_accepted_below_gate`；stats 分布与上面数字一致。
- `complete/final_decisions.json`：10 条齐备——队列记录 final_label 来自
  人工表，rec-005/rec-007 标 human_overridden 且 rationale 非空；
  `confirmation_ledger.json`：override_rate=2/6≈0.333。
- `partial/confirmation_ledger.json`：rejected_rows 两行原因分别为
  `V4-override-without-rationale`、`V1-record-not-in-queue`；
  unresolved=[rec-007, rec-009]（rec-007 因决定被拒回到未决），exit 3
  如实阻断——演示"人工复核未完成不得声称完成"的硬门。
