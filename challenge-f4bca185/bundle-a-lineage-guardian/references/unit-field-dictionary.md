# Field Alias and Unit Dictionary

本字典是脚本实际登记规则的说明。未列出的写法不等于错误；它们会被保守地放入 `unmapped_fields` 或标记 unknown unit，而不会被模型临时猜测。

## 1. Canonical fields

| canonical field | 语义 | 空值策略 |
|---|---|---|
| `material_name` | 材料/物质/样品显示名 | 无证据时 null |
| `material_id` | CAS、SMILES、InChI 等提取记录给出的标识 | 不从名称反推 |
| `property_name` | 指标/参数名称 | 不从单位反推 |
| `property_value_raw` | 原始属性值文本 | 永远保留 |
| `property_value_text` | NFC/去外缘空白后的显示值 | missing token 为 null |
| `property_value_number` / `_min` / `_max` | 原始数字、区间端点 | 非数字为 null |
| `unit_raw` / `unit_canonical` / `unit_family` | 原单位、目标单位、单位族 | 未知单位不转换 |
| `value_standard` / `_min` / `_max` | 目标单位下标准值 | 无安全单位时为 null |
| `temperature_c` / `_min` / `_max` | 摄氏温度标量/区间 | 无单位不默认 °C |
| `pressure_kpa` / `_min` / `_max` | kPa 压力标量/区间 | 无单位不换算 |
| `time_s` / `_min` / `_max` | 秒时间标量/区间 | 无单位不换算 |
| `concentration` / `_min` / `_max` / `_unit` | 浓度及目标单位 | 未知浓度表示法不转换 |
| `experiment_id` | 抽取记录给出的实验/批次 ID | 不用行号代替 |
| `literature_ref` | DOI、页码、引用或来源定位文本 | 不从文件名反推文献 |
| `conditions` | 独立条件文本 | 原义保留 |
| `extraction_context` | 备注、上下文、注释 | 原义保留 |

`conditions_canonical` 是用于重复上下文判断的结构化副本，不是新实验事实。`unmapped_fields` 是防数据丢失区，不是废弃区。

## 2. Header aliases（大小写/空白规范化后匹配）

| canonical field | 已登记别名 |
|---|---|
| material_name | material; material name; material label; substance; substance name; compound; compound name; chemical; sample; sample name; system; 材料; 材料名称; 物质; 物质名称; 化合物; 样品; 样品名称 |
| material_id | material id; substance id; cas; cas no; cas number; cas registry number; smiles; inchi; 材料id; 材料编号; cas号; 物质编号 |
| property_name | property; property name; metric; metric name; parameter; indicator; measurement; property metric; property/metric; 性质; 属性; 指标; 参数 |
| property_value | value; result; result value; measured value; measurement value; data; value extracted; extracted value; property value; reading; 数值; 结果; 测量值 |
| unit_raw | unit; units; value unit; measurement unit; 单位; 数值单位 |
| temperature_c | temperature; temp; t; temperature c; temperature degc; reaction temperature; annealing temperature; 温度; 反应温度; 退火温度 |
| pressure_kpa | pressure; p; pressure kpa; reaction pressure; 压力; 反应压力 |
| time_s | time; duration; reaction time; annealing time; holding time; 时间; 时长; 反应时间; 退火时间 |
| concentration | concentration; conc; molarity; 浓度; 摩尔浓度 |
| concentration_unit | concentration unit; conc unit; 浓度单位 |
| experiment_id | experiment; experiment id; exp id; experiment no; batch; batch id; run id; record id; 实验; 实验id; 实验编号; 批次 |
| literature_ref | reference; source; doi; paper; paper doi; citation; literature; title; pages; page; locator; 文献; 文献来源; 引用; doi号 |
| conditions | conditions; condition; experiment conditions; 实验条件; 条件 |
| extraction_context | context; notes; note; remarks; remark; comment; comments; details; extraction context; 备注; 注释; 上下文; 抽取上下文 |

支持 `Temp (°C)`、`Pressure (kPa)`、`Value_kJ` 这类 header default unit。值内显式单位优先于 header default。两个非空列映射到同一字段且内容不同，触发 R-FLD-005，不覆盖。

## 3. Property synonyms（只限显式登记）

