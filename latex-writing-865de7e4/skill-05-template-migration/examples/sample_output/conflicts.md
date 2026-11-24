> 合成示例（synthetic example），非正式案例结果。

# 宏包合规检查报告（conflicts）

> 本报告只给处置建议；导言区的任何改动由 Agent 判断并执行。

> 降级说明：未指定 --cls，取 <示例运行目录>/input/mockjournal.cls
> 降级说明：未指定 --manuscript，取 <示例运行目录>/input/manuscript.tex

- 规则表来源：<bundle 目录>/references/package-conflicts.md

- 稿件：`<示例运行目录>/input/manuscript.tex`（显式加载 4 个宏包）
- 模板类：`<示例运行目录>/input/mockjournal.cls`

## 问题清单（共 4 条）

### 1. [加载顺序][warning]

- 证据：hyperref 在第 7 行加载，但其后仍加载 booktabs(行8), graphicx(行9)
- 处置建议：将 hyperref 移到稿件宏包清单末尾（例外允许在其后：cleveref）。规则：hyperref 重定义大量内部命令，应在稿件显式加载的宏包中最后出现；cleveref 是公认的少数例外

### 2. [与模板类重复][error]

- 证据：<示例运行目录>/input/manuscript.tex:6 加载 geometry[margin=3cm]，模板类已 \RequirePackage[margin=2.5cm]{geometry}
- 处置建议：选项不一致，迁移后将触发 Option clash：删除稿件侧调用；确需不同选项时改用 \PassOptionsToPackage（须置于 \documentclass 之前）

### 3. [与模板类重复][warning]

- 证据：<示例运行目录>/input/manuscript.tex:8 加载 booktabs[]，模板类已 \RequirePackage[]{booktabs}
- 处置建议：迁移稿中删除稿件侧重复加载

### 4. [与模板类重复][warning]

- 证据：<示例运行目录>/input/manuscript.tex:9 加载 graphicx[]，模板类已 \RequirePackage[]{graphicx}
- 处置建议：迁移稿中删除稿件侧重复加载

