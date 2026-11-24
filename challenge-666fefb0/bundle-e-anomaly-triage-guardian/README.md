# anomaly-triage-guardian

科研资料库整理 Skill —— 重心在**异常分诊与诚实降级**：12+1 类分诊 taxonomy、
异常文件 `_quarantine/<类别>/` 原样隔离、单文件异常永不阻塞、状态诚实状态机
（complete/partial/blocked）。

- 技能说明与运行契约：`SKILL.md`
- taxonomy 全文：`references/triage_taxonomy.md`；解析契约：`references/case_contract.md`
- 脚本：`scripts/run_case.py`（init/finalize）、`triage.py`、`inventory.py`、`build_result.py`
- 合成示例：`examples/`（16 文件覆盖 8 类异常）

```bash
cd examples && python3 make_fixture.py && bash run_example.sh
```
