# c-anchor-gate / evidence-anchor-gate

文献研究质量评估的**证据锚定与门控**技能：把证据定位从章节级推进到 `p<页>.¶<段>` 级，
用脚本建立锚点索引，再对模型提交的"判断 + 逐字摘录 + 定位符"做归一化子串门控。
找不到原文的摘录不放行，判断降级为弃权；页码标错但摘录真实存在的，自动修复定位并留痕。

- `SKILL.md` — 运行时契约（中文）
- `references/anchoring.md` — 锚点语法、归一化、匹配算法、四种门控裁决
- `scripts/build_index.py` — 文档发现 + 页/段锚点索引
- `scripts/gate.py` — 摘录门控（verified / repaired_locator / verified_span / abstain_*）
- `scripts/build_result.py` — 组装 result.json + evidence_table.md
- `examples/` — 全合成最小示例（含真实运行输出摘录）

仅依赖 Python 3 标准库；PDF 文本抽取用系统 `pdftotext`（缺失时优雅降级）。无网络访问。
