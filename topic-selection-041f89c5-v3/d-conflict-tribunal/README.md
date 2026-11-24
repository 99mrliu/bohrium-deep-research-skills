# conflict-tribunal

科研选题评估技能的**冲突证据对抗裁决**方向：每个关键断言必须配一次登记在案的
对抗检索，裁决由显式准则机械作出，裁不动的冲突双方并列。

- 核心脚本：`scripts/docket.py`（仅标准库）——`lint` 机检卷宗完整性
  （无对抗检索记录即违例）；`adjudicate` 按 直接性 > 证据类型 > 方法严谨度 > 时效
  裁决，产出裁决报告与冲突登记册。
- 运行契约：`/input` → `/app/work`（docket.jsonl、tribunal 报告）→ `/app/output`
  （result.json 含 case_id 与全部 output_contract 字段，诚实 partial；卷宗随附）。
- 格式与准则：`references/docket_format.md`、`references/adjudication_rules.md`。
- 最小示例（合成）：`examples/`，`bash examples/run_example.sh` 一键复跑。

维护：作者随 Playground challenge-041f89c5 提交；Python ≥3.8，无第三方依赖。
