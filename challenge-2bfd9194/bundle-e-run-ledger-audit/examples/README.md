# 合成示例走查说明（synthetic demo）

**这是合成示例，不是正式案例结果。** synthetic-input/ 与 synthetic-output/ 中的内容均为
演示用合成数据，用于展示 run-ledger-audit 的端到端行为与 WAL/reconcile/replay 证据链。

## synthetic-input/（12 个材料文件 + case.json + task.md）

| 文件 | 覆盖点 |
|---|---|
| notes_alpha.txt / 会议记录-别名.txt | 同内容不同名（别名对，应去重为 duplicate_alias） |
| report_v1.txt / report_最终版.txt | 词干相同内容不同（版本对，应进 version_chains + drafts/） |
| 中文笔记.txt | 中文文件名 |
| a/b/c/d.txt | 深层目录（深度 4，进 PREFLIGHT 深度分布） |
| metadata.csv / observations.csv | 伴随元数据表与数据表（data/） |
| admin_采购备注.txt | 行政版本备注（admin/，声明 v1 已被最终版取代） |
| damaged_simulated.txt | 首行 `X-SIMULATED-CORRUPT` 标记的模拟损坏项（应隔离不复制） |
| scan_发票.txt / supplement_附录A.txt | scans/ 与 supplementary/ 桶 |

## 复跑命令

```
mkdir -p /tmp/r5-test/{input,work,output}
cp -r examples/synthetic-input/* /tmp/r5-test/input/
echo '{"case_id":"synthetic-demo-r5","output_contract":["library_manifest","operations_journal","audit_report","replay_diff"]}' > /tmp/r5-test/input/case.json
echo '合成示例任务：组织资料，保留可复跑证据。' > /tmp/r5-test/input/task.md
python3 scripts/run_case.py all --input /tmp/r5-test/input --work /tmp/r5-test/work --out /tmp/r5-test/output
```

## synthetic-output/ 是什么

本地真实跑出的输出（library/ 实体文件未收录，只收 JSON/JSONL 证据文件）。
其中 operations_journal.jsonl 还包含一次**中断恢复演示**：run1 完成后手工注入了一条
begin 无 done 的记录（id=op_manual_inject，seq=21）和 staging 残留，重跑 apply 时
reconcile 自动清理并补了 seq=22 的 reconciled 记录——之后 AUDIT 仍全 PASS、
REPLAY_DIFF.equal 仍 true、status 仍 complete。

目检要点（均已实测通过）：

- manifest 12 行 = 12 个 input 材料文件，每文件恰一条去向记录；
- duplicates.json 1 组（canonical=notes_alpha.txt，alias=会议记录-别名.txt）；
- version_chains.json 1 链（report_v1 / report_最终版）；
- damaged_simulated.txt 记 skipped_simulated_corrupt，未入库；
- AUDIT_REPORT.json 五项全 PASS；REPLAY_DIFF.json equal=true（复放 10 条 done）；
- result.json status=complete；幂等重跑 journal 零新增行。
