# 材料取证与来源登记

挑战：写作05｜文献证据驱动写作（challenge-b810ef56）。五个相互独立的 Skill 之一。

## 重心

上游数据真实性：写作开始前对全部输入材料做哈希登记、文本层提取质量探测、声明对账，来源分级 OK/DEGRADED/UNUSABLE，并提供摘录逐字定位与真实页码回填。

## 结构

- `SKILL.md`：完整操作规程（用途、运行契约、工作流、异常处理、示例、限制）；
- `scripts/`：material_forensics.py（取证+登记）；locate_quote.py（摘录定位+页码）
- `references/`：规则与口径文档；
- `examples/`：可运行的最小示例（**合成示例，非正式案例结果**），
  `examples/output/` 为本地真实运行所得。

## 快速验证

见 `examples/minimal_example.md` 中的命令；全部脚本仅依赖 Python ≥3.9
标准库（PDF 提取可选使用系统 pdftotext）。
