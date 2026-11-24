# 多重性控制：Holm 与家族划分规则

## 1. Holm step-down（本 bundle 唯一的多重校正方法）

对族内 m 个原始 p 值 p_(1)≤…≤p_(m)：

```
adj_(i) = max_{j≤i} min(1, (m−j+1) · p_(j))
```

性质：强控制 FWER（任意假设结构下），永远不差于 Bonferroni；校正后 p
随秩单调不减（审计把"单调性 + 公式重算"作为 HOLM_MISMATCH 的两条判据）。

## 2. 家族划分规则

| 家族 | 成员 | 校正 |
|---|---|---|
| 一个结局的 omnibus 主检验 | 1 个检验 | 不校正（omnibus 本身是看门人） |
| 一个结局的两两事后比较 | C(k,2) 对 | Holm，族大小 m=C(k,2) |
| 不同结局变量之间 | 各自独立家族 | 不跨结局校正 |

- 选 Holm 而非 BH-FDR：组间比较场景检验数少（≤15）、结论需强 FWER 控制；
  FDR 留给探索性高通量场景（不在本挑战范围）。
- 事后检验与主检验**同路线**（anova→student_t，welch_anova→welch_t，
  KW→MW），禁止混用参数 omnibus + 非参事后的"混搭"，理由：决策链口径
  一致、可被审计按表 1 重算。
- omnibus 不显著时仍报告事后 p_holm（留痕），但解释时必须注明"omnibus
  未拒绝，事后显著对仅作探索性线索"。
- 组数 k>6（m>15）不做两两比较：组合爆炸且解释价值低，decision_log 记
  `holm.note` 并写入 exceptions。

## 3. 记录格式（审计契约）

`entry.posthoc[i] = {pair, test, statistic, p_raw, p_holm, significant}`；
`entry.holm = {family, m, raw, adjusted}`。审计用 raw 列表按 §1 公式重算
adjusted，容差 1e-9，并验证单调性。
