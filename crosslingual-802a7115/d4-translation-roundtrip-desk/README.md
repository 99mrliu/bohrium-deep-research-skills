# xlang-translation-roundtrip-desk

跨语言检索的**受控翻译台账与回译质检**：译名条目化（来源/服务/版本/回译证据）、
回译一致性校验、surface-match-semantic-drift 误译风险标记、逐条使用策略与缺口清单。
工具不自行翻译，译名全部由 Agent 受控供给。

- 入口说明：[SKILL.md](SKILL.md)
- 质检策略：[references/translation_qc_policy.md](references/translation_qc_policy.md)
- 可运行合成示例：[examples/example_walkthrough.md](examples/example_walkthrough.md)
  （`python3 scripts/translation_ledger.py --concepts examples/data/concepts.json --translations examples/data/translations.json --out examples/out`）

运行环境：Python 3.8+，仅标准库，完全离线。
