# 自测日志（selftest_log）

> **合成示例，非真实评测案例。** 以下命令于 2026-11-25 在 macOS（darwin 24.6.0 arm64）、
> Python 3（标准库，无第三方依赖）下，于 bundle 根目录逐条真实执行；exit code 为当时实测值。

## 正例链路

| # | 命令（简写，`python3 scripts/` 前缀） | exit |
|---|---|---|
| 1 | `contract_probe.py --input examples/input --work examples/work` | **0** |
| 2 | `scaffold_result.py --work examples/work --output examples/output` | **0** |
| 3 | `fill_ledger.py --work examples/work --output examples/output mark --field decisions --state filled --source examples/work/decisions.json --value "$(cat examples/work/decisions.json)"` | **0** |
| 4 | 同上，`--field dedup_report --source examples/work/dedup_report.json` | **0** |
| 5 | 同上，`--field conflict_resolutions --source examples/work/conflict_resolutions.json` | **0** |
| 6 | `fill_ledger.py … mark --field screening_summary --state filled --value '{"records_total":5,"included":3,"excluded":1,"deduplicated":1,"conflicts_resolved":1}'` | **0** |
| 7 | `fill_ledger.py … mark --field limits --state null_with_reason`（**故意不带 --reason**） | **3**（stderr: `ERROR: null_with_reason 必须提供非空 --reason（禁止静默空字段）`） |
| 8 | `fill_ledger.py … mark --field limits --state null_with_reason --reason "合成演示：有限快照、无实时库，检索结果不可外推，limits 无法给出完整结论"` | **0** |
| 9 | `fill_ledger.py … mark --field uncertainty --state filled --value '["合成演示：R05 冲突意见调解无法核验组织方预期","合成演示：有限快照、无实时库"]'` | **0** |
| 10 | `fill_ledger.py … mark --field sources --state filled --value '["examples/input/case.json",…,"examples/work/conflict_resolutions.json"]'` | **0** |
| 11 | `fill_ledger.py … mark --field status --state filled --value '"partial"'` | **0** |
| 12 | `validate_result.py --work examples/work --output examples/output` | **0**（V1–V7 全 PASS，verdict=PASS，报告落 `examples/output/validation_report.json`） |
| 13 | `fill_ledger.py --work examples/work --output examples/output report --strict` | **0**（filled=9 / null_with_reason=1 / pending=0） |

步骤 1 的 stderr 留痕（合同形态，属正常探测记录，不影响 exit 0）：
`WARN: contract_shape: list from case.json.fields`、`WARN: contract_shape: free-text markdown section from task.md`。

## 负例（校验门拦截）

| # | 命令 | exit |
|---|---|---|
| 14 | 复制正例 result.json 后用 python3 删除字段 `conflict_resolutions`，写入 `examples/negative/output/result.json` | 0（构造步骤） |
| 15 | `validate_result.py --work examples/work --output examples/output --result examples/negative/output/result.json --report examples/negative/output/validation_report.json` | **3**（`[FAIL] V2_FIELDS_PRESENT: 缺失合同字段: ['conflict_resolutions']`，verdict=FAIL，其余 6 项 PASS） |

## 幂等性验证

| # | 命令 | exit |
|---|---|---|
| 16 | 重跑 `contract_probe.py`（同 #1） | **0** |
| 17 | 重跑 `scaffold_result.py`（同 #2） | **0**（不覆盖已有填充，stderr 无） |
| 18 | 重跑 `mark --field decisions`（同 #3，同值同来源） | **0**（台账历史只刷新时间戳） |
| 19 | 重跑 `validate_result.py`（同 #12） | **0** |
| 20 | python3 逐键比较重跑前后 result.json 业务内容（剔除 change_records 审计流水） | **一致（True）** |

## 平台约束自查

| # | 命令 | exit |
|---|---|---|
| 21 | `python3 scripts/selfcheck.py` | **0**（files=19/50，total=76341B/2097152B，全 UTF-8，无符号链接，frontmatter 合法；最终版含文档后为 22 个文件，见文末复跑） |

## 目检结论

- `examples/output/result.json`：case_id 与输入一致；status=partial；五个合同字段全部就位，
  `limits: null` 且台账记录 reason；`sources`/`uncertainty` 非空；`change_records` 含骨架初始化与全部 8 次字段标记，可审计回放。
- `examples/work/fill_ledger.json`：10 个字段 fill_state 齐全（filled=9、null_with_reason=1、pending=0），
  filled 字段的来源产物路径真实存在。
- `examples/output/validation_report.json` / `examples/negative/output/validation_report.json`：
  正例 verdict=PASS（violations=0），负例 verdict=FAIL（violations=1，V2 拦截）。
- 负例仅删一个字段即被拦截，证明校验门对"不得删字段"是硬约束而非口头检查。
