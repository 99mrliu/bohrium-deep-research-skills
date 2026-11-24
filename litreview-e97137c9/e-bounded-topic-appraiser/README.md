# bounded-topic-appraiser

文献综述生成的"决策端点"Skill：研究空白只能从证据分布里长出来——facet 打标
（population/method/metric/outcome）→ 检测单源主题、未裁决冲突、facet 覆盖缺口并
逐条绑定"已查文献清单"→ 候选选题按语料内新颖度、证据充分度、约束契合度加权评分，
产出 strong/conditional/not_recommended 推荐档位与决策备忘录，而非泛泛的综述结尾。

- 入口说明：`SKILL.md`
- 运行：`python3 scripts/run_case.py init|gaps|appraise|finalize …`（详见 SKILL.md 第 4 节）
- 合成示例：`python3 examples/make_example.py /tmp/bta-demo`（详见 `examples/README.md`）
- 依赖：Python 3 标准库；有 `pdftotext` 时自动用于 PDF，缺失时纯文本材料仍可运行。
