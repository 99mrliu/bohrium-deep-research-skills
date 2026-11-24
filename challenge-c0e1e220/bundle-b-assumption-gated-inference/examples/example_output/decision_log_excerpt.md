# decision_log 摘录（合成示例真实产物）

## A1 — value @ pair_group（two_group）
- 各组 n 与正态性: skew_high n=12 K2_p=0.0000 -> non_normal; skew_low n=12 K2_p=0.8614 -> normal
- Levene(median): W=2.9182, p=0.1017 -> homogeneous
- reason_codes: `NORMALITY_FAIL:skew_high p=0.0000`, `VAR_HOMOG p=0.1017`, `SELECT mannwhitney_u`
- 被否决: student_t(正态性不满足或 n<8); welch_t(正态性不满足，Welch 仅校正方差不能校正偏态)
- **chosen_test = mannwhitney_u**: U=16.0000, df=[None], p=0.001224, alpha=0.05

## A2 — value @ trio_group（k_group）
- 各组 n 与正态性: norm_A n=25 K2_p=0.1311 -> normal; norm_B n=25 K2_p=0.8197 -> normal; norm_C n=25 K2_p=0.4329 -> normal
- Levene(median): W=0.2016, p=0.8179 -> homogeneous
- reason_codes: `NORMALITY_OK`, `VAR_HOMOG p=0.8179`, `SELECT anova`
- 被否决: welch_anova(方差齐性成立); kruskal_wallis(全部组正态且方差齐，参数检验功效更高)
- **chosen_test = anova**: F=24.6428, df=[2, 72], p=7.028e-09, alpha=0.05

