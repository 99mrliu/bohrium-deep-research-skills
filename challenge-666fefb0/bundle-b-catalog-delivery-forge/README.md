# catalog-delivery-forge

科研资料库整理 Skill —— 重心在**下游交付渲染工程**：整理结论必须落成四件套
可复核交付物（catalog.md / catalog.csv / tree_diff.md / verify_report.md），
脚本先出确定性提案、模型只写覆盖项。

- 技能说明与运行契约：`SKILL.md`
- 格式契约：`references/catalog_format.md`；解析契约：`references/case_contract.md`
- 脚本：`scripts/run_case.py`（init/finalize）、`inventory.py`、
  `render_catalog.py`、`build_result.py`
- 合成示例：`examples/`（`make_fixture.py` + `run_example.sh` 一键跑通）

```bash
cd examples && python3 make_fixture.py && bash run_example.sh
```
