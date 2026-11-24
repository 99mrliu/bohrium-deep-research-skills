# feasibility-precondition-gate

可行性决策取向的科研选题评估 Skill：五类前提（数据/算力/实验/时间/人员）逐条登记并强制标注 source（带定位）或 assumption（带理由），脚本按门控规则生成可行性结论（feasible / conditional / not_feasible / insufficient_evidence）与风险登记册。详见 [SKILL.md](SKILL.md)。

## 文件

- `SKILL.md`：技能说明与运行时契约；
- `scripts/feasibility_gate.py`：前提门控判定器（G1–G4 门控 + Y1–Y4 一致性检查）；
- `references/precondition_format.md`：台账格式与登记纪律；
- `references/gate_rules.md`：门控规则表与判定语义；
- `examples/`：合成示例（含违例对照），见 `examples/minimal_example.md`。

## 依赖

Python 3.8+ 标准库，无安装步骤。

## 快速自检

按 `examples/minimal_example.md` 两条命令运行；预期退出码 0 / 1。
