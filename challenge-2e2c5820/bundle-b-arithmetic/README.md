# Bundle B — 确定性实算核验中枢（deterministic-arithmetic-feasibility-core）

Bohrium Playground 挑战 **实验方案可行性评估**（challenge-2e2c5820）的 Skill 包。
设计重心：**数值正确性**——模型只做带定位符的结构化抽取；所有算术（预算合计对上限、
进度关键路径对时限、参数域成员、单位归一化）由 Python 脚本以 Decimal 确定性完成，
逐行打印公式与操作数，任何人重跑可得完全相同的数字。

## 目录结构

```
outputs/
  SKILL.md                        # Skill 主文件（工作流 / 结论分级 / 异常处理 / 预算意识）
  README.md                       # 本文件
  GITHUB_URL.txt                  # 仓库地址
  scripts/
    inspect_case.py               # case.json 结构探针（schema 无关，exit 3 = 不可读）
    validate_extraction.py        # 抽取结果校验（exit 2 = 违规并列出）
    recalc_budget.py              # 预算复算：逐行公式 + 申报漂移核对 + 超支/结余 + 精确 delta
    recalc_schedule.py            # 进度实算：DAG/环检测(exit 2)/关键路径/资源占用/时限判定
    check_domains.py              # 参数域判定：枚举/区间 + 单位归一化 + 4 种 verdict
    assemble_result.py            # 装配 result.json：contract 字段兜底、只补不覆盖
  references/
    extraction_schema.md          # 抽取 schema + locator 约定 + 逐字抄数铁律
    units.json                    # 单位归一化表（rpm↔g 不自动换算，请专家复核）
    arithmetic_rules.md           # Decimal/舍入/容差/匹配启发式/诚实铁律
  examples/synthetic/             # 合成示例（非正式案例数据）+ 可复跑流水线 + 实跑产物
```

## 快速验证

```bash
cd examples/synthetic
bash run_example.sh        # 端到端跑 3 个方案版本，exit 0
cat output/budget_v2.md    # 看超支判定与逐行公式
cat output/result.json     # case_id + 全部 contract 字段 + status/sources/uncertainty/change_record
```

负向测试：把任一 extraction 的某步 depends_on 改成环，`recalc_schedule.py` 应 exit 2。

## 退出码约定

| 脚本 | 0 | 非 0 |
|---|---|---|
| inspect_case.py | 成功 | 2 用法错误；3 case.json 不可读/非法 JSON |
| validate_extraction.py | 通过 | 2 违规（全部列出）/文件不可读 |
| recalc_budget.py | 成功（超支是结论不是错误） | 2 用法/读取/无法实算 |
| recalc_schedule.py | 成功 | 2 用法/读取/**依赖环**/无法实算 |
| check_domains.py | 成功 | 2 用法/读取 |
| assemble_result.py | 成功 | 2 用法/case.json 不可读 |

## 环境要求

Python 3.8+，仅标准库（json/decimal/re/argparse/pathlib/glob/datetime），无网络，
绝对路径安全、与 cwd 无关。
