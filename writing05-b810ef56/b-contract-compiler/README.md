# 交付契约工程

挑战：写作05｜文献证据驱动写作（challenge-b810ef56）。五个相互独立的 Skill 之一。

## 重心

下游交付工程：写作前把 case.json 编译成交付契约清单，写作后由确定性脚本组装并终验 result.json，消灭缺键、键名走样、case_id 不一致、悬空引用、空值冒充完成。

## 结构

- `SKILL.md`：完整操作规程（用途、运行契约、工作流、异常处理、示例、限制）；
- `scripts/`：contract_inspect.py（契约编译）；assemble_result.py（确定性组装）；validate_output.py（终验）
- `references/`：规则与口径文档；
- `examples/`：可运行的最小示例（**合成示例，非正式案例结果**），
  `examples/output/` 为本地真实运行所得。

## 快速验证

见 `examples/minimal_example.md` 中的命令；全部脚本仅依赖 Python ≥3.9
标准库（PDF 提取可选使用系统 pdftotext）。
