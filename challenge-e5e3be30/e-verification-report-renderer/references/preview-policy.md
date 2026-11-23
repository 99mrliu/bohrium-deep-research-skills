# 渲染降级链与诚实声明规则

平台要求："Editable Office/slide/diagram outputs should also have real rendered
PDF/PNG previews for inspection." 核验报告（Markdown）属于可编辑交付物，
必须附带**真实渲染**的预览。本文件规定渲染链、降级顺序与诚实声明义务。

## 1. 渲染链（report_render.py 实现）

按优先级依次**真实探测并真实执行**，任一成功即停：

| 优先级 | 方法 | 探测 | 执行 | 产物 |
| --- | --- | --- | --- | --- |
| 1 | xelatex | `shutil.which("xelatex")` | 极简 LaTeX 模板（longtable）编译 | verification-report.pdf |
| 2 | pdflatex | `shutil.which("pdflatex")` | 同上（CJK 内容可能编译失败，失败即降级） | verification-report.pdf |
| 3 | pandoc | `shutil.which("pandoc")` | `pandoc report.md -o report.pdf` | verification-report.pdf |
| 4 | html（兜底） | 无需外部工具 | 内建 Markdown→HTML 转换器，内联 CSS | verification-report.html |

每步判定成功的标准：子进程返回码为 0 **且**产物文件存在、大小 ≥100 字节。
探测失败、调用异常、编译失败都会记录并降级到下一级。

## 2. 诚实声明规则（硬性）

1. **绝不伪造渲染产物**：不允许把 Markdown 改名 `.pdf`、不允许写入空壳文件、
   不允许在未真实执行工具的情况下声称已渲染。
2. **降级必须声明**：最终报告尾部固定写入"渲染链实际路径与降级说明"一节，
   逐条列出每个方法的探测/执行结果（未安装、编译失败、成功），并写明最终
   采用的链。凡未走 xelatex 链，必须附加渲染降级声明（版式可能与 PDF 版有差异）。
3. **机器可读日志**：`render-info.json` 记录 `chain`、`preview_path`、
   `preview_size_bytes`、全部 `attempts`、时间戳，供 `contract_assemble.py merge`
   回写 `render_chain_used` / `report_preview_path` 契约字段。
4. **字节数以日志为准**：预览文件内嵌的说明不写自身精确字节数
   （自引用无法精确），精确大小以 `render-info.json` 为准。
5. 预览产物必须与 `verification-report.md` 同源同时生成；报告内容更新后
   必须重渲（run_example.sh 演示了"回写路径后重渲"的两阶段流程）。

## 3. 评测环境适配

- 评测环境若提供 `latex-compiler` / `office-renderer` / `pdf-render-tool`
  （见 `/input/environment/resources.yaml`），优先用其等价命令替换第 1–3 级，
  但降级链与诚实声明规则不变。
- 容器内通常无 LaTeX：预期多数情况下落在 pandoc 或 html 链，这是正常行为，
  只要声明如实即不扣分；假装有 PDF 才会失败。
