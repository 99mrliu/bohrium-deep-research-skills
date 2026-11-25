# xlang-result-assembly-qc

跨语言检索交付末端的**结果组装与过程质控**：从 case.json 取真实 case_id、镜像
output_contract 全部字段组装 result.json（未供给字段 null＋留痕，绝不编造），
提交前 8 项契约与诚实性自检（case_id / 契约字段 / status 一致 / 命中可回指 /
语种覆盖诚实 / 去重计数说明 / sources 可解析 / 无占位符）。

- 入口说明：[SKILL.md](SKILL.md)
- 检查细则：[references/qc_checklist.md](references/qc_checklist.md)
- 可运行合成示例：[examples/example_walkthrough.md](examples/example_walkthrough.md)

运行环境：Python 3.8+，仅标准库，完全离线。本 Skill 不产生检索内容，
只保证上游证据被完整、诚实、合规地交付。
