# 自测日志（合成示例，非真实评测案例）

环境：macOS arm64，Python 3.12（仅标准库）。工作目录为 bundle 根目录。
以下为 2026-11-25 真实执行的命令与退出码。

## 1. 端到端主流程（全部 exit 0）

```
$ python3 scripts/scaffold_result.py --case examples/case.json --output examples/run
OK: 骨架已落盘 examples/run/result.json；case_id=demo-meta-veracity-001；合同字段 6 个 -> ['field_profile_summary', 'field_trust', 'repair_ledger', 'quarantine', 'language_flags', 'screening_decisions']
[exit code: 0]

$ python3 scripts/profile_fields.py --records examples/synthetic_records.jsonl --case examples/case.json --work examples/run
OK: 9 条记录，10 个字段；domain_flags=1，language_flag=2 -> examples/run/field_profile.json
[exit code: 0]

$ python3 scripts/text_health.py --records examples/synthetic_records.jsonl --work examples/run
OK: 9 条记录；issues=5，修复留痕=3，不可修复=1 -> examples/run/records_text_fixed.jsonl, examples/run/text_health_report.json
[exit code: 0]

$ python3 scripts/repair_fields.py --records examples/run/records_text_fixed.jsonl --work examples/run
OK: 9 条记录；doi 规范化=3，补全=8，冲突未补=8，畸形 DOI=1 -> examples/run/records_final.jsonl, examples/run/repair_ledger.json
[exit code: 0]

$ python3 scripts/trust_scores.py --work examples/run --output examples/run --records-source examples/synthetic_records.jsonl --finalize
OK: 9 条记录；quarantine=2，language_flags=2 -> examples/run/trust_scores.json, examples/run/repair_ledger.json
OK: result.json 已回填，status=partial，未填字段=['screening_decisions']
[exit code: 0]
```

## 2. 幂等性验证

全套 5 条命令连跑两遍，对 `examples/run/` 全部产物取 md5 后 diff：
两次逐字节一致，输出 `IDEMPOTENT OK`（diff 无输出，exit 0）。
注意：第二轮 scaffold 走"增量补键"分支，不覆盖已填充字段；
finalize 不重复追加 uncertainty（已实现去重）。

## 3. 退出码路径（2=运行/IO 错误，3=合同不满足）

```
$ python3 scripts/scaffold_result.py --case /nonexistent/case.json --output /tmp/mvlx
ERROR: case.json 不存在 ...                       [exit code: 2]

$ python3 scripts/scaffold_result.py --case /tmp/mvl_nocontract.json --output /tmp/mvlx
ERROR: case.json 缺 output_contract（合同不满足）  [exit code: 3]

$ python3 scripts/trust_scores.py --work /tmp/mvl_empty --output /tmp/mvlx
ERROR: 缺前置产物 field_profile.json ...           [exit code: 3]

$ python3 scripts/profile_fields.py --records /tmp/mvl_empty.jsonl --work /tmp/mvl_empty
ERROR: 记录为空，无法画像                          [exit code: 3]

$ python3 scripts/profile_fields.py --records /nonexistent.jsonl --work /tmp/mvl_empty
ERROR: 输入文件不存在 ...                          [exit code: 2]
```

## 4. 合规自查

```
$ python3 scripts/selfcheck.py --bundle . --result examples/run/result.json
文件数=19（上限 50） 总字节=124909（上限 2097152）   ← 执行时点
result.json 校验: examples/run/result.json
PASS: 全部检查通过                                    [exit code: 0]
```

（加入 example_walkthrough.md 与本日志后复跑仍为 PASS：21 个文件。）

## 5. 产物目检要点（人工复核记录）

- `run/records_final.jsonl` 中 SCIELO-0003.title == "Influência da
  cafeína na atenção de idosos"（乱码已修复）；其 abstract 仍含原始乱码
  与 U+FFFD（不可修复，未猜改）。
- `run/repair_ledger.json` 中 PUBMED-0002 的 6 条 cross_fill 均
  source_record_id=WOS-0001；OVID-0006 无 journal 补全记录（冲突未补）。
- CNKI-0004 在 `records_final.jsonl` 中 abstract 仍 ""、doi 仍 "N/A"，
  台账无其 change（无强键不补）。
- `run/result.json` 含 case_id + 6 个合同字段 + status/sources/
  uncertainty/change_records；screening_decisions == null 且有
  uncertainty 说明；status == "partial"。
