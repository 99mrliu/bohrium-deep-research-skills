# Comparison Matrix(比较矩阵)

> 按 quantity_kind 分组; **quantity_kind 不同的格子机检直接判不可比**;
> 不同数据集/不同污染物(染料)不得合并; 不可比与未报告项保留在表中, 不删除。

比较任务: 比较三篇光催化论文中 g-C3N4 对 RhB 的降解性能

## 量类: catalyst_dosage (规范比较单位: g/L)

| measurement_id | doc | paragraph | 原值 | 单位 | 换算到规范单位 | 口径 | 六维可比性摘要 |
|---|---|---|---|---|---|---|---|
| M-002 | DOC-01 | P003 | 0.5 | g/L | 0.5 g/L (reported) | 催化剂投加量, 以单位反应液体积的 g-C3N4 粉体质量计 | units:comparable; metric:comparable; task:comparable; material:comparable; pollutant:comparable; budget:not_comparable |
| M-005 | DOC-02 | P002 | 1 | g/L | 1 g/L (reported) | 催化剂投加量, 以单位反应液体积的 g-C3N4 粉体质量计 | units:comparable; metric:comparable; task:comparable; material:comparable; pollutant:comparable; budget:not_comparable |
| M-007 | DOC-03 | P002 | 500 | mg/L | 0.5 g/L (derived) | 催化剂投加量, 以单位反应液体积的 g-C3N4 粉体质量计 | units:comparable; metric:comparable; task:comparable; material:comparable; pollutant:comparable; budget:not_comparable |

### 六维度可比性判定

| 维度 | 结论 | 依据 |
|---|---|---|
| task | comparable | 取值一致: photocatalytic_degradation |
| metric | comparable | 口径一致(auto): 催化剂投加量, 以单位反应液体积的 g-C3N4 粉体质量计 |
| units | comparable | 量纲一致 L^-3·M; 单位写法 ['g/L', 'mg/L'] 可互相换算(换算值标 derived) |
| material | comparable | 取值一致: g-C3N4 |
| pollutant | comparable | 取值一致: RhB |
| budget | not_comparable | 取值不同, 不得合并: M-002=300 W Xe lamp; M-005=300 W Xe lamp + 420 nm cutoff; M-007=150 W LED |

## 量类: concentration (规范比较单位: g/L)

| measurement_id | doc | paragraph | 原值 | 单位 | 换算到规范单位 | 口径 | 六维可比性摘要 |
|---|---|---|---|---|---|---|---|
| M-003 | DOC-01 | P003 | 10 | mg/L | 0.01 g/L (derived) | RhB 初始浓度 C0 | units:comparable; metric:comparable; task:comparable; material:comparable; pollutant:comparable; budget:comparable |

### 六维度可比性判定

| 维度 | 结论 | 依据 |
|---|---|---|
| task | comparable | 取值一致: photocatalytic_degradation |
| metric | comparable | 口径一致(auto): RhB 初始浓度 C0 |
| units | comparable | 量纲一致 L^-3·M; 单位写法 ['mg/L'] 可互相换算(换算值标 derived) |
| material | comparable | 取值一致: g-C3N4 |
| pollutant | comparable | 取值一致: RhB |
| budget | comparable | 取值一致: 300 W Xe lamp |

## 量类: degradation_efficiency (规范比较单位: %)

| measurement_id | doc | paragraph | 原值 | 单位 | 换算到规范单位 | 口径 | 六维可比性摘要 |
|---|---|---|---|---|---|---|---|
| M-001 | DOC-01 | P004 | 96 | % | 96 % (reported) | η=(C0−Ct)/C0, UV-2600 UV-Vis 分光光度计测定 554 nm 吸光度, 30 min 暗吸附平 | units:comparable; metric:review; task:comparable; material:comparable; pollutant:comparable; budget:not_comparable |
| M-006 | DOC-03 | P002 | 0.92 | fraction | 92 % (derived) | 1−Ct/C0, 554 nm 吸光度, 同型号 UV-Vis 仪器 | units:comparable; metric:review; task:comparable; material:comparable; pollutant:comparable; budget:not_comparable |

### 六维度可比性判定

| 维度 | 结论 | 依据 |
|---|---|---|
| task | comparable | 取值一致: photocatalytic_degradation |
| metric | review | 口径不一致(auto 标记, agent 复核): M-001: η=(C0−Ct)/C0, UV-2600 UV-Vis 分光光度计测定 554 nm 吸光度, 30 min 暗吸附平; M-006: 1−Ct/C0, 554 nm 吸光度, 同型号 UV-Vis 仪器 |
| units | comparable | 量纲一致 1(无量纲); 单位写法 ['%', 'fraction'] 可互相换算(换算值标 derived) |
| material | comparable | 取值一致: g-C3N4 |
| pollutant | comparable | 取值一致: RhB |
| budget | not_comparable | 取值不同, 不得合并: M-001=300 W Xe lamp; M-006=150 W LED |

## 量类: rate_constant (规范比较单位: s^-1)

| measurement_id | doc | paragraph | 原值 | 单位 | 换算到规范单位 | 口径 | 六维可比性摘要 |
|---|---|---|---|---|---|---|---|
| M-004 | DOC-02 | P003 | 0.031 | min⁻¹ | 0.000516667 s^-1 (derived) | pseudo-first-order: ln(C0/Ct)=kt, 前 60 min 线性拟合, R²=0.98 | units:comparable; metric:comparable; task:comparable; material:comparable; pollutant:comparable; budget:comparable |

### 六维度可比性判定

| 维度 | 结论 | 依据 |
|---|---|---|
| task | comparable | 取值一致: photocatalytic_degradation |
| metric | comparable | 口径一致(auto): pseudo-first-order: ln(C0/Ct)=kt, 前 60 min 线性拟合, R²=0.98 |
| units | comparable | 量纲一致 T^-1; 单位写法 ['min⁻¹'] 可互相换算(换算值标 derived) |
| material | comparable | 取值一致: g-C3N4 |
| pollutant | comparable | 取值一致: RhB |
| budget | comparable | 取值一致: 300 W Xe lamp + 420 nm cutoff |

## 跨 quantity_kind 可比性(机检)

- catalyst_dosage ↔ concentration: **不可比** (quantity_kind 不同, 机检直接判不可比; 例如降解效率%与速率常数k不是同一个量)
- catalyst_dosage ↔ degradation_efficiency: **不可比** (quantity_kind 不同, 机检直接判不可比; 例如降解效率%与速率常数k不是同一个量)
- catalyst_dosage ↔ rate_constant: **不可比** (quantity_kind 不同, 机检直接判不可比; 例如降解效率%与速率常数k不是同一个量)
- concentration ↔ degradation_efficiency: **不可比** (quantity_kind 不同, 机检直接判不可比; 例如降解效率%与速率常数k不是同一个量)
- concentration ↔ rate_constant: **不可比** (quantity_kind 不同, 机检直接判不可比; 例如降解效率%与速率常数k不是同一个量)
- degradation_efficiency ↔ rate_constant: **不可比** (quantity_kind 不同, 机检直接判不可比; 例如降解效率%与速率常数k不是同一个量)
