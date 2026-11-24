# 最小可运行示例（端到端）

> 本示例为合成示例：`input/` 与 `output/` 中的全部数据、文献均为虚构，
> 仅用于演示技能工作流；但下列命令均为真实执行，输出为真实运行结果的摘录，
> 可按原样复现。

## 目录

```
examples/
  input/
    case.json                  # case_id = SYNTH-EXAMPLE-001，output_contract 5 键
    task.md                    # 任务说明
    materials/own_results.md   # 虚构结果：图1/表1/统计输出 → D01–D04
    materials/references.txt   # 4 条虚构文献 → L01–L04
  output/
    anchors.json               # 锚点登记表（步骤2产物）
    claims.json                # 论断台账，6 条论断（步骤3产物）
    discussion.md              # 按台账写成的讨论，句内挂锚（步骤4产物）
    evidence_matrix.md         # build_matrix.py 真实输出
    coverage.json              # build_matrix.py 真实输出
    cite_report.md             # cite_check.py 真实输出
    result.json                # result_contract.py check PASS 的完整结果
```

## 正向流程（全部真实执行，退出码均为 0）

```bash
cd examples/

# 步骤1：初始化 result.json 骨架
python3 ../scripts/result_contract.py init --case input/case.json --out output/result.json
# init OK: output/result.json (case_id=SYNTH-EXAMPLE-001, 契约键 5 个: deliverable, preserved_facts, evidence_map, change_log, limitations_note)

# 步骤5：双审计
python3 ../scripts/build_matrix.py --claims output/claims.json --anchors output/anchors.json \
    --discussion output/discussion.md --out output/evidence_matrix.md --json output/coverage.json
# [INFO] 登记锚点 L01 未被任何论断使用
# 论断 6 条，通过 6 条；ERROR 0 条，INFO 1 条
# PASS

python3 ../scripts/cite_check.py --discussion output/discussion.md \
    --bib input/materials/references.txt --out output/cite_report.md
# [INFO] 文献 L01 未被正文引用（未使用）
# 正文引用 4 处（去重 3），文献表 4 条；ERROR 0，WARN 0，INFO 1
# PASS

# 步骤6：填齐 result.json 后终检
python3 ../scripts/result_contract.py check --case input/case.json --result output/result.json
# [OK] result.json 为合法 JSON
# [OK] case_id 一致: SYNTH-EXAMPLE-001
# [OK] status 合法: complete
# [OK] 契约键齐全且非空或已说明（5/5）
# PASS
```

证据矩阵摘录（output/evidence_matrix.md，真实生成）：

```
| C02 | 孔隙率随固化温度升高而上升的趋势与 Kumar 等的报道一致 | D04, L02 | D04(支持); L02(一致) | 直陈 | 是 | 是 | 是 | OK |
| C04 | 本研究 80 °C 最优的结论与 L03 报道的 100 °C 最优不一致 | D01, L03 | D01(支持); L03(不一致) | 直陈 | 是 | 是 | 是 | OK |
```

注意 L01 的处理：它与本文论断无直接关系，台账与正文均未强行引用，
两个脚本如实记为 INFO——这是"避免只堆引用"的正确姿势，不判失败。

## 负向测试（ seeded errors 全部被捕获，退出码均为 1）

构造两类典型错误：一条**无锚论断**（C01，anchors 为空），一处**引用材料
中不存在的文献**（[L99]）：

```bash
mkdir -p /tmp/negtest
cat > /tmp/negtest/bad_claims.json <<'EOF'
[
  {"id": "C01", "text": "80 °C 组的力学性能全面优于其他各组", "anchors": [], "strength": "直陈"},
  {"id": "C02", "text": "该趋势已被 Smith 等的经典研究反复证实",
   "anchors": [{"id": "L99", "relation": "一致"}], "strength": "直陈"}
]
EOF
cat > /tmp/negtest/bad_discussion.md <<'EOF'
# 讨论
80 °C 组的力学性能全面优于其他各组。该趋势已被 Smith 等的经典研究反复证实，结论与之一致 [L99]。
EOF

python3 ../scripts/build_matrix.py --claims /tmp/negtest/bad_claims.json \
    --anchors output/anchors.json --discussion /tmp/negtest/bad_discussion.md \
    --out /tmp/negtest/bad_matrix.md --json /tmp/negtest/bad_coverage.json
# [ERR] C01 无锚点（孤儿论断），不得进入正文
# [ERR] C02 引用登记表之外的锚点: L99
# [ERR] 正文出现登记表之外的锚点: [L99]
# 论断 2 条，通过 1 条；ERROR 3 条，INFO 8 条
# FAIL            ← 退出码 1

python3 ../scripts/cite_check.py --discussion /tmp/negtest/bad_discussion.md \
    --bib input/materials/references.txt --out /tmp/negtest/bad_cite_report.md
# [ERR] 幻觉引用: 正文引用 [L99]，但文献表中不存在该条目
# 正文引用 1 处（去重 1），文献表 4 条；ERROR 1，WARN 0，INFO 4
# FAIL            ← 退出码 1
```

result_contract.py 的负向行为（篡改 case_id 并删去契约键 evidence_map）：

```bash
python3 ../scripts/result_contract.py check --case input/case.json --result /tmp/negtest/bad_result.json
# [ERR] case_id 与 case.json 不一致: result='TAMPERED-999' case='SYNTH-EXAMPLE-001'
# [ERR] 缺少契约键: evidence_map
# FAIL            ← 退出码 1
```

结论：无锚论断、幻觉引用、未知锚点、篡改 case_id、缺失契约键均会被
确定性脚本拦截，FAIL 必须回到台账或正文修复，无法绕过。
