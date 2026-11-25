# e-contract-exporter

文献研究质量评估的**交付契约 & 人工复核**技能包（skill 名
`contract-review-exporter`）：保证评估交付物契约有效、不完整时诚实
partial、可被第二人复核，且人工修正沉淀回流程。

- `SKILL.md` — 运行时契约与工作流（中文）
- `references/result_contract.md` — result.json 交付契约完整规范
- `references/review_protocol.md` — 人工复核 override 协议与沉淀机制
- `scripts/contract_check.py` — 契约检查器（exit 0/1/2）
- `scripts/apply_overrides.py` — override 受理 + 沉淀报告（恒 exit 0）
- `scripts/render_report.py` — 自包含 HTML 审计报告 + 纯文本预览
- `examples/` — 全合成可运行示例（含真实运行输出摘录）

纯 Python 3 标准库，完全离线。快速验证见 `examples/README.md`。
