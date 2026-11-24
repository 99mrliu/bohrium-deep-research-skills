# runbook-governor

科研选题评估技能的**运行可靠性工程**方向：把定时定预算的评测执行变成受治理的状态机。

- 核心脚本：`scripts/runbook.py`（仅标准库）——阶段状态机 + 预算台账 + 契约断点校验 +
  三级降级（L0/L1/L2）+ 危急 triage + finalize 机检。
- 运行契约：`/input`（case.json、task.md、材料）→ `/app/work`（过程产物、run_state.json、
  快照）→ `/app/output`（result.json 含 case_id 与全部 output_contract 字段，诚实 partial）。
- 协议细节：`references/runbook_protocol.md`；状态文件结构：`references/state_format.md`。
- 最小示例（合成）：`examples/`，`bash examples/run_example.sh` 一键复跑。

维护：作者随 Playground challenge-041f89c5 提交；脚本无第三方依赖，Python ≥3.8。
