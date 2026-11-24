# 回放验证方法（replay-verification）

本 skill 的中心承诺：**每一次增量判定都能拿出可回放的证据**。
回放不是重新检索，而是用冻结的输入材料 + journal 历史，逐字节复算某一轮的
全部判定，并输出机器可核验的 diff 报告。

## 1. 回放算法（replayer.py）

对目标 `run_id`：

1. 从 `increment_journal.jsonl` 读出全部 run 记录，定位目标行 `T`，
   取其之前的记录 `runs[:T]`；
2. 取该轮对应的 **previous snapshot**（即该轮 record_run 时的
   `--snapshot-in`），与 `runs[:T]` 一起重建注册表（`registry_from`）与水位；
3. 重新加载该轮的源响应文件（路径记录在 run 记录的 `sources[].locator_file`），
   用与 record_run **完全相同**的纯函数 `journal_lib.process_run` 重算：
   `run_id`、`input_digest`、`counts`、`events`、`deliveries`、`watermarks_after`；
4. 对每个字段分别计算 canonical JSON 的 sha256，与 journal 记录比对；
5. 输出 `replay_diff.json`。

## 2. replay_diff.json 语义

| 字段 | 含义 |
|---|---|
| `status` | `consistent`（全部字段逐字节一致）/ `inconsistent` |
| `byte_equal` | 所有 checks 均 equal 时为 true |
| `checks[]` | 每字段 `{field, recorded_sha256, replayed_sha256, equal}` |
| `mismatches[]` | 不一致时的定位：`{event_index, field, recorded, replayed, reason}` |
| `journal_line` | 目标记录在 journal 中的行号（1 起） |

`status=consistent` 的读法：**状态重建（snapshot + 历史 journal）与判定
规则（dedup 链 + 窗口过滤）共同完备**，任何人拿到同样材料都能复现同样清单。

## 3. 常见不一致原因（排查指引）

- `input_digest` 不等 → 源文件被改动 / 传错了该轮的材料；
- `events` 不等但 `input_digest` 相等 → 判定代码或 snapshot 版本错位，
  用 `mismatches` 的逐事件逐字段 diff 定位；
- `watermarks_after` 不等 → 水位推进规则变化（如日期解析口径调整）；
- `run_id` 不在 journal → 传错 run_id 或 journal 被截断。

## 4. 幂等性校验（idempotency_check.py）

与回放互补：回放证明“同样输入复算同样结果”，幂等证明“同样一轮不重复入账”。

1. 把 journal 与 snapshot-in 复制到临时目录；
2. 用与正式运行完全相同的参数再跑一次 `record_run.py`；
3. 通过条件（全部满足才 `status=pass`）：
   - summary `appended=false`（命中 `run-already-recorded-idempotent-noop`）；
   - 临时 journal 与原 journal **逐字节相同**（零追加）；
   - `new + version_updates = 0` 且 `deliveries = 0`（零二次投递）。

## 5. 结果归档

`replay_diff.json` 与 `idempotency_report.json` 的路径与结论必须汇入最终
`result.json` 的 `replay_verification` / `idempotency_verification` 字段，
连同 journal 的 sha256（`journal_ref`）一起构成完整证据链。
