# 统计量定义与双实现复核方法

## 统计量定义（写入 statistics.json 的 definitions 字段）

| 量 | 定义 |
|---|---|
| n | 非缺失观测数 |
| mean | 算术平均值 |
| SD | 样本标准差，ddof=1：`sqrt(Σ(x−mean)²/(n−1))` |
| SEM | `SD/sqrt(n)` |
| median / Q1 / Q3 | type-7 线性插值分位数（(n−1)p 位置线性插值） |
| min / max | 极值 |
| skewness | 矩偏度 `m3/m2^1.5`（m2、m3 为二、三阶中心矩，除 n） |
| Pearson r | 成对完整观测：`Σ(x−mx)(y−my)/sqrt(Σ(x−mx)²Σ(y−my)²)` |
| 组间 F | 单因素方差分析 F 统计量（仅用于面板排序，不做推断） |

## 双实现复核（verify_stats.py）

流水线内的统计（`describe()`/`pearson()`）用朴素两遍累加。复核器是
**独立第二实现**：

- 均值/方差用 Welford 在线算法（`mean += delta/n; M2 += delta*(x−mean)`），
  数值稳定性与累加路径都不同；
- 分位数独立重实现 type-7；
- Pearson 按原始行重新成对扫描累加；
- 分组样本量重新计数；
- 全部字段与 `statistics.json` 比对，相对容差 `1e-6·max(1,|a|,|b|)`。

任一字段不一致：写入 `verification_report.json`（含复算值与报告值），
`result.json` 的 `uncertainty` 记录，`status` 不报 `success`。

## 第三道校验（check_report.json）

流水线末尾再**重读原始源文件**（非内存中的清洗副本）复算每个数值列的
mean 与 n、每条展示相关的 r，与报告值比对。三重保障：实现错误、
内存数据被意外修改、源文件被外部改动，都能被定位。

## 误差线/须线含义的声明纪律

- 箱线图：箱体 Q1–Q3，中线=中位数，须线=1.5×IQR，须外点=离群观测
  （仅标记）。图注逐字写明。
- 不出现误差线图；若任务要求均值±误差展示，只允许 SD 并写明"标准差
  （SD），n=…"，禁止不声明含义的误差线。
- 不做显著性检验；图注不写 p 值。
