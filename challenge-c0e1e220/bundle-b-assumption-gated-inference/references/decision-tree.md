# 检验选择决策树与阈值表（含审计契约）

本文件是 pipeline_b 与 decision_audit 共同遵守的**唯一口径**。任何改动必须
两边同步，否则审计必然报违例。

## 1. 门控阈值

| 项 | 口径 |
|---|---|
| α | `case.json constraints.alpha`，默认 0.05；假设门控与主检验共用同一 α |
| 正态性 | D'Agostino–Pearson K²；`n < 8` 不检验，记 `not_tested`，**按非正态保守处理**；p < α 记 `non_normal`；组内方差为零记 `non_normal`（ZERO_VAR） |
| 方差齐性 | Levene 检验（**median 中心**，即 Brown–Forsythe）；p < α 记 `heterogeneous` |
| 全部正态 | 仅当**每一组** conclusion == "normal"（not_tested 不算正常） |

## 2. 决策树（表 1）

**两组（k=2）**

| 条件 | chosen_test | reason_codes 必含 |
|---|---|---|
| 全正态 且 方差齐 | `student_t` | NORMALITY_OK, VAR_HOMOG |
| 全正态 且 方差不齐 | `welch_t` | NORMALITY_OK, VAR_INHOMOG |
| 其他（含 not_tested） | `mannwhitney_u` | NORMALITY_FAIL:* / N_LT_8:* / ZERO_VAR:* |

**k 组（k≥3）**

| 条件 | chosen_test |
|---|---|
| 全正态 且 方差齐 | `anova` |
| 全正态 且 方差不齐 | `welch_anova`（Welch 1951：Λ=Σ(1−w_i/W)²/(n_i−1)，df2=(k²−1)/(3Λ)） |
| 其他 | `kruskal_wallis`（tie 校正） |

事后两两比较与主检验同路线：anova→student_t；welch_anova→welch_t；
kruskal_wallis→mannwhitney_u；Holm 校正（见 multiplicity.md）。组数 > 6
不做两两比较（组合爆炸），只报 omnibus。

## 3. reason_codes 规范

格式（审计按**前缀集合**比对，前缀 = `:` 或空格前的部分）：

- `N_LT_8:<组名> n=<n>`（每组至多一条）
- `NORMALITY_FAIL:<组名> p=<%.4f>`
- `ZERO_VAR:<组名>`
- `NORMALITY_OK`（全部组检验通过时）
- `VAR_HOMOG p=%.4f` / `VAR_INHOMOG p=%.4f`
- `SELECT <chosen_test>`（恒为最后一条）

## 4. decision_log 条目契约（审计依据）

每条目必须含：
`analysis_id, design(two_group|k_group), role, data{file, source_type,
group_column{name,index}, outcome_column{name,index}, levels, unit},
groups[{label, n, values_sha256, normality{test, statistic, p, conclusion}}],
levene{center, statistic, df1, df2, p, conclusion},
assumptions{all_normal, var_homogeneous, min_n},
candidates, chosen_test, reason_codes, rejected_candidates,
test_result{statistic_name, statistic, df, p, alpha, significant},
effect_size, confidence_interval, posthoc[{pair, test, p_raw, p_holm}], holm`。

- `values_sha256` = sha256("\n".join(repr(v) for v in sorted(values)))，浮点
  用 Python repr；审计重建后重算比对（防数据替换）。
- 两组方向约定：统计量与效应量均为**排序后第二组 − 第一组**（数值升序，
  字符串字典序）。
- p 在 JSON 中保留全精度；报告文本 4 位小数，p<0.0001 记 `<0.0001`。

## 5. 附录 A：审计侧数据重建口径

decision_audit 按以下公开口径从原始文件重建各组取值（与 pipeline 一致）：

1. 编码嗅探 utf-8-sig → utf-8 → gbk → latin-1；分隔符取首行计数最多的
   `,` `;` `\t`；首行 ≥半数单元格非数值 → 表头。
2. SQLite：第一个用户表，值转字符串后按同口径解析。
3. 去重：仅当 `constraints.duplicate_policy` 含 "dedupe" 时执行完全重复行
   去重（保留首行）；否则只报告不删除。
4. 缺失 token（大小写不敏感，去空白）：`"" NA N/A NaN null - nan`；
   组或结局缺失的行按变量排除。
5. 组匹配：原始字符串相等，或两侧均可解析为浮点且 |Δ|<1e-12。
6. 结局列必须可解析为浮点，否则该行不计入。

## 6. 违例码语义

| 码 | 触发 |
|---|---|
| ASSUMPTION_MISMATCH | 正态性/Levene 结论翻转、其 p 漂移 >1e-6、reason_codes 前缀集合不符、assumptions 汇总不符 |
| TEST_MISMATCH | chosen_test ≠ 决策树在重算假设下的应选 |
| STAT_MISMATCH | 主检验 statistic/df 漂移 >1e-6·max(1,|stat|)，或数据重建 n/哈希不符 |
| P_MISMATCH | 主检验 p 漂移 >1e-6 |
| BOOT_CI_DRIFT | bootstrap CI 端点 |Δ|>0.05，或点估计落在记录区间外 |
| HOLM_MISMATCH | Holm 公式重算不符（>1e-9）、校正 p 非单调、族大小 m 不符 |
| ALPHA_MISMATCH | result.json 的 α ≠ case.json constraints.alpha |
