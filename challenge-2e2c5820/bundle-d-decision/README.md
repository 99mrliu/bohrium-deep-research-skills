# Bundle D — 多版本决策治理与风险伦理路径

面向 Bohrium Playground 挑战「实验方案可行性评估」（challenge-2e2c5820）的 Skill 包。
重心：**结论的可执行性与治理** —— 评估必须收敛为 PI 能直接行动的决定：可辩护的版本排序、
含降级路径的完整风险登记、伦理/安全审批路线图、以及条件五要素齐全的「有条件可行」裁决。

## 目录结构

```
outputs/
  SKILL.md                        # 技能定义（frontmatter + 中文工作流）
  README.md                       # 本文件
  GITHUB_URL.txt                  # 仓库路径声明
  scripts/
    inspect_case.py               # case.json 模式无关探针（exit 3 = 不可读）
    score_matrix.py               # 决策矩阵 + 加权排序 + 权重 ±20% 敏感性（空证据 exit 2）
    validate_risk_register.py     # 风险登记 lint（缺 5 字段 exit 2；近似重复触发/缺定位警告）
    ethics_path.py                # 伦理审批路径规则分类器（undetermined=确认项，true=需办理）
    check_conditions.py           # 裁决与条件五要素 lint（缺要素 exit 2）
    assemble_result.py            # 汇总 result.json（幂等，非空字段不覆盖，change_record 追加）
  references/
    rubric.md                     # 7 维 0–4 分量规 + 默认权重 + 证据要求
    ethics_rules.json             # 涉及→审批路径规则表（通用模板，以机构规定为准）
    risk_taxonomy.md              # 六类风险：典型触发与标准降级路径
  examples/synthetic/             # 合成示例，非正式案例数据（含一次真实运行的 output/）
```

## 快速验证

```bash
cd examples/synthetic
bash run_example.sh        # 端到端跑通，产物写入 output/，结尾打印 RUN_EXAMPLE_OK
```

## 设计红线

1. 每格分数必须带证据定位 + 逐字引文，空证据被脚本拒绝（exit 2）。
2. `undetermined` 伦理状态永远列为确认项，绝不按「不涉及」处理。
3. 审批路径一律措辞「需办理」，绝不写「已批准」。
4. 「有条件可行」的每条条件必须有责任方、验证方法、阻断性、关联项。
5. result.json 中无法核实的字段保持 null 并写入 uncertainty，禁止编造。

仅依赖 Python 标准库，无网络访问，脚本与 cwd 无关，误用时非零退出并打印原因。
