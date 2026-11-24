# statistical_playbook.md — 统计口径与裁决依据手册

本手册是 stat-assumption-tribunal 的口径档案：所有默认值的来源、改判规则、
禁止事项与公式。文中阈值均为**通行惯例（convention）而非定理**，引用时须以
「本分析采用如下约定」的口吻写出。

---

## 1. 口径表

| 项目 | 本工具口径 | 说明 |
|---|---|---|
| 标准差／方差 | ddof=0（总体，除以 n）与 ddof=1（样本，除以 n−1）**并列报告**，标签 `std_ddof0`／`std_ddof1` | 推断语境（SE、CI、t 检验）一律使用 ddof=1；描述总体时用 ddof=0。禁止只报一种却不标注 |
| 四分位数 | `statistics.quantiles(n=4)` 的 `method='inclusive'` 与 `'exclusive'` 并列 | inclusive 把端点计入（Excel PERCENTILE.INC、numpy 默认线性插值接近此口径）；exclusive 不计端点（Excel PERCENTILE.EXC）。n<4 时 exclusive 不可得，输出 null |
| 缺失策略 | drop-nulls-pairwise：缺失标记（空、NA、N/A、NaN、null、None、`.`，大小写不敏感）所在行剔除并计 `n_missing`；其余非数值 token **报错**，绝不静默转 0 | 相关分析为两列成对剔除 |
| 去重策略 | keep-all：不去重，完全重复行计入统计并报告 `n_exact_duplicate_rows`；是否去重由分析者显式声明 | 报告重复计数使「未去重就分组」成为可见事实而非静默假设 |
| 偏度 | 矩估计 g1 = m3 / m2^1.5，无自由度校正 | 与 scipy `stats.skew` 默认一致 |
| 峰度 | 超出峰度 g2 = m4 / m2² − 3 | 正态总体 E[g2] ≈ −6/(n+1) |
| 均值置信区间 | mean ± t(0.975, n−1) × std(ddof=1)/√n | t 分位数由内置 CDF 二分求逆 |
| 并列秩 | Mann-Whitney 与 Kruskal-Wallis 均做并列校正，报告 `n_tie_groups` 与 `tie_correction_applied` | 见 §5 公式 |

## 2. 前提检验阈值与依据（惯例声明）

| 检验 | 规则 | 依据性质 |
|---|---|---|
| 最小样本量 | 任一组 n<8 → 拒绝参数检验 | 惯例：K² 检验在 n<8 时无意义（scipy 同限）；小样本 t 检验对偏态极敏感 |
| 正态性 | n≥8：D'Agostino-Pearson K²，p<α 判不通过；n<20 附加经验规则：|g1|>1 或 |g2|>2 判不通过 | K² 为 D'Agostino & Pearson (1973) 的常规综合检验；|g1|>1／|g2|>2 是文献中常见的「明显偏离」经验界（如 Hair et al. 常用 |skew|>1 标记显著偏态）。均为惯例 |
| 方差齐性 | Brown-Forsythe（以中位数为中心的 Levene），p<α 判不齐 | 对非正态比经典 Levene（均值版）更稳健，为通行推荐 |
| 显著性水平 | α=0.05（`--alpha` 可改） | 惯例 |

## 3. 改判（reroute）决策矩阵

k = 组数；min_n = 最小组样本量。

| 条件 | 选定检验 | 退出码 |
|---|---|---|
| k=2，min_n≥8，各组正态性通过，方差齐性通过 | **Welch t（主）** + Student t（并列参考） | 0 |
| k=2，min_n≥8，正态性通过，方差齐性**不**通过 | **Welch t**（Student 仅作参考并附书面提示） | 0 |
| k=2，min_n<8 **或** 任一组正态性不通过 | **Mann-Whitney U**（并列校正正态近似 + rank-biserial 效应量） | 2 |
| k>2，min_n≥8，正态性与方差齐性均通过 | **单因素 ANOVA**（η² 效应量） | 0 |
| k>2，min_n<8 或正态性/方差齐性不通过 | **Kruskal-Wallis**（并列校正，η²_H 效应量） | 2 |
| 任一组 n<3、完全并列、常数列、无法计算 | 报错 JSON | 1 |

退出码 2 是**劝告性**信号：分析已完成，但结论必须使用改判后的检验，
并须在交付物中复述 `reroute_reason`。

## 4. 禁止事项清单

