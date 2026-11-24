# 假设检验：正态性与方差齐性的操作要点

## 1. 为什么 n<8 不做正态性检验

- 所有正态性检验在小样本下功效极低：n=5 时即使总体是指数分布，K²/Shapiro
  也常常 p>0.05——"不拒绝"毫无信息量。
- 因此本 bundle 的规则是 **n<8 → not_tested → 按非正态保守处理**（走秩方法），
  并在 reason_codes 与 uncertainty 中显式留痕，绝不把"没检验"写成"正态"。
- 代价是功效损失（秩方法 ARE≈0.955），但小样本下参数检验的第一类错误
  失控风险更大，保守是对的。

## 2. K² vs Shapiro-Wilk

| | D'Agostino K² | Shapiro-Wilk |
|---|---|---|
| 原理 | 偏度 Z₁ 与峰度 Z₂ 的 χ²(2) 综合 | 次序统计量与期望的正态相关 |
| 依赖 | 闭式公式，纯标准库可算 | 需要 n 相关查表系数，stdlib 无法精确实现 |
| n 范围 | n≥8（n<20 近似稍粗） | 3–5000 精确 |
| 偏态/峰态方向 | 可分解解释 | 不可分解 |

本 bundle 选 K² 是因为**审计必须可独立重算**：闭式公式让任何第三方用
十行代码复核同一数字；它与 scipy.stats.normaltest 逐位一致（差异<1e-6，
见 scripts/crosscheck_scipy.py）。若运行环境恰好有 scipy 且分析者想用
Shapiro 复核，可在 digest 层面人工对照，但决策链以 K² 为准（口径唯一性
优先于检验偏好）。

## 3. Levene 变体选择

- center=mean：经典 Levene，对偏态敏感；
- **center=median（Brown–Forsythe）**：本 bundle 默认，对非正态稳健，
  与 scipy `levene(center='median')` 一致；
- center=trimmed：截尾均值，介于两者之间，未采用（多一个截尾比例超参，
  不利于审计复算）。

注意：Levene 本身对"正态但重尾"数据也较敏感；当 Levene 拒绝且各组确实
近似正态时，Welch t / Welch ANOVA 是正确出路，而不是硬上合并方差。

## 4. 门控的常见误用（本 bundle 明确禁止）

1. **"先跑 t 再回头看假设"**——门控必须先于检验，且留痕（decision_log）。
2. **把正态性 p≥0.05 当成"已证明正态"**——只是"未拒绝"，小样本时尤其
   不能说；文案统一写"K² 未拒绝正态性（p=…）"。
3. **对 k≥3 组直接做多个 t 检验**——必须 omnibus 先行 + 事后 Holm。
4. **方差不齐仍用合并方差 t/ANOVA**——Welch 路线的自由度校正代价很小，
   没有理由不用。
5. **门控阈值与主检验 α 不一致**——本 bundle 统一使用 constraints.alpha。
