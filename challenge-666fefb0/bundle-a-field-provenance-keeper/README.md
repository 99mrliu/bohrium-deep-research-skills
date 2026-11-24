# field-provenance-keeper

科研资料库整理 Skill —— 重心在**上游数据真实性**：每个元数据字段携带来源层与
逐字证据，落地前经锚定 lint 机械复验，锚不住一律降级 unknown 并记冲突。

- 技能说明与运行契约：`SKILL.md`
- 解析与证据规则：`references/case_contract.md`、`references/provenance_rules.md`
- 脚本（Python 3 标准库）：`scripts/run_case.py`（init/lint/finalize）、
  `inventory.py`、`provenance_lint.py`、`build_result.py`
- 合成示例：`examples/`（`make_fixture.py` 生成夹具，`run_example.sh` 一键跑通）

快速验证：

```bash
cd examples && python3 make_fixture.py && bash run_example.sh
```
