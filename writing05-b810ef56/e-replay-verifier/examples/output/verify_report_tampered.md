# 独立复核报告

复核口径：不信任交付过程，manifest 的全部承诺逐项重算。

通过 14 项，失败 1 项。

| 类别 | 条目 | 结果 | 说明 |
|---|---|---|---|
| HASH | deliverable.md | FAIL | 哈希不符（文件在打包后被改动） |
| HASH | result.json | PASS | 哈希一致 |
| QUOTE | E1 | PASS | 逐字命中 |
| QUOTE | E2 | PASS | 逐字命中 |
| NUMBER | N1 | PASS | 数字 1.8 命中 |
| NUMBER | N2 | PASS | 数字 0.5 命中 |
| REF | [1] | PASS | 著录字段齐备 |
| REF | [2] | PASS | 著录字段齐备 |
| CONTRACT | result.json 可解析 | PASS | JSON 合法 |
| CONTRACT | case_id | PASS | 'SYNTH-DEMO-0005' |
| CONTRACT | 键: change_log | PASS | 存在 |
| CONTRACT | 键: deliverable | PASS | 存在 |
| CONTRACT | 键: evidence_table | PASS | 存在 |
| CONTRACT | 键: limits | PASS | 存在 |
| CONTRACT | 键: uncertainty | PASS | 存在 |

结论：未通过项：HASH:deliverable.md。
