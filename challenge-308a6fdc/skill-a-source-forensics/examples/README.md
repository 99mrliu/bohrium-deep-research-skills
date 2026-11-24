# 合成示例（非正式案例结果）

本目录演示 source-forensics-kit 的完整跑法。**全部材料为合成示例数据，非真实科研数据；output/ 下为合成示例产物，非正式案例结果。**

## 目录

```
examples/
├── input/                      # 扮演评测时的 /input
│   ├── case.json               # case_id="EXAMPLE-NOT-A-TEST-CASE"，含 output_contract 五键
│   ├── task.md                 # 合成任务：写带锚简报
│   └── materials/              # 三份合成材料（文件头已标注"合成示例数据"）
│       ├── exp_log.txt         # → M2
│       ├── metrics.csv         # → M3
│       └── survey_notes.md     # → M4
└── output/                     # 真实运行脚本生成的产物（见下方命令）
    ├── deliverable.md          # 带锚合成示例稿件（模拟 agent 写作产出）
    ├── manifest.json           # 取证清单（从 work 目录复制）
    ├── anchor_index.json       # 锚点索引（从 work 目录复制）
    ├── audit_report.md         # 锚核验报告
    └── result.json             # 按 output_contract 装配的结果
```

材料编号由 `forensic_intake.py` 按相对路径排序分配：`M1=case.json`、`M2=exp_log.txt`、`M3=metrics.csv`、`M4=survey_notes.md`、`M5=task.md`。

## 复现命令

```bash
cd examples

# 1. 取证建库（input 扮演 /input，/tmp/sf_work 扮演 /app/work）
python3 ../scripts/forensic_intake.py --input input --work /tmp/sf_work

# 2. 查看材料编号 / 类型 / 抽取回执
cat /tmp/sf_work/manifest.json

# 3. 交付稿 output/deliverable.md 已按锚语法写好（真实评测中由 agent 写作）

# 4. 锚核验 + 完整性证明 + 装配 result.json（output 扮演 /app/output）
python3 ../scripts/anchor_audit.py --work /tmp/sf_work --input input \
  --case input/case.json --deliverable output/deliverable.md \
  --output output --note "合成示例，非正式案例结果"

# 5. 把建库产物复制进 output 便于查阅（可选）
cp /tmp/sf_work/manifest.json /tmp/sf_work/anchor_index.json output/
```

预期：锚 10 个全部 OK、无锚事实句 0、完整性 pass、结论 PASS、result.json `status=complete`。

## 负例自测

把交付稿换成含"错锚 + 无锚数字句"的稿子，`--strict` 下退出码为 3，
报告会列出 ANCHOR-MISMATCH / ANCHOR-INVALID / UNANCHORED-CLAIM，例如：

```markdown
模型准确率达到 99.9%[M2:L2]。      <!-- ANCHOR-MISMATCH：锚位原文无 99.9% -->
训练耗时 3 小时。                  <!-- UNANCHORED-CLAIM：含数字却无锚 -->
该结论由专家认定[M9:L1]。          <!-- ANCHOR-INVALID：材料 M9 不存在 -->
```
