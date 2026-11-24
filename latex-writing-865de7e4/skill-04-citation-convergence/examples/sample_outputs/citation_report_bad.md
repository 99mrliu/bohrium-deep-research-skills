> 合成示例（synthetic example），非正式案例结果

# 引用图谱静态审计报告（citeaudit，未编译）

## 概要

| 指标 | 数量 |
| --- | --- |
| .tex 文件 | 1 |
| .bib 文件 | 1 |
| 引用点（\cite 出现次数） | 6 |
| 去重后的被引键 | 6 |
| **未定义引用（undefined citations）** | 2 |
| 交叉引用点（\ref/\eqref 等） | 2 |
| **未定义交叉引用** | 0 |
| \label 总数 | 3 |
| **重复 \label** | 1 |
| bib 条目数 | 5 |
| **bib 重复键** | 0 |
| **未被引用的 bib 条目** | 1 |
| **缺必需字段的 bib 条目** | 1 |
| 有字段问题（含建议字段）的 bib 条目 | 5 |

> 本报告只给建议（suggestions），不自动修改任何 .tex/.bib 文件；是否采纳由 Agent 判断。

## 1. 未定义引用（undefined citations）

### `vaswani2017attentoin`

- 引用点：`main.tex:17`（\cite）
- 最接近的 bib 键候选（仅建议，需人工核对）：
  - `vaswani2017attention`（相似度 0.95，强匹配）

### `zhang2020residual`

- 引用点：`main.tex:20`（\cite）
- 未找到相近的 bib 键候选（可能确实缺少条目）。


## 2. 未定义交叉引用与重复标签

### 重复 \label（同一键定义多次）

- `sec:intro` 定义于 `main.tex:16`；`main.tex:24`

## 3. 未被引用的 bib 条目

以下条目在 .bib 中存在但正文从未 \cite（**不要直接删除**：可能是漏引，也可能是备查文献，由 Agent 判断处置）：

- `knuth1984texbook`（@book，`refs.bib:35`）

## 4. bib 字段缺失（按 entrytype 最小字段）

规则详见 references/bib-field-rules.md。

| 条目 | entrytype | 位置 | 缺必需字段 | 缺建议字段 |
| --- | --- | --- | --- | --- |
| `goodfellow2016deep` | @book | `refs.bib:10` | — | edition、isbn、doi |
| `he2016deep` | @article | `refs.bib:27` | year | volume、number、doi |
| `knuth1984texbook` | @book | `refs.bib:35` | — | edition、isbn、doi |
| `lecun2015deep` | @article | `refs.bib:17` | — | number、doi |
| `vaswani2017attention` | @article | `refs.bib:2` | — | number、pages、doi |

## 5. \cite 顺序与重复（信息级）

首次出现顺序（数字编号样式下参考文献表通常按此排序）：

`vaswani2017attentoin` → `vaswani2017attention` → `goodfellow2016deep` → `lecun2015deep` → `zhang2020residual` → `he2016deep`

