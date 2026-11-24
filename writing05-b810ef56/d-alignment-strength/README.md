# 论断–证据对齐与强度标定

挑战：写作05｜文献证据驱动写作（challenge-b810ef56）。五个相互独立的 Skill 之一。

## 重心

语义对齐判定：对每条论断做逐字锚定、数字保真、方向一致、否定审视四层核验；按研究设计把证据定为 A–D 级并检查成稿措辞是否越级。

## 结构

- `SKILL.md`：完整操作规程（用途、运行契约、工作流、异常处理、示例、限制）；
- `scripts/`：align_check.py（四层对齐核验）；strength_map.py（定级+措辞校准）
- `references/`：规则与口径文档；
- `examples/`：可运行的最小示例（**合成示例，非正式案例结果**），
  `examples/output/` 为本地真实运行所得。

## 快速验证

见 `examples/minimal_example.md` 中的命令；全部脚本仅依赖 Python ≥3.9
标准库（PDF 提取可选使用系统 pdftotext）。
