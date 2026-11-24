# quant-evidence-synth

文献综述生成的"定量证据字段与数值冲突合成"Skill：先把文献中的数值结构化为
"数值+单位+指标+定位"的 quant candidate，按词表做单位归一化（ms→s、g→kg、cm→m、%→ratio），
对同指标同量纲的跨文献数值对做冲突检测（相对差异 >20% 或 CI 不重叠，供模型裁决、不自动调和），
交付前由脚本执行数字回链门控——草稿与证据表中的每个数字必须能回链到某个 quant candidate，
否则就地标 [数值未定位]。

- 入口说明：`SKILL.md`
- 运行：`python3 scripts/run_case.py init|verify|finalize …`（详见 SKILL.md 第 4 节）
- 合成示例：`python3 examples/make_example.py /tmp/qes-demo`（详见 `examples/README.md`）
- 依赖：Python 3 标准库；有 `pdftotext` 时自动用于 PDF，缺失时纯文本材料仍可运行。
