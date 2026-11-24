# 草稿静态检查与质量门禁

挑战：写作05｜文献证据驱动写作（challenge-b810ef56）。五个相互独立的 Skill 之一。

## 重心

过程质量控制：成稿每个事实句带论断标记〔C#〕，lint 脚本做确定性逐句检查（数字溯源、引文闭环、占位符、措辞越级、因果滑移），门禁脚本按策略裁决 PASS/FAIL，FAIL 不许交付。

## 结构

- `SKILL.md`：完整操作规程（用途、运行契约、工作流、异常处理、示例、限制）；
- `scripts/`：draft_lint.py（静态检查）；gate_check.py（门禁裁决）
- `references/`：规则与口径文档；
- `examples/`：可运行的最小示例（**合成示例，非正式案例结果**），
  `examples/output/` 为本地真实运行所得。

## 快速验证

见 `examples/minimal_example.md` 中的命令；全部脚本仅依赖 Python ≥3.9
标准库（PDF 提取可选使用系统 pdftotext）。
