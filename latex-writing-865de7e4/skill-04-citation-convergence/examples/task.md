# 任务（合成示例（synthetic example），非正式案例结果）

`bad_project/` 是一个小型 LaTeX 工程，存在若干引用与参考文献问题。请：

1. 全面诊断 \\cite/\\ref/\\label/`.bib` 的完整性问题；
2. 修复后使 `pdflatex + bibtex` 多轮编译收敛到零 undefined citation / reference 警告；
3. 交付引用映射（每个引用点 ↔ bib 条目 ↔ 最终状态）与编译收敛证据。

`fixed_project/` 是一版参考修复（修复决策由 Agent 做出，脚本只诊断与验证）。
