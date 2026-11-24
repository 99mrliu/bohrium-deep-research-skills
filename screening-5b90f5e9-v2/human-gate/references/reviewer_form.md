# 复核者填写规范（human_decisions.csv）

## 列定义

| 列 | 必填 | 说明 |
|---|---|---|
| record_id | 是 | 必须与 review_queue.json 中的 record_id 完全一致 |
| reviewer_id | 是 | 复核者标识（姓名缩写/工号）；仲裁记录建议注明 arbitrator: |
| final_label | 是 | included / excluded / needs_fulltext 三选一 |
| rationale | 条件必填 | final_label 与模型建议不同时必填（V4）；一致时可空 |

## 填写纪律

- 每条队列记录至多一行决定（V5）；改主意时修正原行而不是追加新行；
- 不要给队列外的记录写决定（V1 拒绝）——如果认为某条自动放行的记录
  判错了，正确做法是把它补进队列（重跑 triage 并加 boundary_flags）
  再回填，让审计链完整；
- needs_fulltext 用于"题录层面无法定夺、需要全文"的记录，它不是
  included 的近义词，进入全文获取清单；
- 复核者只回答"这条记录按当前标准何去何从"，标准本身的修改走
  标准版本管理流程，不在本表单内完成。

## 校验一览（merge_review.py）

V1 在队列内；V2 reviewer 非空；V3 标签合法；V4 推翻必带理由；
V5 不可重复。被拒行进入 confirmation_ledger.json 的 rejected_rows，
逐行给出原因——被拒不等于丢失，修正后重跑即可并入。
