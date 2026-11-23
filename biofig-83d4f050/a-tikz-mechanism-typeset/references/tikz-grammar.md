# biopathway.tex 图元语法全参考

机制图源文件骨架：

```tex
\documentclass[tikz,border=6pt]{standalone}
\input{biopathway.tex}   % 与图同目录（从 assets/ 复制到 /app/work）
\begin{document}
\begin{tikzpicture}[node distance=1.1cm and 1.6cm]
  ...区室带 → 节点 → 边 → legend...
\end{tikzpicture}
\end{document}
```

仅依赖 tikz、pgfplots、xcolor 及其自带库（arrows.meta, positioning, calc,
backgrounds, fit, decorations.pathmorphing, decorations.markings）；
pgfplots 已设 `\pgfplotsset{compat=1.17}`。

## 1. 区室带（先画，背景层）

自上而下顺序固定：**细胞外 → 膜 → 胞质 → 核**。

```tex
\begin{scope}[on background layer]
  \fill[extracellularband] (-6.5, 1.4) rectangle (6.5, 3.4);
  \fill[membraneband]      (-6.5, 0.6) rectangle (6.5, 1.4);
  \fill[cytosolband]       (-6.5,-3.6) rectangle (6.5, 0.6);
  \fill[nucleusband]       ( 1.0,-3.6) rectangle (6.5,-1.2);
\end{scope}
\node[bandlabel] at (-6.4,3.35) {extracellular};   % 斜体灰色带标签
\pic at (0,1.0) {bilayer={6.5}};                    % 磷脂双分子层（参数=半宽）
```

核也可以用 `\node[nucleusbody] ...`（双圈大圆）表示。

## 2. 节点样式

| 样式 | 外观 | 用于 | 标签规则 |
|---|---|---|---|
| `protein` | 蓝色圆角矩形 | 一般蛋白、激酶、转录因子 | **正体** |
| `gene` | 橙色矩形 | 基因 / DNA 元件 | **斜体**（样式自带 itshape，或用 `\gene{STAT3}`） |
| `complex` | 紫色双线圆角矩形 | 蛋白复合体 | 正体，组分用 `/` 连接 |
| `smallmolecule` | 绿色椭圆 | 配体、代谢物、药物、离子 | 正体 |
| `receptor` | 加粗高圆角矩形 | 跨膜受体 | 中心必须对齐膜带中线（跨膜放置） |
| `pbadge` / `ubbadge` | 小圆徽标 | 磷酸化 P / 泛素 Ub（phosphorylate/ubiquitinate 边自动放置，也可手动 `\node[pbadge]{P};`） | — |
| `ann` | 小号灰字 | 注释文字 | — |

辅助宏：`\gene{IL6}`（斜体基因名）、`\phos{STAT3}` → `p-STAT3`（p- 前缀正体）。

## 3. 边样式与中文机制词映射

| 中文机制词 | 边样式 | 外观 | 备注 |
|---|---|---|---|
| 促进 / 激活 / 上调 | `activate` | 蓝开放三角箭头 → | 正调控专用 |
| 抑制 / 拮抗 / 下调 | `inhibit` | 红 T 形横杠 ⊣ | 负调控专用，**不得用普通箭头代替** |
| 结合 / 互作 / 形成复合体 | `bind` | 黑实线（无箭头） | 无方向性 |
| 磷酸化 | `phosphorylate` | 红棕箭头 + 中点 P 徽标 | 激酶→底物 |
| 泛素化 | `ubiquitinate` | 紫箭头 + 中点 Ub 徽标 | E3→底物 |
| 转运 / 入核 / 易位 / 分泌 | `transport` | 灰黑虚线箭头 | 跨区室移动 |
| 募集 | `recruit` | 蓝点线开放箭头 | 向膜/复合体募集 |
| 材料未明确的关系 | `uncertain` | 灰虚线 + 中点 ? | **必须**同时记入 exceptions |

用法：`\draw[activate] (a) -- (b);`，可 `|-`/`-|` 折线绕障，
`node[ann, midway, above] {文字}` 加边注。

## 4. 布局规则

1. **信号流向**默认自上而下（胞外→胞质→核）或自左而右；反馈回路用折线走外围。
2. **跨膜受体**：`receptor` 节点中心坐标 = 膜带 y 中线；配体在胞外带与其连线，胞内结构域侧接下游蛋白。
3. **入核**：胞质中的转录因子 → 核内基因，用 `transport` 虚线跨带；核内 `gene` 节点斜体。
4. **分支**：一个节点引出多条 activate/inhibit 时错开角度（`.. controls ..` 或先 `++` 偏移），避免重叠。
5. **反馈/前馈回路**：绕行主链路外侧，用 `-|` 折线；抑制性反馈用 `inhibit` 红色，醒目。
6. 节点间距：`node distance=1.1cm and 1.6cm` 起步，复杂图用 `positioning` 库的 `right=of` 等。

## 5. 图例

```tex
\node[legendframe, anchor=north west] at (x,y) {%
  \begin{tabular}{@{}ll@{}}
    \multicolumn{2}{@{}l}{\textbf{Legend}}\\[2pt]
    \legendrow{activate}{activation}
    \legendrow{inhibit}{inhibition}
    \legendrow{phosphorylate}{phosphorylation}
    \legendrow{transport}{translocation}
    \legendrow{uncertain}{uncertain (no source)}
  \end{tabular}};
```

机制图例必须覆盖图中**实际用到**的每种边样式；用到的样式与图例一一对应，
这是 `legend_data_consistency` 校验的一部分。

## 6. pgfplots 数据图

```tex
\begin{tikzpicture}
\begin{axis}[bpchart, xlabel={...}, ylabel={...}, legend pos=north west]
  \addplot[bpscatter] table[x=log2FC, y=neglog10p, col sep=comma] {data.csv};
  \addlegendentry{genes}
  \addplot[bpbar] table[x=group, y=value, col sep=tab] {results.tsv};
\end{axis}
\end{tikzpicture}
```

- `bpchart`：统一坐标轴/网格/图例外观；`bpbar` 蓝色柱状；`bpscatter` 蓝色散点。
- **数据文件随图复制到 /app/work**，`\addplot table` 直读真实文件，列名必须与文件头完全一致（编译错误"no column named x"说明列名不符，回去核对）。
- 轴标签与单位照抄数据文件表头/案例说明；图例条目 = 数据系列名，逐一对应。
- TSV 用 `col sep=tab`，CSV 用 `col sep=comma`。
