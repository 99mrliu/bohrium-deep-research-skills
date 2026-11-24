# 统计方法说明（statistics notes）

本文件精确记录本 bundle 各脚本使用的公式、字段名与已知局限。
所有计算仅依赖 Python 标准库，结果确定性（无随机数、无墙钟时间）。

## 1. 泊松计数 95% CI（slice_stats.py）

字段：`ci95_lo` / `ci95_hi`；方法标识 `ci_method = "garwood-wilson-hilferty"`。

Garwood 精确区间把泊松计数 n 的 CI 与卡方分位数联系起来：

    lower = 0.5 * χ²(α/2,   2n)        （n = 0 时 lower = 0）
    upper = 0.5 * χ²(1-α/2, 2(n+1))

标准库没有卡方分位数函数，因此卡方分位数用 **Wilson–Hilferty 近似**：

    χ²(p, k) ≈ k · (1 − 2/(9k) + z_p·√(2/(9k)))³
    z_p = NormalDist().inv_cdf(p)   （statistics 标准库）

近似分位数在下尾近 0 处截断为 0（WH 变换可能给出负值）。

**局限**：WH 近似在小自由度（尤其下尾、k≤4）有可见误差（相对误差可达数个百分点），
因此本区间是“近似精确”而非严格精确；对年度文献计数的量级（个位到十位）足够稳健，
但不要把 CI 边界当成锋利阈值做过度解读。窗口模式（--window N）下 CI 按窗口总计数计算，
不再对应“每年”速率。

## 2. 变点扫描：泊松两段模型 MLE（changepoint.py）

对每个候选 τ（= 第二段首个 bin）：

    λ1 = S1/T1,  λ2 = S2/T2        （闭式 MLE；S=段内事件总数, T=段内 bin 数）
    ll_gain = [S1·ln λ1 − λ1·T1] + [S2·ln λ2 − λ2·T2] − [S·ln λ − λ·T]
             （ −Σln x! 项与模型无关，在增益中消去；λT = S 故实际按 S·ln(S/T) − S 计算）

字段：candidates[{tau, lambda1, lambda2, rate_ratio, ci95_lo, ci95_hi, ll_gain, rank, supported}]。

**rate_ratio 的 95% CI（log 尺度，delta 法）**：

    log(rr) ± z(0.975) · SE,   SE = √(1/S1 + 1/S2)
    （两段计数独立 ⇒ Var(log Ŝ) ≈ 1/S）

`supported = true` 当且仅当 CI 整体在 1 的某一侧（`ci95_lo > 1` 或 `ci95_hi < 1`）。
`adopted_tau` = supported 候选中 ll_gain 最大者。S1 或 S2 为 0 的候选被跳过（对数比不可估），并记入 warnings。

**局限**：(i) 扫描全部 τ 属于多重比较，ll_gain 本身没有校正显著性——
因此采纳规则要求 CI 排除 1，且报告应优先引用 adopted_tau；(ii) delta 法 SE 在小计数（S<5）
时偏乐观；(iii) 模型假设段内速率恒定，渐变（ramp）会被近似为某个折中的跳变；
(iv) 右删失 bin 已被排除，若实际并非删失而是真衰退，会损失对该衰退的检出。

## 3. 单年波动 z 分数（changepoint.py）

字段：fluctuations[{year, count, ma_baseline, z, direction}]。

    MA = 前 3 个 bin 计数的均值（不含当年）
    z  = (x − MA) / √MA
    |z| ≥ 2 ⇒ 波动候选

含义：在“基线速率 ≈ MA”的泊松假设下，z 近似标准正偏度（均值 MA、方差 MA）。
|z|≥2 的单年尖峰/凹陷是**噪声候选**，不是拐点证据；拐点必须由第 2 节的两段模型支持。

**局限**：MA 用前 3 年估计基线，本身有抽样误差（未计入分母）；基线速率小（MA<2）时
正态近似差、z 偏大；真实趋势期（如持续上升段起点）也可能触发，这正是
claim_audit 中「波动年 + 有 supported 变点 ⇒ 不算违规」规则存在的原因。

## 4. 右删失 40% 规则（slice_stats.py）

字段：`partial_year_suspect`、`censoring{final_label, final_count, median_prev3, threshold}`。

    partial_year_suspect = ( 末 bin 计数 < 0.4 × 前 3 个 bin 计数的中位数 )
    （bin 数 < 4 时不检测）

动机：文献库/检索快照对最近一年的收录几乎总是不全（右删失），末年计数骤降
通常是数据截取伪象而非领域退潮。

**局限**：这是启发式规则，**真实衰退同样会触发它**——所以 claim_audit 不是
“禁止讨论末段”，而是禁止把末段计数当作衰退的（唯一）证据；衰退主张必须
由未删失区间的统计支撑。阈值 0.4 是经验值，跨数据库口径（如预印本占比高
的领域收录滞后更严重）可能偏松或偏严。

## 5. 趋势方向重算（claim_audit.py, trend/decline 主张）

区间内 bin 对半分（奇数个时中间 bin 归后半段），比较两半段速率比，
CI 同第 2 节 log 尺度公式：

    rr = (S2/T2)/(S1/T1),  log(rr) ± 1.96·√(1/S1 + 1/S2)

    主张 up：  lo > 1 ⇒ ok；hi < 1 ⇒ direction_mismatch；否则 downgraded（功效不足）
    主张 down：hi < 1 ⇒ ok；lo > 1 ⇒ direction_mismatch；否则 downgraded
    主张 stable：CI 排除 1（任一方向）⇒ direction_mismatch；否则 ok

**局限**：对半分是最粗的趋势检验，对先升后降（倒 U）不敏感；区间 < 4 bin 时
直接判 downgraded。审计只覆盖“方向与计数是否矛盾”，不替主张做因果解释。
