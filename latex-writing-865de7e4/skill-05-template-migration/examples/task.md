# 任务（合成示例）

> 合成示例（synthetic example），非正式案例任务。

将输入目录下的 `manuscript.tex`（plain article 稿件）迁入自造期刊模板
`mockjournal.cls`：

1. 落实模板必填字段 `\journalname`（填 `Journal of Synthetic Examples`）
   与 `\keywords`（填 `adaptive mesh refinement; shallow water equations`）；
2. 处理稿件宏包与模板类自带宏包的重复及加载顺序问题；
3. 保持正文文字零改动（允许命令与空白差异）；
4. 交付可继续编辑的迁移稿源码、合规检查证据与最小 diff 报告。
