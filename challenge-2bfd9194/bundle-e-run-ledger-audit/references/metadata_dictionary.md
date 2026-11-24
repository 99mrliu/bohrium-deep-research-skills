# 交付物字段字典（metadata dictionary）

## result.json

| 字段 | 类型 | 含义 |
|---|---|---|
| case_id | string | 来自 case.json（递归尝试 case_id/caseId/id/case），取不到为 unknown_case |
| status | string | in_progress / complete / partial / blocked，由 finalize 按证据收口 |
| contract_fields | object | output_contract 字段 → {path, present} 或 {value:null, reason} |
| sources | array | 证据来源（case.json / task.md / input_files） |
| uncertainties | array | 不确定项（缺字段、外部路径、待作答 QA 等） |
| change_records | array | 每个 input 文件一条 {src, dst, action} |
| failures_and_recovery | array | 各阶段异常 {stage, error, at, recovery} |
| limits | array | partial 时的降级项清单（仅 status!=complete 时存在） |
| summary | object | 统计：文件数、重复组、版本链、journal_stats、audit_overall、replay_equal 等 |

## LIBRARY_MANIFEST.jsonl（每行一个 input 文件）

| 字段 | 含义 |
|---|---|
| src | 相对 /input 的路径（NFC） |
| dst | 相对 /app/output 的路径（library/...）；skipped_* 为 null；duplicate_alias 回指 canonical 的 dst |
| sha256 / bytes | 源文件内容哈希与字节数 |
| action | committed / already_committed_identical / duplicate_alias / skipped_simulated_corrupt / skipped_unreadable / failed |
| journal_done_seq | 对应 journal done 记录的 seq（证据回指） |
| canonical / reason | 别名的 canonical 源路径 / 跳过或改名原因 |

## PREFLIGHT.json

- inventory：file_count、total_bytes、depth_distribution（路径段数 → 文件数）、unreadable 清单
- disk：total/used/free/required_with_margin（= total_bytes × 1.2）、margin
- estimated_ops：预计提交操作数（= 可读文件数）
- risks：file_gt_100MB / depth_gt_8 / special_chars_in_name
- status：ok | blocked（blocked 时 blocking_reason 必填）

## duplicates.json

groups[]：{sha256, bytes, canonical（字典序最前者）, aliases[], members[]}。
去重判定只看内容哈希，不看文件名。

## version_chains.json

chains[]：{stem（规范化词干）, ext, members[]（按 mtime 排序）, distinct_hashes,
latest_by_mtime, note}。词干规范化：去扩展名、NFC、小写，循环剥离
`_vN / _final / 最终版 / 定稿 / 终稿 / 最新版 / 修订版 / 修改版 / revN / copy / 副本 / 日期` 后缀。
词干相同且 distinct_hashes ≥ 2 才成链；latest_by_mtime 仅为推断。

## AUDIT_REPORT.json / REPLAY_DIFF.json

见 references/audit_checklist.md 与 references/journal_format.md §不变量。

## QA_LOG.json（仅 task.md 含问题时生成）

items[]：{question, answer, evidence_paths[], status: pending_model_answer | answered}。
answer 必须有 library/ 内证据文件支撑；全部 answered 后重跑 finalize。
