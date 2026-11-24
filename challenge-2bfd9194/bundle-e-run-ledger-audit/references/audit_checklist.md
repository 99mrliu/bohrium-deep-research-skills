# 审计清单（AUDIT_REPORT.json 五项检查与处置）

audit_run.py 是独立审计器：不 import 任何业务脚本，只读 /input 与 /app/output，重新核算。
全 PASS 才允许 result.json 报 complete。

## A. input_manifest_coverage

每个 input 材料文件（排除 case.json/task.md）在 LIBRARY_MANIFEST.jsonl 中有且仅有一条
去向记录；记录必须有 dst（skipped_* 类除外，其 dst 为 null 但有 reason）。

- FAIL 常见原因：apply 中途崩溃导致 manifest 未写全；手工删过 manifest 行。
- 处置：重跑 `run_case.py plan` + `apply`（幂等，已入库文件记 already_committed_identical）。

## B. library_done_hash_consistency

library/ 每个文件：存在 dst 相同的 journal done 记录，且 文件实测 sha256 == done 的
sha256_dst == manifest 的 sha256。

- FAIL 常见原因：library 文件被手工改动/删除；journal 被截断。
- 处置：删除可疑文件后重跑 apply（WAL 会重新提交并留新 done）；若 journal 被截断，
  从最早断点重跑全部阶段。

## C. journal_closure

每条 begin 有 done/failed/reconciled 闭合；无 corrupt_line。

- FAIL 常见原因：进程在两次 append 之间被杀；journal 被手工编辑出坏行。
- 处置：重跑 `run_case.py apply` —— 启动 reconcile 会自动清理 staging 残留并补
  reconciled 记录闭合。坏行需人工核对后修复 journal（保留原行备份）。

## D. dup_and_chain_members_exist

duplicates.json 的 canonical/aliases/members 与 version_chains.json 的 members 列出的
文件真实存在于 /input。

- FAIL 常见原因：扫描后 /input 被改动。
- 处置：重跑 scan（duplicates/version_chains 全量重算），再跑后续阶段。

## E. status_consistent_with_evidence

result.json 的 status 与证据一致：

- 有 failed 且无后续同 id done（未恢复）却报 complete → FAIL；
- A–D 任一项 FAIL 却报 complete → FAIL；
- status 取值必须是 in_progress/complete/partial/blocked 之一。

- 处置：该 FAIL 几乎总是"状态写早了"。先修 A–D 的根因，重跑 verify + finalize；
  修不了就让 finalize 如实写 partial 并列 limits，不得手工把 status 改成 complete。

## 审计通过后的第三方复跑

```
python3 replay.py --journal /app/output/operations_journal.jsonl --input /input \
    --out /app/work/replay --library /app/output/library --diff-out /app/output/REPLAY_DIFF.json
```

`REPLAY_DIFF.equal=true` 即"他人仅凭 journal 与 /input 可逐字节复现 library/"的直接证明。
