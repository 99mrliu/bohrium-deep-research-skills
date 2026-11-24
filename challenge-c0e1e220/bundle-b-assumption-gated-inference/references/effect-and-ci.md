# 效应量与置信区间口径

## 1. 两组

方向约定（写进 decision_log，审计可复核）：**排序后第二组 − 第一组**。
例如 28 天 vs 90 天：正差异 = 90 天组更高。

| 量 | 口径 | 适用路线 |
|---|---|---|
| Hedges g | 合并 SD 标准化均值差 × 精确小样本校正 J(ν)=Γ(ν/2)/(√(ν/2)·Γ((ν−1)/2))，ν=n1+n2−2 | 两组均给 |
| g 的 95%CI | **百分位 bootstrap，B=2000，seed=20240501**（协议见 §3） | 两组均给 |
| rank-biserial r | r = 2U1/(n1n2) − 1，由 MW 的 U1 换算 | 两组均给（MW 路线为主要效应量） |
| 均值差 CI | Welch 自由度 t 区间 | student_t / welch_t 路线 |
| 中位数差（HL） | 全部 n1·n2 个两两差的中位数 + 大样本分位区间 | mannwhitney_u 路线 |

效应量大小参考（Cohen 惯例，仅作语境）：|g| 0.2/0.5/0.8 ≈ 小/中/大。
**显著性（p）与实际意义（效应量+CI）必须同时报告**，禁止只报 p。

## 2. k 组

| 路线 | 效应量 |
|---|---|
| anova / welch_anova | η² = SSb/SSt；ω² = (SSb−(k−1)·MSw)/(SSt+MSw)（Welch 路线借用经典 SS 口径并在 effect_size.note 注明） |
| kruskal_wallis | ε² = (H−k+1)/(N−k) |

η² 有正偏，ω² 更接近总体值；两者同时给出，解释时以 ω² 为主。

## 3. bootstrap 确定性协议（审计按此逐位重算）

```
rng = random.Random(20240501)          # 固定种子
for b in 1..2000:                      # B=2000
    依次对 group1、group2: 以 rng.randrange(n) 有放回抽 n 个下标
    计算 Hedges g（合并 SD=0 的 replicate 跳过）
m = 有效 replicate 数（m < 1000 → CI 记 None）
排序后 lo = s[floor(0.025·m)], hi = s[ceil(0.975·m)−1]（下标截断到合法范围）
```

- 同一个 random.Random 实例按 group1→group2 顺序消费，保证跨平台逐位
  一致（CPython 的 random 协议稳定）。
- 审计容差放宽到端点 |Δ|≤0.05（防第三方重采样实现细节差异），并要求
  **点估计落在记录区间内**。
- 百分位法局限：小样本/强偏态下可能欠覆盖；需要更高精度时应换 BCa
  （本 bundle 未实现，写入 limitations）。

## 4. 解释警示

- CI 是"参数"的区间估计，不是个体取值的散布范围；
- g 的 CI 跨 0 而 p<α（或反之）在边界样本上可能出现，以门控检验的 p 为
  显著性裁决，CI 用于表达估计精度；
- HL 估计的是"位置位移"（pseudo-median 差），仅在分布形状相近时可解读为
  中位数差。
