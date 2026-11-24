# 统计分析报告 — case-synthetic-vinegar-demo

（由 stats-run-gates pipeline_e 生成；所有 p 值/效应量写法与 result.json 一致，受 G6 门检约束）

## 1 数据与清洗
- 输入 synthetic_vinegar.csv：sha256=2cefae667ade…，759 bytes
- 输入 synthetic_vinegar.db：sha256=906719ce7178…，8192 bytes
- 行数：raw=47，kept=47，dropped=0（闭合律 rows_raw==kept+dropped：成立）
- 清洗规则 flag_and_report：影响行数 3（完全重复行只标记报告不删除（删除需 constraints.duplicate_policy 显式授权））
- 清洗规则 missing_report_and_exclude：影响行数 0（分组变量缺失行整行剔除；结局变量缺失按逐变量有效 n 处理（不零填、不插补））
- 清洗规则 outlier_flag_1.5IQR：影响行数 3（1.5×IQR 栅栏只标记不删除）
- CSV/SQLite 一致性：一致

## 2 描述统计（按 group 分组）
### yield_rate（单位：%）
| 组 | n | 均值 | SD | 中位数 | Q1 | Q3 | min | max |
|---|---|---|---|---|---|---|---|---|
| control | 23 | 50.7087 | 8.4171 | 50.9100 | 46.5550 | 53.2150 | 35.8800 | 82.5000 |
| treatment | 22 | 53.6355 | 8.9014 | 54.5600 | 50.7000 | 59.0375 | 21.3000 | 63.3700 |

## 3 假设检验、效应量与 95% 置信区间（alpha=0.05）
### yield_rate [HT:yield_rate]
- 方法：Mann-Whitney U 检验（tie 校正正态近似）（理由码 2G_NONNORM：至少一组不满足正态性（或 n<8 保守判定））
- 统计量 = 148.0000，df = None，p = 0.0171
- 效应量：hedges_g = 0.3321，95% CI [-0.2111, 1.3926]（bootstrap percentile B=2000 seed=20240501；幅度：小）[ES:yield_rate]
- 位置差（treatment - control）：hodges_lehmann_median_diff = 4.4500，95% CI [3.5000, 5.8100]
- 参考：welch_t(classical reference)，统计量 = 1.1322，p = 0.2639（仅作可比性参考；主结论以 mannwhitney_u 为准）
- 判定：在 alpha=0.05 下组间差异统计显著 [CI:yield_rate]

## 4 解释
- yield_rate（单位：%）：control（n=23）与 treatment（n=22）比较，采用Mann-Whitney U 检验（tie 校正正态近似）（统计显著），p = 0.0171；均值差（treatment - control）= 2.9268 %。效应量 hedges_g（0.3321），95% CI [-0.2111, 1.3926]。统计显著不等于实际意义：本效应幅度为「小」。本结果为组间关联证据，不能表述为「证明」因果。[HT:yield_rate] [ES:yield_rate] [CI:yield_rate]
- yield_rate：为主结论稳健性附记经典参考统计量（welch_t(classical reference)，统计量 = 1.1322，p = 0.2639）；该参考值不改变以假设门控选定方法为准的结论。[HT:yield_rate]

## 5 局限与不确定性
- 局限：yield_rate 有 3 个 1.5×IQR 栅栏外取值（仅标记未删除），极端值可能影响参数法结果。
- 局限：本分析基于观察性数据，全部结论为关联性证据，不支持因果断言。
- 不确定性：效应量 95% CI 来自分层百分位 bootstrap（B=2000，seed=20240501），重抽样尾部分位本身存在蒙特卡洛误差。
- 不确定性：yield_rate 采用秩检验正态近似（tie 校正），极端 ties 或小组样本下 p 值为近似。

## 6 可复现性
- seed=20240501，python=3.9.6，platform=macOS-15.7.4-arm64-arm-64bit；输入/阶段产物哈希见 work/manifest.json；影子复跑由 scripts/replay_diff.py 逐字节核验。
