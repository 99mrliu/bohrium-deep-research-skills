# 可复核性工程（第三方一键重验包）

挑战：写作05｜文献证据驱动写作（challenge-b810ef56）。五个相互独立的 Skill 之一。

## 重心

交付后可复核性：把产物文件哈希、逐字摘录、关键数字、文献条目、契约键固化为核验清单，复核方不调用模型、不信任交付过程即可一条命令重验全部承诺。

## 结构

- `SKILL.md`：完整操作规程（用途、运行契约、工作流、异常处理、示例、限制）；
- `scripts/`：pack_manifest.py（生成核验清单）；verify_pack.py（独立重验）
- `references/`：规则与口径文档；
- `examples/`：可运行的最小示例（**合成示例，非正式案例结果**），
  `examples/output/` 为本地真实运行所得。

## 快速验证

见 `examples/minimal_example.md` 中的命令；全部脚本仅依赖 Python ≥3.9
标准库（PDF 提取可选使用系统 pdftotext）。
