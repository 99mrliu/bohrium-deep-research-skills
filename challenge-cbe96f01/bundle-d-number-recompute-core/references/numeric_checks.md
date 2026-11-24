# N1–N5 重算检查的精确语义

## N1 百分比重算（硬矛盾，容差 0.5 个百分点）

覆盖句式：

- `X% (a/b)` —— claimed = X，recomputed = 100·a/b
- `(a/b) = X%`、`a of b (X%)` —— 同上

容差 0.5pp 对应常规四舍五入（如 45.83% 写 45.8% 或 46% 均合法）。超出容差即硬矛盾：claimed 与 recomputed 均写入矛盾记录。盲区：百分比变化（percentage points vs percent）表述歧义不判，交 Agent。

## N2 p 值—显著性措辞（硬矛盾）

以 p 值为中心 ±80 字符窗口内做措辞匹配：

| 措辞 | 要求 |
|-|-|
| highly significant | p < 0.01 |
| significant（无 not/no 否定） | p < 0.05 |
| not significant / no significant | p ≥ 0.05 |

`p < 0.05` 与 `p = 0.049` 按数值判定；`p < 0.001` 类开口不等式按字面阈值判定（p 视为阈值本身）。盲区：多重比较校正、单侧/双侧检验——交 Agent 按 stat_reporting.md 判断。

## N3 组量合计（硬矛盾）

单句内 ≥2 个组计数（"X group contained n"模式）之和必须等于全文某处声明的同名词总数（participants/patients/subjects/samples）。排除标准的常见合法情形：组间有重叠、总数不含脱落——因此矛盾落 finding 前由 Agent 复核上下文（脱落/排除说明），脚本只负责报警。

## N4 同名计数交叉（提示级，不报警）

同一名词在全文出现多个计数取值（如摘要 120、方法 118）时输出交叉核对条目，列取值与页码。是否构成矛盾由 Agent 判断（可能是"筛选 120 → 入组 118"的合法流程，也可能是真矛盾）。

## N5 表格合计行（硬矛盾）

管道表格（`| a | b |`）中首列含 `Total/合计` 的行，逐数值列重加上方各行（遇到上一张表的 Total 行停止）。表头分隔行（`|---|`）跳过。盲区：非管道格式的栏对齐表格（pdftotext 输出常见）不识别，跳过时必须在 uncertainties 声明并由 Agent 人工核对。

## 严重度建议

| 情形 | severity |
|-|-|
| 核心结论依赖的数字硬矛盾（主效应百分比、p 值） | major~critical |
| 次要数字硬矛盾（人口学表格合计） | minor~major |
| N4 确认为摘要-正文不一致 | major |
| N4 确认为合法筛选流程 | 不出 finding，或 advisory 建议明确表述 |
