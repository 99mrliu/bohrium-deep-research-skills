# 宏包映射表（命令 / 环境 / 文件 → 宏包与 TeX Live 包）

本表被 `scripts/texlog.py --map` 解析：三个小节标题分别含「命令」「环境」「文件」，
表格第一列为键（反引号包裹），第二列为提供它的宏包或 TeX Live 包名，第三列为说明。
脚本只据此给建议，是否采用由 Agent 判断。

## 命令 → 宏包

| 命令 | 宏包 | 说明 |
| --- | --- | --- |
| `\vect` | `esvect` | 向量箭头记号；也可用 `\mathbf`/`\vec` 替代（amsmath 自带 `\vec`） |
| `\bm` | `bm` | 粗体数学符号，优于 `\boldsymbol` |
| `\boldsymbol` | `amsmath` | 粗体数学符号 |
| `\mathbb` | `amssymb` | 黑板粗体（ℝ、ℕ 等） |
| `\mathfrak` | `amssymb` | 德文尖体 |
| `\dfrac` | `amsmath` | 行间尺寸分式 |
| `\cfrac` | `amsmath` | 连分数 |
| `\SI` | `siunitx` | 带单位数值（旧写法，siunitx v3 用 `\qty`） |
| `\qty` | `siunitx` | 带单位数值 |
| `\num` | `siunitx` | 数字格式化 |
| `\includegraphics` | `graphicx` | 插图 |
| `\subfloat` | `subfig` | 子图（勿与 subcaption 混用） |
| `\subcaption` | `subcaption` | 子图题注 |
| `\toprule` | `booktabs` | 三线表顶线 |
| `\midrule` | `booktabs` | 三线表中线 |
| `\bottomrule` | `booktabs` | 三线表底线 |
| `\multirow` | `multirow` | 跨行单元格 |
| `\cline` | `array`（LaTeX 内核亦可） | 局部横线 |
| `\url` | `url` 或 `hyperref` | 网址排版 |
| `\href` | `hyperref` | 超链接 |
| `\cref` | `cleveref` | 智能交叉引用（须晚于 hyperref 加载） |
| `\Cref` | `cleveref` | 句首智能引用 |
| `\algtext` | `algorithmicx` | 算法伪代码 |
| `\State` | `algorithmicx`（`algpseudocode`） | 伪代码语句 |
| `\lstinline` | `listings` | 行内代码 |
| `\todo` | `todonotes` | 待办批注 |
| `\sout` | `ulem` | 删除线 |
| `\ce` | `mhchem` | 化学式 |
| `\ang` | `siunitx` | 角度 |
| `\nicefrac` | `nicefrac`（或 `xfrac` 的 `\sfrac`） | 行内斜分式 |
| `\text` | `amsmath` | 数学模式中的文字 |
| `\operatorname` | `amsmath` | 自定义算子 |
| `\DeclareMathOperator` | `amsmath` | 声明算子（导言区） |
| `\addbibresource` | `biblatex` | 声明文献库（配合 biber） |
| `\printbibliography` | `biblatex` | 输出文献表 |
| `\footnotemark` | LaTeX 内核 | 脚注记号 |
| `\captionof` | `caption` | 环境外题注 |
| `\adjustbox` | `adjustbox` | 盒子缩放/裁剪 |

## 环境 → 宏包

| 环境 | 宏包 | 说明 |
| --- | --- | --- |
| `align` | `amsmath` | 多行对齐公式 |
| `align*` | `amsmath` | 无编号多行对齐 |
| `gather` | `amsmath` | 多行居中公式 |
| `equation` | LaTeX 内核（编号需 amsmath 功能时加载） | 单行公式 |
| `split` | `amsmath` | 单行内折行 |
| `cases` | `amsmath` | 分段函数 |
| `matrix` / `pmatrix` / `bmatrix` | `amsmath` | 矩阵 |
| `theorem` | `amsthm`（`\newtheorem`） | 定理类环境 |
| `proof` | `amsthm` | 证明环境 |
| `algorithm` | `algorithm`（float 包族） | 算法浮动体 |
| `algorithmic` | `algorithmicx` 或 `algorithms` | 伪代码主体 |
| `lstlisting` | `listings` | 代码清单 |
| `minted` | `minted` | 代码高亮（需 -shell-escape） |
| `tikzpicture` | `tikz`（pgf） | TikZ 绘图 |
| `axis` | `pgfplots` | 函数图像坐标轴 |
| `tabularx` | `tabularx` | 定宽自适应表格 |
| `longtable` | `longtable` | 跨页表格 |
| `sidewaystable` | `rotating` | 横排表格 |
| `wrapfigure` | `wrapfig` | 文字绕排插图 |
| `subfigure` | `subcaption` 或 `subfig` | 子图 |
| `thebibliography` | LaTeX 内核 | 手写文献表 |
| `forest` | `forest` | 树状图 |

## 文件（.sty/.cls/.bib 相关）→ TeX Live 包

| 文件 | TeX Live 包 | 说明 |
| --- | --- | --- |
| `ghostmath.sty` | 无（虚构包名） | 合成示例专用，演示"宏包未安装"错误；真实场景中应换成已安装宏包 |
| `siunitx.sty` | `siunitx` | `tlmgr install siunitx` |
| `cleveref.sty` | `cleveref` | 须最后加载 |
| `esvect.sty` | `esvect` | 向量箭头 |
| `algorithmicx.sty` | `algorithmicx` | 伪代码 |
| `algorithm.sty` | `algorithms` | 算法浮动体在 algorithms 合集内 |
| `minted.sty` | `minted` | 另需 Pygments 与 -shell-escape |
| `ctex.sty` / `ctexart.cls` | `ctex` | 中文支持，须用 xelatex |
| `xeCJK.sty` | `xecjk` | 中文支持，须用 xelatex |
| `fontspec.sty` | `fontspec` | 字体选择，触发 xelatex 判定 |
| `beamer.cls` | `beamer` | 幻灯片类 |
| `IEEEtran.cls` | `ieeetran` | IEEE 模板类 |
| `elsarticle.cls` | `elsarticle` | Elsevier 模板类 |
| `revtex4-2.cls` | `revtex` | APS 模板类 |
| `achemso.cls` | `achemso` | ACS 模板类 |
| `pgfplots.sty` | `pgfplots` | 绘图 |
| `booktabs.sty` | `booktabs` | 三线表 |
| `biber`（可执行） | `biber` | biblatex 后端；缺失时 `tlmgr install biber` |
