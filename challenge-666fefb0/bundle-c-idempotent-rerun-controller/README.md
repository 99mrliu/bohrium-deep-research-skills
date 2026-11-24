# idempotent-rerun-controller

科研资料库整理 Skill —— 重心在**过程质量控制**：计划先行（plan_hash）、逐条
journaling、断点续跑、输出树指纹幂等证书、可回滚 undo。

- 技能说明与运行契约：`SKILL.md`
- 协议细则：`references/idempotency_protocol.md`；解析契约：`references/case_contract.md`
- 脚本：`scripts/run_case.py`（init/plan/apply/verify/certify/undo/finalize）、
  `tx_engine.py`、`inventory.py`、`build_result.py`
- 合成示例：`examples/`（含崩溃注入与回滚演示）

```bash
cd examples && python3 make_fixture.py && bash run_example.sh
```
