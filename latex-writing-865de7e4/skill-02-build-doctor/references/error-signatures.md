# 常见错误签名 → 根因 → 处置

供 Agent 阅读 `diagnosis.md` 后快速定位根因。签名以 texlog.py 归一化后的形式
给出（数字已替换为 `#`）。处置栏是建议，改稿由 Agent 决定。

| 错误签名（首行） | 典型根因 | 处置建议 |
| --- | --- | --- |
| `LaTeX Error: File 'xxx.sty' not found` | 宏包未安装；或包名拼错 | 查 package-map.md「文件」表确认 TeX Live 包名；`tlmgr install` 或换等价宏包 |
| `LaTeX Error: File 'xxx.cls' not found` | 文档类未安装 | 同上；或改用已安装类（如 article/ctexart） |
| `Undefined control sequence`（l. 行末为 `\cmd`） | 命令拼错；宏包未加载；自定义命令未定义 | 查 package-map.md「命令」表；补 `\usepackage` 或 `\newcommand`；核对拼写 |
| `LaTeX Error: Environment foo undefined` | 环境所属宏包未加载 | 查 package-map.md「环境」表补宏包 |
| `Missing $ inserted` | 文本模式用了数学符号（_、^、\alpha 等） | 给该段加 `$...$` 或改用文本命令 |
| `Missing } inserted` / `Missing { inserted` | 花括号不配平（数学上下标 `{n}` 常漏右括号） | 逐字符核对 l. 行的 `{`/`}` 配对 |
| `Extra }, or forgotten $` | 多数为上一级错误的级联 | 先看它 cascade-of 的根因 |
| `Double subscript` / `Double superscript` | `x_i_j`、`x^2^3` | 加花括号：`x_{i_j}` |
| `There's no line here to end` | `\\` 用在段首/垂直模式 | 删除多余 `\\` 或改用 `\par`、`\vspace` |
| `Missing \begin{document}` | 导言区有排版内容；多为前面错误的级联 | 修第一个根因；检查导言区是否混入正文 |
| `Emergency stop` / `Fatal error occurred` | 几乎总是级联终点 | 忽略本身，修它 cascade-of 的根因 |
| `LaTeX Error: \begin{foo} ended by \end{bar}` | 环境开闭不匹配 | 核对环境名与嵌套顺序 |
| `Undefined tab position` / `Extra alignment tab` | 表格列数超过声明 | 核对列声明与 `&` 数量 |
| `Missing number, treated as zero` / `Illegal unit of measure` | 长度参数缺单位或宏展开错 | 检查 `\setlength`、`\includegraphics[width=...]` 等 |
| `Package x Error: ...` | 宏包自身报错（选项冲突、加载顺序） | 读错误正文；cleveref 须在 hyperref 后加载 |
| `Citation 'k' undefined`（警告） | `.bib` 无此键 / 拼写错 / 未跑 bibtex/biber | 核对键名；确认文献工具已执行且 `.bbl` 生成 |
| `Reference 'r' undefined`（警告） | 标签拼错或需再编译一轮 | 核对 `\label`/`\ref`；收敛轮次不足时texbuild 会自动加轮 |
| `Label(s) may have changed. Rerun`（提示） | 交叉引用未稳定 | texbuild 的收敛判据会自动再跑，无需人工处理 |
| `I can't write on file 'chapters/x.aux'` | 构建目录缺子目录镜像 | texbuild 已自动镜像 `\include` 子目录；出现此错说明有手工指定的 `\include` 路径异常，检查路径大小写 |

## 级联判读要点

1. 第一个 `! ` 错误通常是唯一真根因；其后 5–6 行内的 `Missing $`、`Extra }`
   多为派生。texlog.py 会把它们标注 `cascade-of`，修复时只动根因。
2. `Emergency stop`、`Fatal error` 永远是最后一条且永远是派生。
3. 修复后必须真实重编译（texverify.py），新日志 0 错误才算闭环；
   不得凭"理论上修好了"宣布成功。
