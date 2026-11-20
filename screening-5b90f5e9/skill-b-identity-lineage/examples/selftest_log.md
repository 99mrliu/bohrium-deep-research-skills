# 真实自测记录（selftest_log）

环境：macOS arm64，Python 3（仅标准库），日期 2026-11-20。
模拟平台运行时：`/tmp/sim-skill-b/{input,work,output}` 分别扮演 `/input`、`/app/work`、`/app/output`。
输入为 `examples/` 下的**虚构合成数据**（example_case.json + 两个来源导出）。

## 准备

```bash
SIM=/tmp/sim-skill-b
mkdir -p "$SIM/input/example_exports" "$SIM/work" "$SIM/output"
cp examples/example_case.json "$SIM/input/case.json"
cp examples/example_exports/* "$SIM/input/example_exports/"
printf '# 示例任务\n' > "$SIM/input/task.md"
```

## 正向全流程（每步实际退出码）

| # | 命令 | 实际输出摘要 | exit |
|---|---|---|---|
| 1 | `parse_case.py --input-dir $SIM/input --work $SIM/work` | case_id=example-synthetic-01, materials=2, warnings=0 | 0 |
| 2 | `scaffold_result.py --work $SIM/work --output-dir $SIM/output` | 骨架 10 字段（output_contract） | 0 |
| 3 | `import_records.py --work $SIM/work` | records=10, files=2, warnings=0 | 0 |
| 4 | `identity_resolve.py --work $SIM/work` | pairs_evaluated=11, auto_merge=2 (1×Tier1 DOI, 1×Tier2 题名), pending=2, keep_separate=7, auto_clusters=8 | 0 |
| 5 | `apply_arbitration.py --work $SIM/work`（filled_arbitrations.json） | clusters=7, merges=1, splits=1 | 0 |
| 6 | `build_canonical.py --work $SIM/work` | canonical=7, conflicts=4（DOI 前缀差异、题名变体、预印本×正式版年份与 venue） | 0 |
| 7 | `screen_canonical.py --work $SIM/work`（filled_screen_judgments.jsonl） | screened=7, included=3, excluded=3, needs_human=1, propagated=3, closure=true | 0 |
| 8 | `audit_check.py --work $SIM/work` | ok=true，全部 8 项检查通过（identified=10=7+3；screened=7=3+3+1；谱系副本数一致；传播=合并副本数） | 0 |
| 9 | `fill_result.py --work $SIM/work --output-dir $SIM/output` | status=completed, pending_fields=[] | 0 |
| 10 | `selfcheck.py --work $SIM/work --output-dir $SIM/output` | all passed | 0 |

## 负向验证（故意失败，均按预期拒绝）

| # | 操作 | 结果 | exit |
|---|---|---|---|
| N1 | 把 can-007 的 evidence_quote 替换为伪造句子 | `anchor_failures.json` 落盘，提示"非 title/abstract 子串"，修复后重跑步骤 7 恢复 exit 0 | **3**（符合预期） |
| N2 | 把仲裁 rationale 置空后跑 apply_arbitration.py | `arbitration_errors.json`：「rationale 为空（合并/拆分都必须有依据）」 | **3**（符合预期） |

## 幂等与契约行为

| 操作 | 结果 | exit |
|---|---|---|
| 重跑 identity_resolve.py / audit_check.py / selfcheck.py | 输出一致，审计仍全过 | 0 |
| result.json 已存在时重跑 scaffold_result.py（不带 --force） | skipped，已填充的 status=completed 不被覆盖 | 0 |
| 全部 10 个脚本 `--help` | 正常打印用法 | 0 |

## 关键中间产物核对（合成数据）

- Tier3 pending 对恰为 `source_a-003|source_b-003`（Jaccard 1.0，年份差 1）与
  `source_a-004|source_b-004`（Jaccard 0.9，同年同首作者）——前者仲裁 merge
  （版本谱系：canonical=正式版 source_b-003），后者仲裁 split（不同人群/DOI/期刊）。
- 7 个 canonical：can-001..can-007，与 filled_screen_judgments.jsonl 一一对应。
- conflict_log.jsonl 4 条：clu-001 DOI 前缀形式差异；clu-002 原始题名变体；
  clu-003 年份（2021 vs 2022）与 venue（arXiv vs 期刊）冲突，resolution 取正式版。
