# contract-first-deliverables

下游交付工程取向的科研选题评估 Skill：output_contract 先编译成 result.json 骨架，各阶段只回填不重构，交付前契约机检，人读报告由结构化载荷确定性渲染。详见 [SKILL.md](SKILL.md)。

## 文件

- `SKILL.md`：技能说明与运行时契约；
- `scripts/contract_scaffold.py`：case.json → result.json 骨架 + 契约字段清单；
- `scripts/contract_validate.py`：交付前契约合规机检（case_id、字段齐全、status 与回填一致）；
- `scripts/render_review_pack.py`：payload.json → evaluation_report.md + evidence_matrix.md（确定性渲染）；
- `references/contract_binding.md`：契约形态兼容与绑定纪律；
- `references/payload_format.md`：载荷结构与渲染纪律；
- `examples/`：合成示例，运行方式见 `examples/minimal_example.md`。

## 依赖

Python 3.8+ 标准库，无安装步骤。

## 快速自检

按 `examples/minimal_example.md` 四条命令依次运行；第 3 条退出码 0、第 4 条退出码 1（示例故意违约）即为正常。
