# 任务说明（合成示例 SYNTH-EXAMPLE-001）

> 本示例为完全虚构的合成数据，仅用于演示技能流程。

依据 `materials/factsheet.md` 中的实验事实底稿，撰写论文的「结果」与「讨论」两节初稿，要求：

1. 所有数值必须来自事实底稿，不得虚构；
2. 结果段只陈述观察事实，解释、机制推测、文献对照放入讨论段；
3. 因果、显著性、趋势、幅度等表述的强度须与底稿中的统计证据匹配；
4. 讨论段须包含研究局限。

产出：

- 草稿：`examples/output/draft_v1.md`（初稿 `examples/input/draft_v0.md` 为故意埋入违规的演示稿）
- lint 报告：`examples/output/lint_report_v0.*` 与 `lint_report_v1.*`
- 结果契约：`examples/output/result.json`（须通过 `result_contract.py check`）
