# 定量公式、容差与统计限制

本文件只定义计算契据；具体 claim 的 verdict 由 Agent 综合语义给出。实现为 Python 3 标准库，无网络、第三方统计或绘图依赖。

## 1. 原报值与派生量

- `reported`：原文直接给出的 events/n、mean/sd/n、单位、表观百分比和逐字 quote。原报表观值不是自动可信的真值。
- `derived`：脚本根据 reported observations 计算的 p、effect、ratio、区间或检验；每项必须有 `formula`、`substitution`、`source_ids`。
- raw counts 与 `reported_display` 不一致时产生 `reported_display_conflicts_with_raw_counts`，两套值并列，不以 display 替换 raw，也不以复算 result 抹掉原报。

比例组第一组和第二组分别为 `p1=x1/n1`、`p0=x0/n0`。参数名的方向固定为“第一组减/除以第二组”，Agent 仍需检查它是否就是 claim 的语言方向。

| metric | 派生公式 | 输出单位 |
|---|---|---|
| `proportion_difference` | `p1-p0` | proportion |
| `percentage_point_difference` | `100*(p1-p0)` | percentage_point |
| `relative_change` | `(p1-p0)/p0` | relative_fraction |
| `proportion_ratio` | `p1/p0` | ratio |
| `mean_difference` | `mean1-mean0` | 原观测单位 |
| `relative_mean_change` | `(mean1-mean0)/mean0` | relative_fraction |
| `mean_ratio` | `mean1/mean0` | ratio |

**20 percentage points 与 20% relative change 不是同义。** 例如 p1=.70、p0=.50：差为 .20=20pp，相对变化为 .20/.50=.40=40%，比例为 1.4。relative/ratio 的基线为零时结果未定义，不返回零或无穷大充数。

连续组保留 mean、sd、n。当前实现计算两组均值差、均值比和相对均值变化，不自动执行 t 检验：缺少分布/独立性与适用方法判断时，不把均值汇总数据硬变成精确推断结论。

## 2. 两独立比例的双侧 z 检验

使用 pooled normal approximation：

```
p_pool = (x1+x0)/(n1+n0)
SE0 = sqrt(p_pool*(1-p_pool)*(1/n1+1/n0))
z = (p1-p0)/SE0
p_two_sided = erfc(abs(z)/sqrt(2))
```

`erfc` 等价于计算双侧标准正态尾概率。备择为 p1≠p0，`exact_test=false`。SE0=0（例如两组都全成功或全失败）时 z/p 为 null，并记录 degenerate warning，不能强行解释为无限显著或零效应。

sparse check 计算四个 pooled expected cells：`n1*p_pool`、`n1*(1-p_pool)`、`n0*p_pool`、`n0*(1-p_pool)`。任一 <5 即标记 `sparse_expected_cells=true` 并提示近似不稳定；脚本仍展示计算值但不硬判 semantic verdict。稀疏/极端数据应根据任务使用精确或合适的小样本方法，不能把这里的 p 当精确 p。

统计不显著不等于效应为零：可能是不确定性太大、样本量不足或区间很宽。统计显著也不等于数值效应达到 claim 指定幅度，更不自动证明语义命题。

## 3. Wilson 区间

对每个独立比例单独计算 **per-group Wilson score interval**，不做 continuity correction；不是两比例之差的 Wilson/Newcombe 区间。

```
D = 1 + zc^2/n
center = (p + zc^2/(2n))/D
halfwidth = zc*sqrt(p*(1-p)/n + zc^2/(4n^2))/D
CI = [max(0,center-halfwidth), min(1,center+halfwidth)]
```

默认 confidence=.95，`zc=1.959963984540054`。其他 0.5≤confidence<1 的 zc 用 `erfc` 标准正态 CDF 和 120 次二分反解计算。confidence 不在 (0,1) 或低于 .5、非法 events/n 都 exit 1；不允许 NaN/Infinity。

区间描述抽样不确定性，不是语义支持度，也不是效应为零的开关。除二项独立性和观测定义外，选择偏倚、测量错误、非独立抽样等均不能由该公式解决。

## 4. 单位与分母

内置相同量纲的乘法换算：

- time：s、ms、us、min、h；
- length：m、cm、mm、um、km；
- mass：kg、g、mg、ug；
- volume：L、mL、uL。

`converted = value * source_factor / target_factor`。大小写有意义的单位（L、mL）保留；跨量纲或未列入单位 exit 1，不猜汇率、温度、摩尔浓度或语境特定单位。2500 ms = 2500×(1e-3 s/ms) = 2.5 s。

`percent` 仅可按明确规则转 proportion（除以100）；`relative_percent` 转 relative_fraction；percentage_point 是单独输出单位，不能用普通 percent 相对变化替代。所有 claim target 必须带确定单位。分母必须由 quote 支撑；n、样本数、事件数、均值 SD 不可混用。

## 5. 容差比较

每个 component 可声明：

```json
{"target":{"value":0.4,"unit":"relative_fraction"},
 "tolerance":{"absolute":1e-9,"relative":0}}
```

判定仅为：

```
abs(calculated-target) <= max(absolute, relative*abs(target))
```

默认 absolute=1e-9、relative=1e-9；二者必须非负。report 同时输出 target、calculated-target、容差规则、最大允许绝对误差、within_tolerance 和 entailment_comparison。浮点误差（如 19.999999999999996 对20）由显式容差处理，不做字符串漂移比较。

`target_origin=source_reported` 时，问题是“原文是否报告该精确值”。脚本可并列派生值，但 comparison 固定为 `not_applicable_source_reporting_question`，不得因派生 p 与 target 不同就自动 contradicted。原文未报告仍是 insufficient evidence 的一种情况。

## 6. 不具备的能力

- 不做通用 OCR/PDF 结构理解或自动 claim 真伪裁决；观察由 Agent 从原文提取。
- 不从 mean/sd/n 伪造个体数据、分布、精确 p 或原始比例。
- 不把统计区间当效应上下界的绝对保证，不做多重检验校正、配对设计、聚空/生存模型、贝叶斯推断或任意小样本精确判断。
- 不将相关主题的 quote 当数值支持，不把缺失信息当反证，不静默消解来源冲突。
