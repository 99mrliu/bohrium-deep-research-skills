# examples — 【合成示例】

本目录所有内容均为**人工构造的合成示例**,不对应任何真实论文或真实评测用例,
仅用于演示 coverage-qc-audit 套件的交付物形态与两道质量门。

## 文件清单

| 文件 | 说明 |
|------|------|
| input/case.json | 合成用例合同(含 output_contract 示例) |
| input/paper.txt | 合成论文,预埋三处缺陷(随机化未描述/只报P值/引文张冠李戴) |
| ledger_valid.json | 有效台账:14 单元,覆盖五个检查面与六个审查面,含全部五态 |
| ledger_tampered.json | **故意篡改**的台账:counts 五数对账错 + 引用不存在的 F-999 |
| run_journal.jsonl | 有效运行日志:22 条,含输入/输出文件真实 sha256,末条 final |
| run_journal_broken.jsonl | **故意破坏**的日志:J-020 的 audit_sheet.md 哈希被置零 |
| audit_sheet_example.md | 审查单样例(与 expected_output/audit_sheet.md 相同) |
| run_example.sh | 一键运行四组校验并核对期望退出码 |
| expected_output/result.json | 合成最终交付物(镜像 case.json 的 output_contract) |
| expected_output/audit_sheet.md | 合成审查单 |
| expected_output/ledger_check_valid_stdout.txt | 有效台账校验输出(PASS) |
| expected_output/ledger_check_tampered_stderr.txt | 篡改台账被拦截的 stderr |
| expected_output/journal_check_valid_stdout.txt | 有效日志校验输出(PASS) |
| expected_output/journal_check_broken_stderr.txt | 坏哈希日志被拦截的 stderr |

## 运行方式

```bash
bash run_example.sh
```

预期:四项全部 “OK”,脚本退出码 0。其中两项为反向用例——
ledger_tampered.json 必须触发五数对账与幽灵 finding 违规,
run_journal_broken.jsonl 必须触发 sha256 不匹配违规——
以此证明两道质量门是真实拦截,而非摆设。

注意:run_journal.jsonl 中声明的输出哈希对应 expected_output/result.json
与 audit_sheet.md 的**初始内容**;run_example.sh 重跑时只刷新四个校验输出
文本,不改变这两个交付文件,故日志哈希保持有效。若手工改动这两个文件,
需同步更新日志中的 sha256。
