# 端到端走查（合成示例，非真实评测案例）

本目录全部数据为虚构：10 条虚构题录（含 1 对精确重复 0001/0002、1 条中文记录 0006、1 条空摘要 0007、1 条混合人群边界 0008、1 对疑似模糊重复 0009/0010）。

## 步骤与示意输出

```bash
SKILL=<skill 目录>   # 含 scripts/ 的目录
# 模拟运行时装载
mkdir -p /tmp/demo/{input,work,output}
cp examples/example_case.json   /tmp/demo/input/case.json
cp examples/example_records.jsonl /tmp/demo/input/example_records.jsonl
echo "# 任务\n按纳入/排除标准全量筛选题录。" > /tmp/demo/input/task.md

# 0 盘点
python3 $SKILL/scripts/parse_case.py --input-dir /tmp/demo/input --work /tmp/demo/work
# -> case_id=synth-demo-01 materials=1 contract_fields=10

# 2 骨架
python3 $SKILL/scripts/scaffold_result.py --work /tmp/demo/work --output-dir /tmp/demo/output

# 3 归一化（0002 的大写键名与 DOI 前缀被容忍）
python3 $SKILL/scripts/normalize_records.py --work /tmp/demo/work
# -> identified=10

# 4 保守精确去重（0001/0002 归一 DOI 相同 → merge_exact；0009/0010 仅 suspected）
python3 $SKILL/scripts/exact_dedup.py --work /tmp/demo/work
# -> identified=10 groups=9 duplicates_removed=1 suspected=1

# 5 标准骨架（随后用 filled_criteria_table.json 演示模型填充结果）
python3 $SKILL/scripts/build_criteria_skeleton.py --work /tmp/demo/work
cp examples/filled_criteria_table.json /tmp/demo/work/criteria_table.json

# 7 模型判定（用 filled_judgments.jsonl 演示）+ 锚定校验与合成
cp examples/filled_judgments.jsonl /tmp/demo/work/judgments.jsonl
python3 $SKILL/scripts/screen_engine.py --work /tmp/demo/work
# -> screened=9 included=3 excluded=3 needs_human=3 (exit 0)

# 9 计数闭合
python3 $SKILL/scripts/prisma_check.py --work /tmp/demo/work
# -> CLOSED: 10 = 1 + 9；9 = 3 + 3 + 3
```

## 预期判定（演示）

| group | canonical | 结论 | 主理由码 | 说明 |
|---|---|---|---|---|
| G0001 | example_records-0001 | included | IN-ALL-MET | 0002 为精确重复副本 |
| G0002 | example_records-0003 | excluded | EX-POPULATION | 青少年人群（EXC1 fail） |
| G0003 | example_records-0004 | excluded | EX-DESIGN | 回顾性队列（EXC2 fail） |
| G0004 | example_records-0005 | excluded | EX-OUTCOME | 仅 HbA1c（INC3 fail） |
| G0005 | example_records-0006 | needs_human | EX-LANGUAGE | 中文，边界强制转人工 |
| G0006 | example_records-0007 | needs_human | EX-NO-ABSTRACT | 摘要为空，强制转人工 |
| G0007 | example_records-0008 | needs_human | BND-PARTIAL-OVERLAP | 糖尿病/前期混合人群 |
| G0008 | example_records-0009 | included | IN-ALL-MET | |
| G0009 | example_records-0010 | included | IN-ALL-MET | 与 0009 疑似重复但未合并，登记 uncertainty |

真实自测（含故意制造锚定失败验证 exit 3 再修复）的完整命令与退出码见 `selftest_log.md`。
