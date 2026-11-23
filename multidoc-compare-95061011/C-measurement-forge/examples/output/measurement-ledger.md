# Measurement Ledger(测量台账)

> 每格 = 一条测量记录: value + unit(解析为 SI 量纲向量与换算因子) + quantity_kind
> + metric_definition(口径随值走) + condition_context + 逐字 quote + doc/paragraph。
> SI 换算列一律为 derived; 原值原文保留。

## catalyst_dosage

- 定义: 催化剂投加量, 质量/体积量纲(常见 mg/L 或 g/L)。
- 口径要求: 注明投加量基准(单位反应液体积)与催化剂形式(粉体/复合物/负载型)。mg/L 与 g/L 混用时换算列标 derived, 原值保留。

| id | 原值 | SI 换算 | 单位 | 口径(metric_definition) | 条件窗 | doc | paragraph | quote |
|---|---|---|---|---|---|---|---|---|
| M-002 | 0.5 | 0.5 [L^-3·M] (derived) | g/L | 催化剂投加量, 以单位反应液体积的 g-C3N4 粉体质量计 | 50 mL 反应液, RhB 10 mg/L | DOC-01 | P003 | "In a typical run, 50 mL of RhB solution with an initial concentration C0 of 10 mg/L was mixed with the catalyst at a dosage of 0.5 g/L." |
| M-005 | 1 | 1 [L^-3·M] (derived) | g/L | 催化剂投加量, 以单位反应液体积的 g-C3N4 粉体质量计 | RhB 15 mg/L, 420 nm 截止滤光片 | DOC-02 | P002 | "Experiments were carried out with an initial RhB concentration of 15 mg/L and a catalyst dosage of 1 g/L under a 300 W xenon lamp with a 420 nm cutoff filter." |
| M-007 | 500 | 0.5 [L^-3·M] (derived) | mg/L | 催化剂投加量, 以单位反应液体积的 g-C3N4 粉体质量计 | RhB 10 mg/L, 150 W LED | DOC-03 | P002 | "The RhB initial concentration was 10 mg/L and the catalyst dosage was 500 mg/L, irradiated with a 150 W LED source." |

## concentration

- 定义: 污染物(染料等)的浓度, 质量/体积量纲。
- 口径要求: 注明是初始浓度 C0 还是时间 t 浓度 Ct、测定仪器与波长、以及是否为换算值(derived)。

| id | 原值 | SI 换算 | 单位 | 口径(metric_definition) | 条件窗 | doc | paragraph | quote |
|---|---|---|---|---|---|---|---|---|
| M-003 | 10 | 0.01 [L^-3·M] (derived) | mg/L | RhB 初始浓度 C0 | 50 mL 反应液, 暗吸附前配制 | DOC-01 | P003 | "In a typical run, 50 mL of RhB solution with an initial concentration C0 of 10 mg/L was mixed with the catalyst at a dosage of 0.5 g/L." |

## degradation_efficiency

- 定义: 污染物降解效率: 在给定照射时间 t 内被降解的污染物比例, 无量纲。
- 口径要求: 必须记录计算公式(通常 η=(C0−Ct)/C0 或 1−(Ct/C0))与测定方式: 测定波长(如 554 nm)、测定仪器(如 UV-Vis 分光光度计)、C0 与 Ct 的取样时间窗。仅写 'degradation 96%' 而无公式口径者不得进入比较。

| id | 原值 | SI 换算 | 单位 | 口径(metric_definition) | 条件窗 | doc | paragraph | quote |
|---|---|---|---|---|---|---|---|---|
| M-001 | 96 | 0.96 [1(无量纲)] (derived) | % | η=(C0−Ct)/C0, UV-2600 UV-Vis 分光光度计测定 554 nm 吸光度, 30 min 暗吸附平衡后取样 | g-C3N4, RhB C0=10 mg/L, 投加量 0.5 g/L, 300 W 氙灯, 照射 90 min | DOC-01 | P004 | "RhB was degraded 96% within 90 min of irradiation." |
| M-006 | 0.92 | 0.92 [1(无量纲)] (derived) | fraction | 1−Ct/C0, 554 nm 吸光度, 同型号 UV-Vis 仪器 | g-C3N4, RhB 10 mg/L, 投加量 500 mg/L, 150 W LED, 反应 120 min | DOC-03 | P002 | "The removal efficiency reached 0.92 after 120 min of reaction." |

## rate_constant

- 定义: 准一级/准二级降解动力学速率常数 k。
- 口径要求: 必须记录动力学模型(如 pseudo-first-order, ln(C0/Ct)=kt)与线性拟合区间(R²、数据点数)。速率常数与降解效率是不同的量: 二者即使在同一篇内也不可直接互换比较。

| id | 原值 | SI 换算 | 单位 | 口径(metric_definition) | 条件窗 | doc | paragraph | quote |
|---|---|---|---|---|---|---|---|---|
| M-004 | 0.031 | 0.000516667 [T^-1] (derived) | min⁻¹ | pseudo-first-order: ln(C0/Ct)=kt, 前 60 min 线性拟合, R²=0.98 | g-C3N4, RhB C0=15 mg/L, 投加量 1 g/L, 300 W 氙灯+420 nm 截止滤光片 | DOC-02 | P003 | "The degradation followed pseudo-first-order kinetics according to ln(C0/Ct) = kt, giving a rate constant k = 0.031 min⁻¹ over the first 60 min of irradiation (R² = 0.98)." |
