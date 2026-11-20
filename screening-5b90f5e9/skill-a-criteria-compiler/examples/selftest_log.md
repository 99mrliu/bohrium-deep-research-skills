# 真实自测记录（合成示例数据，非真实评测案例）

日期：2026-11-20。环境：macOS arm64，Python 3（仅标准库）。
沙箱：`/tmp/crit-selftest/{input,work,output}` 模拟 `/input`、`/app/work`、`/app/output`。
输入：`example_case.json` → `input/case.json`；`example_records.jsonl` → `input/example_records.jsonl`；另建简版 `task.md`。

## 主流程

| 步骤 | 命令（`$SKILL`=skill 目录，`$T=/tmp/crit-selftest`） | exit | 关键输出 |
|---|---|---|---|
| 0 盘点 | `parse_case.py --input-dir $T/input --work $T/work` | 0 | case_id=synth-demo-01 materials=1 contract_fields=10 |
| 2 骨架 | `scaffold_result.py --work $T/work --output-dir $T/output` | 0 | 骨架字段数=10，status=in_progress |
| 3 归一化 | `normalize_records.py --work $T/work` | 0 | identified=10（0002 大写键名、DOI 前缀被容忍；0007 abstract field_status=unknown） |
| 4 去重 | `exact_dedup.py --work $T/work` | 0 | identified=10 groups=9 duplicates_removed=1 suspected=1（G0001 合并 0001+0002，match_key=doi:10.9999/synth.0001；0009/0010 Jaccard=0.9 仅登记） |
| 5 标准骨架 | `build_criteria_skeleton.py --work $T/work` | 0 | v1.0.0 空表生成；随后 `cp examples/filled_criteria_table.json $T/work/criteria_table.json` |
| 7a 锚定失败注入 | 把 filled_judgments 第 2 行 snippet 改为 "this phrase does not appear anywhere in the record" → `screen_engine.py --judgments bad_judgments.jsonl` | **3** | anchor_failures.json：1 处"evidence_snippet 归一后不是该记录 title/abstract 的子串" |
| 7b 修复重跑 | `cp examples/filled_judgments.jsonl $T/work/judgments.jsonl` → `screen_engine.py --work $T/work` | 0 | screened=9 included=3 excluded=3 needs_human=3 |
| 8 升版回溯演示 | 改 INC1 predicate 升 v1.1.0 → `rejudge_plan.py --old criteria_table_v1.0.0.json --new criteria_table.json` | 0 | changed=[INC1]，affected_record_ids=7 条（凡触及 INC1 的记录全部强制重判）；演示后回滚 |
| 9 计数闭合 | `prisma_check.py --work $T/work` | 0 | CLOSED：10 = 1 + 9；9 = 3 + 3 + 3 |
| 10 填 result.json | 按 SKILL.md 第 4 节映射填充全部 10 个合同字段 | — | status=completed |
| 11 终检 | `selfcheck.py --work $T/work --output-dir $T/output` | 0 | PASS (6/6)：合同字段齐备、产物齐备、路径引用有效、9 条 decisions 均带码、计数闭合 |

## 判定结果（与 example_walkthrough.md 预期一致）

included：G0001(0001)、G0008(0009)、G0009(0010)；excluded：G0002(EX-POPULATION)、G0003(EX-DESIGN)、G0004(EX-OUTCOME)；needs_human：G0005(EX-LANGUAGE)、G0006(EX-NO-ABSTRACT)、G0007(BND-PARTIAL-OVERLAP)。

## 健壮性抽测

| 场景 | 预期 | 实际 |
|---|---|---|
| 重跑 screen_engine（幂等） | exit 0，同计数 | exit 0，9/3/3/3 |
| scaffold_result 重跑无 --force | 保留已有 result.json | 保留，exit 0 |
| parse_case 缺 case.json | exit 2 诚实降级 | exit 2 |
| screen_engine criteria 为空 | exit 2（模型未编译标准） | exit 2 |
| 全部 9 个脚本 `--help` | 正常输出 | 全部 OK |