1. **禁止**把缺失值当 0 或静默填充；缺失只能按显式策略剔除并计数。
2. **禁止**在未通过前提检验时报告 t 检验／ANOVA 的 p 值；必须改判并写明理由。
3. **禁止**只报对结论有利的 ddof 或四分位方法（cherry-picked ddof）；两种口径并列。
4. **禁止**做多重比较却不说明比较次数；本工具不自动校正（见 §6），但报告必须显式列出全部已做比较。
5. **禁止**静默类型转换：非数值、非缺失标记的输入一律报错。
6. **禁止**隐瞒重复行：`n_exact_duplicate_rows` 必须随结果披露。
7. **禁止**编造任何数字：写入 result.json 的数值必须可由 verify-claims 复算通过。

## 5. 公式附录

**D'Agostino-Pearson K²**（n≥8）。g1、g2 为矩法偏度与超出峰度。

- 偏度变换：Y = g1·√((n+1)(n+3)/(6(n−2)))；
  β₂ = 3(n²+27n−70)(n+1)(n+3) / ((n−2)(n+5)(n+7)(n+9))；
  W² = −1 + √(2(β₂−1))；δ = 1/√(ln W)；α = √(2/(W²−1))；
  Z1 = δ·asinh(Y/α)。
- 峰度变换：E[g2] = −6/(n+1)；Var(g2) = 24n(n−2)(n−3)/((n+1)²(n+3)(n+5))；
  X = (g2−E[g2])/√Var(g2)；
  √β₁ = 6(n²−5n+2)/((n+7)(n+9)) · √(6(n+3)(n+5)/(n(n−2)(n−3)))；
  A = 6 + (8/√β₁)(2/√β₁ + √(1+4/β₁²))；
  Z2 = ((1 − 2/(9A)) − ((1 − 2/A)/(1 + X√(2/(A−4))))^(1/3)) / √(2/(9A))。
- K² = Z1² + Z2²，p = P(χ²₂ ≥ K²)。

**Brown-Forsythe**。z_ij = |x_ij − median_j|；对 z 做单因素 ANOVA：
F = MSB/MSW，df = (k−1, N−k)，p 取 F 上尾。

**Welch / Student t**。
Welch：t = (m1−m2)/√(s1²/n1 + s2²/n2)，
df = (s1²/n1+s2²/n2)² / [ (s1²/n1)²/(n1−1) + (s2²/n2)²/(n2−1) ]。
Student：s_p² = ((n1−1)s1²+(n2−1)s2²)/(n1+n2−2)，
t = (m1−m2)/(s_p√(1/n1+1/n2))，df = n1+n2−2。
双侧 p = I_{df/(df+t²)}(df/2, 1/2)（正则化不完全 beta）。

**Mann-Whitney U（并列校正）**。全体混合秩（并列取平均秩），
U1 = R1 − n1(n1+1)/2，U2 = n1n2 − U1，U = min(U1, U2)；
Var(U) = n1n2/12 · ((N+1) − Σ(t³−t)/(N(N−1)))，t 为各并列组大小；
z = (U − n1n2/2 + 0.5)/√Var(U)（0.5 为朝向均值的连续性校正），双侧 p = 2Φ(−|z|)。
**rank-biserial** r = 2U1/(n1n2) − 1，U1 取按标签排序第一组；r=±1 表示完全分离，
正值表示第一组取值偏大。

**Kruskal-Wallis**。H = 12/(N(N+1))·Σ(R_j²/n_j) − 3(N+1)；
并列校正 C = 1 − Σ(t³−t)/(N³−N)，H′ = H/C；p = P(χ²_{k−1} ≥ H′)；
η²_H = (H − k + 1)/(N − k)。

**相关**。Pearson r = Sxy/√(Sxx·Syy)，t = r√((n−2)/(1−r²))，df = n−2，双侧 p；
Spearman ρ = 对两列平均秩的 Pearson r。

## 6. 多重比较说明（报告，不自动校正）

本工具**不**执行 Bonferroni／FDR 等自动校正，因为校正策略取决于研究设计，
静默校正与静默不校正同样危险。规则是：

- 交付物中显式列出本次分析执行的全部检验（比较次数 m）；
- 每个 p 值旁注明「未经多重比较校正，共进行 m 次检验」；
- 若任务要求控制族系错误率，由分析者显式选择方法并在 `anomalies` 中记录。

## 7. 数值实现与自检

t／F CDF 经由正则化不完全 beta（连分式，Numerical Recipes Lentz 算法）；
卡方 CDF 经由正则化不完全伽马（级数 + 连分式双分支）；正态 CDF 经 math.erf；
t 分位数经二分求逆。`stattool.py selftest` 内置 18 项数值断言，包括：
t(df=10⁴)≈正态（<1e-4）、χ²₁ 的 0.95 分位 3.8415（<1e-9）、F(1,df)=t² 恒等
（<1e-10）、I_x(1,1)=x、P(1,x)=1−e^(−x)、MWU 手算点等，实测 18/18 PASS。