| 输入写法（规范化后） | canonical |
|---|---|
| bandgap / band gap / band_gap / eg | band_gap |
| electrical conductivity / conductivity | conductivity |
| product yield / yield | yield |
| annealing time | annealing_time |
| reaction time | reaction_time |
| glass transition / tg | glass_transition_temperature |
| plqy / photoluminescence quantum yield | plqy |
| density | density |
| swelling energy | swelling_energy |

化学/材料名称不做模糊同义归一。只有 `material_id` 相同才在重复语义键中优先使用 ID；名称不同不会被自动断言为同一物质。

## 4. Numeric and range grammar

- 数字：十进制、前导小数点、科学计数法；`1,234.5` 按千分位处理，`1,2` 按小数逗号处理。更含糊的逗号格式不解析。
- 区间：`–`、`—`、`~`、`～`、`..`、`to`，以及两个数字之间的连字符。端点分开保存。
- 不创建区间中点；不把 uncertainty 自动并入区间；不解析没有登记语法的复杂分布。
- missing token：空、`-`、`--`、`—`、`n/a`、`na`、`n.r.`、`nr`、`none`、`null`、`not reported`、`not available`、`missing`、`未报告`、`未提供`、`缺失`、`无`。

## 5. Unit conversion table

Decimal 因子按“原单位值 × factor = 目标单位值”解释；温度仿射公式单列。

| 输入单位（规范化后） | family | target | factor/formula |
|---|---|---|---|
| °C, ℃, degC, Celsius, degree(s) Celsius | temperature | degC | `C = C` |
| K, Kelvin | temperature | degC | `C = K - 273.15` |
| °F, ℉, degF, Fahrenheit | temperature | degC | `C = (F - 32) * 5/9` |
| s, sec(s), second(s) | time | s | 1 |
| ks, kilosecond(s) | time | s | 1000 |
| ms, millisecond(s) | time | s | 0.001 |
| us, µs, μs, microsecond(s) | time | s | 0.000001 |
| min(s), minute(s) | time | s | 60 |
| h, hr(s), hour(s) | time | s | 3600 |
| d, day(s) | time | s | 86400 |
| kPa, kilopascal(s) | pressure | kPa | 1 |
| Pa, pascal(s) | pressure | kPa | 0.001 |
| MPa, megapascal(s) | pressure | kPa | 1000 |
| bar | pressure | kPa | 100 |
| mbar | pressure | kPa | 0.1 |
| atm, atmosphere(s) | pressure | kPa | 101.325 |
| psi | pressure | kPa | 6.894757 |
| J, joule(s) | energy | J | 1 |
| kJ, kilojoule(s) | energy | J | 1000 |
| MJ, megajoule(s) | energy | J | 1000000 |
| eV, electronvolt(s) | energy | J | 1.602176634e-19 |
| M, molar, mol/L, mol L-1 | concentration | mol/L | 1 |
| mM, mmolar, mmol/L | concentration | mol/L | 0.001 |
| µM/μM, µmol/L/μmol/L | concentration | mol/L | 0.000001 |
| %, percent, percentage, wt%, vol% | percent | % | 1 |
| fraction, ratio, dimensionless | dimensionless | 1 | 1 |
| ppm | concentration_ratio | ppm | 1 |
| ppb | concentration_ratio | ppb | 1 |

### 保守边界

- 小写 `m` 不解释为 molar，因为它常与 metre 冲突；明确 `M` 才按 molar。
- `g/100 g water`、任意复合速率、复杂暴露剂量、未登记组合单位均为 unknown unit，不能靠字符串相似猜测。
- `%` 不转换为 0–1 fraction；`fraction` 也不转换为百分比，因为抽取上下文可能不同。
- `eV` 换算到 J 使用 SI 精确值 `1.602176634e-19`；微小 JSON 浮点显示不改变原始值。
- header default unit 只在该列无更明确值内单位时使用。

## 6. Precision policy

计算使用 Python standard-library `Decimal`。JSON 输出数值不补无意义尾零；CSV 用规范化十进制文本。`property_value_raw` 和 `raw_snapshot.json` 才是精度/格式的权威记录。若评审需要严格有效数字，应沿 change log 的 formula 和 row fingerprint 回查原始单元格，而不是从 JSON float 反推。
