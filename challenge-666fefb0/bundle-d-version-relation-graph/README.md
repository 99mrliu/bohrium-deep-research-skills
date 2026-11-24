# version-relation-graph

科研资料库整理 Skill —— 重心在**版本关系语义图谱**：六类信号构建 typed-edge
有向图（duplicate_of/same_work/version_of/supplement_of），canonical 显式打分
裁决、证据不足诚实为 null，同题异版全部保留。

- 技能说明与运行契约：`SKILL.md`
- 图谱语义：`references/graph_semantics.md`；解析契约：`references/case_contract.md`
- 脚本：`scripts/run_case.py`（init/graph/finalize）、`graph_build.py`、
  `inventory.py`、`build_result.py`
- 合成示例：`examples/`（`make_fixture.py` + `run_example.sh` 一键跑通）

```bash
cd examples && python3 make_fixture.py && bash run_example.sh
```
