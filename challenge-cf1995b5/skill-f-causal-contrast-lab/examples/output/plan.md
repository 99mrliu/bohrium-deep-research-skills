<!-- 合成示例输出，非正式测评结果 -->
# 因果对照实验执行方案

- **案例**：synthetic-enzyme-contrast-001 — 区分真实直接酶抑制、化合物荧光干扰与聚集效应
- **状态**：PASS；本文件为前瞻性方案，不含实测结果。
- **费用口径**：CNY synthetic scenario units；仅为合成情景的前瞻资源/价格/预订合同，不是供应商报价、库存确认或采购批准。

## 1. 可证伪机制假设
以同一独立制备批次内的配对因果对照区分三种可竞争解释：催化初速的真实下降、化合物自身荧光造成的表观信号变化，以及对洗涤剂敏感的聚集型抑制。先做光学背景判读，再解释扣除匹配背景后的酶反应初速；不以单一表观IC50下结论。
| ID | 假设 | 预测 | 证伪条件 |
|---|---|---|---|
| H1 | 在本合成协议条件下，化合物X降低酶E的催化初速，且该效应不能仅由光学背景解释。 | 匹配载体与无酶/化合物单独背景校正后，X组初速随浓度下降，且每个独立生物学重复方向一致；已知抑制剂K显示阳性窗口。 | 在所有达到可接受QC的独立重复中，X组背景校正初速未达到预设下降判据，或表观效应可由化合物光学背景完全解释。 |
| H2 | X的化合物自身荧光或无酶信号变化可产生类似抑制的表观读数。 | 无酶+X随X浓度增加出现可测的背景斜率或终点偏移；化合物单独孔提供背景幅度，扣除后H1效应减弱或消失。 | 在各X浓度下，无酶和化合物单独背景均低于预设干扰阈值，且完整背景校正不改变初速结论。 |
| H3 | X的至少部分表观抑制对低浓度非离子洗涤剂敏感，符合聚集相关替代解释。 | 相同X浓度下，加入洗涤剂前后的背景校正抑制率出现预设幅度的差异。 | 在洗涤剂本身通过QC的条件下，各独立重复的抑制率差异均低于预设分流幅度。洗涤剂不敏感仍不能排除所有聚集或其他非特异机制。 |

## 2. 操作化变量
| ID | 类型 | 单位 | 操作定义 | 测量 | 允许水平 | 来源 |
|---|---|---|---|---|---|---|
| IV_X | independent | µM | 反应开始时孔内X的标称终浓度；每个浓度的配对孔共享同一分装与加样序列。 | 由母液浓度和两次体积分配合成计算；本方案不使用实测纯度校正。 | [0.03,0.1,0.3,1,3,10] | case_json:$.parameter_domains.compound_uM；合成协议选取的有限水平 |
| IV_DETERGENT | independent | % v/v | 在X与酶预孵育阶段加入0.01% v/v洗涤剂，匹配孔不加洗涤剂但保持其余体积和载体一致。 | 按工作液体积/预孵育总体积计算终浓度。 | [0,0.01] | case_json:$.parameter_domains.detergent_percent；合成反筛假设 |
| DV_RATE | dependent | RFU/min及载体归一化百分比 | 每个孔在3–8 min内产物RFU对时间的线性斜率，扣除匹配无酶背景后，相对同区组载体孔归一化。 | 读板机导出未舍入时间序列；锁定窗口后用固定线性斜率算法计算，保留孔级数据。 | ["实测前不预设数值或范围；只接收通过固定窗口和QC的可追溯孔级值，不将本协议假设当作实测结果"] | case_json:$.protocol_assumptions.initial_rate_window_min；实测前无数值 |

## 3. 对照—替代解释映射
| ID | 类型 | 条件 | 排除的替代解释 | 威胁 | 假设 |
|---|---|---|---|---|---|
| C_VEHICLE | vehicle | 相同酶、底物和载体终浓度，不含X；每个独立重复与每个洗涤剂条件均设置。 | 载体、蒸发、板内位置或当日制备差异造成的表观抑制。 | 载体不匹配、边缘蒸发或跨日比较可伪造剂量趋势。 | ["H1","H3"] |
| C_NO_ENZYME | no_enzyme | 底物、X各浓度及载体均与反应孔一致，以缓冲液替代酶；分有/无洗涤剂配对。 | 底物自发转化、非酶催化和X依赖的底物光学变化被误认为酶抑制。 | 缺酶匹配浓度会留下错误的背景扣除。 | ["H1","H2"] |
| C_KNOWN_INHIBITOR | known_inhibitor | 以1 µM合成已知抑制剂K替代X，反应组成和读数与X孔一致；每个独立重复设置。 | 酶失活、底物失效或读数窗口不敏感导致假阴性。 | 阳性窗口失败时不能解释X阴性；K的作用也不能证明X具有同一机制。 | ["H1"] |
| C_COMPOUND_ONLY | compound_only_fluorescence | 不含酶与底物，仅缓冲液、匹配载体和各X浓度；使用同一板型、滤光设置和动力学历程。 | X自身荧光、荧光淬灭或光散射被当成产物形成变化。 | 仅做无酶+底物不能分离X与底物相互作用和X自身背景。 | ["H2"] |
| C_DETERGENT | detergent_counter_screen | 所有关键X浓度及载体在同一独立批次内配对设置0与0.01% v/v洗涤剂；同时检查载体和K窗口。 | 对洗涤剂敏感的聚集相关非特异抑制被解释为直接催化抑制。 | 洗涤剂可能改变底物或酶基线；反筛敏感不是聚集的直接结构证据。 | ["H1","H3"] |

## 4. 主要读数与前瞻决策
| ID | 读数 | 方向 | 指标/单位 | 判据 | 决策规则 | 证据 |
|---|---|---|---|---|---|---|
| R1 | 背景校正初始速率与抑制幅度 | 相对于同区组匹配载体，支持H1的方向为背景校正初速下降；上升或不变不支持该方向的H1。 | 3–8 min线性RFU斜率，经匹配无酶和化合物背景校正后归一化至载体 / RFU/min；percentage_of_vehicle | 至少两个相邻X浓度均达到≥30%下降，三个独立生物学重复方向一致，且相关载体技术复孔CV≤10%；先通过R2干扰判读。 | 满足判据：进入洗涤剂配对R3并仅表述为条件下真实催化抑制；不满足：若阳性对照和QC合格则判为未支持H1，若QC失败则判为不可判定并重做失败区组。 | ["E1","E2","E3"] |
| R2 | X自身荧光与无酶干扰 | 化合物单独或无酶孔随X浓度上升的背景斜率/偏移支持H2；低于干扰阈值不支持光学解释。 | 每µM X的背景RFU斜率增量与完整反应和无酶孔之间的斜率差 / RFU·min⁻¹·µM⁻¹ | 任一X浓度对应匹配背景超过100 RFU/µM的合成预警阈值，或背景校正使R1结果跨越30%决策点。 | 达到预警：先标记光学干扰，禁止报告未校正的抑制；用逐孔匹配背景重算R1，校正后不足30%则支持H2作为充分替代解释。背景不稳定或非线性则判不可判定并调整读数设置，不选择性删除孔。 | ["E3","E4"] |
| R3 | 洗涤剂前后抑制率差 | 加洗涤剂后抑制率下降支持H3；不变或上升不支持该替代解释。 | 同一独立批次内无洗涤剂抑制率减有洗涤剂抑制率 / percentage_points | 在0.01%洗涤剂自身载体QC通过时，同一X浓度的配对差≥20个百分点且三个独立重复同向。 | 达到判据：降级为聚集相关抑制待证，禁止仅据动力学曲线宣称直接结合；追加正交粒径/浓度依赖性或替代活性测法。未达判据：不把H3作为本组解释，但仍保留其他非特异机制不确定性。 | ["E3","E5"] |

## 5. 重复、随机化、区组与盲法
```json
{
  "biological_repeats": 3,
  "technical_wells": 3,
  "independent_unit": "三个不同日期的独立酶/底物制备和独立配液批次；每天构成一个重复区组。",
  "technical_unit": "同一独立批次内每条件三个孔，用于估计加样/读数重复性。",
  "distinction": "统计决策以三个独立制备/日期为n；先对条件内技术复孔按预设规则汇总，不把9个孔当成n=9。",
  "randomization": {
    "relevant": true,
    "method": "每个区组内以预登记随机 seed 对条件位置随机化；无酶、化合物单独和载体对照均衡分布于板内，禁止按结果改位。"
  },
  "blocking": {
    "relevant": true,
    "method": "日期/独立制备为区组；每个区组包含全套条件，洗涤剂与无洗涤剂在同一区组配对。"
  },
  "blinding": {
    "relevant": true,
    "method": "由第二人编码X/K样品；读数与初速分析使用条件编码，QC锁库和决策表生成后揭盲。"
  }
}
```
**独立生物学重复不等于技术复孔；不得合并后虚增独立样本量。**
## 6. 参数与执行步骤
### 参数
```json
{
  "enzyme_nM": 1,
  "substrate_uM": 20,
  "compound_uM": [
    0.03,
    0.1,
    0.3,
    1,
    3,
    10
  ],
  "known_inhibitor_uM": 1,
  "detergent_percent": 0.01,
  "incubation_min": 5,
  "readout_temp_C": 25,
  "biological_repeats": 3,
  "technical_wells": 3,
  "plate_type": "black_384"
}
```
### 步骤
| ID | 时长(min) | 操作 | 资源ID | 参数 | QC | 验收 |
|---|---|---|---|---|---|---|
| S1 | 30 | 锁定分析表、随机种子、条件编码和原始文件命名；每区组制备载体、无酶、K、X单独、完整反应及±洗涤剂布局。 | ["EQ_MULTICHANNEL","RS_PLATE"] | {"plate_type":"black_384","biological_repeats":3,"technical_wells":3} | 布局核对者独立确认所有对照、浓度、方向及每条件孔数；检查无漏设的±洗涤剂配对。 | 布局表逐孔无重复ID/遗漏且随机化记录封存，否则不得加样。 |
| S2 | 20 | 按三个独立日期分别制备酶、底物和化合物工作液；设置0与0.01%洗涤剂匹配预混液。 | ["EQ_MULTICHANNEL","RS_ENZYME","RS_SUBSTRATE","RS_COMPOUND","RS_DETERGENT"] | {"compound_uM":[0.03,0.1,0.3,1,3,10],"detergent_percent":0.01} | 记录配液计算、实际时间和载体终浓度；洗涤剂载体对照先检查沉淀/异常背景。 | 配液计算复核且匹配组载体一致；可见沉淀或载体异常时该区组无效并触发风险分支。 |
| S3 | 5 | 将X或K与酶预孵育；无酶孔以相同缓冲液替代，化合物单独孔同时不加底物。 | ["EQ_MULTICHANNEL","RS_ENZYME","RS_INHIBITOR","RS_COMPOUND"] | {"enzyme_nM":1,"known_inhibitor_uM":1,"incubation_min":5} | 记录预孵育起止；所有孔保持相同加样顺序间隔。 | 预孵育为5 min且各组时序匹配，否则该区组暂停判读。 |
| S4 | 15 | 加入合成底物启动相应反应；无底物的化合物单独孔加入匹配缓冲液，立即转入动力学读数。 | ["EQ_MULTICHANNEL","RS_SUBSTRATE","EQ_READER"] | {"substrate_uM":20,"readout_temp_C":25} | 记录每列启动和首次读数时间；检查气泡、溅出及温度设定。 | 启动延迟在预登记容许记录内且无影响读数的气泡；异常孔保留原始值并标记，不得静默删除。 |
| S5 | 60 | 导出全时间序列，先判读无酶/化合物单独背景，再计算3–8 min固定窗口初速；技术复孔先在条件内QC，然后以区组为独立n执行R1–R3决策。 | ["EQ_READER"] | {"enzyme_nM":1,"compound_uM":[0.03,0.1,0.3,1,3,10],"readout_temp_C":25,"biological_repeats":3,"technical_wells":3} | 锁定窗口与扣除规则后揭盲；保留未校正和校正数据、排除原因及载体CV。 | 三个独立区组均有完整原始轨迹和可追溯决策；QC失败者标不可判定而不是阴性。 |
| S6 | 20 | 依据R1–R3生成预先定义的支持/不支持/不可判定结论，保存候选修订、偏差日志和下一步正交实验建议。 | ["EQ_MULTICHANNEL"] | {} | 第二人从原始孔级数据复核一个完整区组及全部跨决策阈值样本。 | 所有结论均能回溯到原始孔、匹配对照、独立重复和前瞻判据；未观察值不得填成实测结果。 |

## 7. 资源、精确成本与日程
### 资源
| ID | 类别 | 型号/规格 | 能力要求 | 预订状态 |
|---|---|---|---|---|
| EQ_READER | equipment | 未指定；不得伪造，执行前核对实际型号与滤光片 | 25 °C温控、3–8 min动力学历程、适配荧光底物的激发/发射设置、原始孔级时间序列导出。 | prospective_unbooked_requires_confirmation |
| EQ_MULTICHANNEL | equipment | 未指定通用多道移液器 | 覆盖配液体积并适配black_384板；校准状态需现场确认。 | prospective_availability_unconfirmed |
| RS_PLATE | consumable | 通用低自发荧光黑色384孔板 | 4块，板型与读板机匹配。 | prospective_not_purchased |
| RS_SUBSTRATE | reagent | 合成荧光底物，无真实品牌 | 2个工作液批次；±洗涤剂兼容性先做载体QC。 | prospective_not_purchased |
| RS_ENZYME | reagent | 合成酶E，无真实品牌或批号 | 3个独立制备批次，每批次同一天完成所有条件。 | prospective_not_purchased |
| RS_INHIBITOR | reagent | 合成已知抑制剂K | 1分装；只用于确认检测窗口，不提供X机制外推。 | prospective_not_purchased |
| RS_COMPOUND | reagent | 合成化合物X | 1套等比分装；浓度和纯度未实测。 | prospective_not_purchased |
| RS_DETERGENT | reagent | 合成非离子洗涤剂 | 1分装；化学类别、相容性及实际工作浓度需按本地SOP确认。 | prospective_not_purchased |

### 成本（Decimal 重算）
| 项目 | 资源 | 单价 | 数量 | 小计 |
|---|---|---|---|---|
| 荧光读板机8小时 | EQ_READER | 20 | 8 | 160 |
| 黑色384孔板 | RS_PLATE | 12 | 4 | 48 |
| 底物工作液 | RS_SUBSTRATE | 30 | 2 | 60 |
| 酶独立制备 | RS_ENZYME | 40 | 3 | 120 |
| 已知抑制剂K | RS_INHIBITOR | 18 | 1 | 18 |
| 化合物X | RS_COMPOUND | 25 | 1 | 25 |
| 洗涤剂反筛 | RS_DETERGENT | 5 | 1 | 5 |

**重算总成本：436；单轮步骤合计：150 min；按独立重复展开总工作：350 min；日程：4 天。** 所有价格、供应与仪器时段均非供应商报价或批准。
### 时间合同（重复展开与仪器预订分开）
```json
{
  "declared": {
    "one_time_step_ids": [
      "S1",
      "S6"
    ],
    "per_biological_repeat_step_ids": [
      "S2",
      "S3",
      "S4",
      "S5"
    ],
    "total_work_minutes": 350,
    "instrument_booking_minutes": 480,
    "note": "S1+S6=50分钟一次性工作；S2–S5=100分钟/独立重复，三次为300分钟；总工作350分钟。读板机预订480分钟=8小时，包含预热、周转和失败余量，不能当作净步骤耗时。"
  },
  "recomputed": {
    "total_work_minutes": "350",
    "one_time_minutes": "50",
    "per_repeat_minutes": "100",
    "repeats": "3"
  }
}
```
### 日程
```json
{
  "total_days": 4,
  "milestones": [
    {
      "day": 1,
      "activity": "确认读板机能力/预订、本地SOP与耗材；冻结随机化、布局和分析表。"
    },
    {
      "day": 2,
      "activity": "独立重复1：全流程、原始数据导出和载体QC。"
    },
    {
      "day": 3,
      "activity": "独立重复2与3：分别独立配液/制备，同日完成各自全流程。"
    },
    {
      "day": 4,
      "activity": "盲态QC、揭盲决策、复核和归档；如QC失败，仅重做失败区组且不超7日上限。"
    }
  ]
}
```
## 8. 可追溯证据
| ID | 来源类别 | 定位符 | 支持对象 | 原文/规范JSON值 | 机械核验 |
|---|---|---|---|---|---|
| E1 | case_json | $.protocol_assumptions.initial_rate_window_min | ["H1","DV_RATE","R1","S5"] | [3,8] | PASS |
| E2 | case_json | $.protocol_assumptions.decision_assumptions.inhibition_threshold_percent | ["H1","R1"] | 30 | PASS |
| E3 | provided_markdown | source_note.md#synthetic-assumptions | ["H1","H2","H3","R1","R2","R3"] | 协议规划假设：先在内源背景与化合物背景扣除后评估初速变化，再联合无酶、化合物单独荧光和洗涤剂反筛结果作出机制分流。 | PASS |
| E4 | case_json | $.mechanism_context.interference_concern | ["H2","C_NO_ENZYME","C_COMPOUND_ONLY","R2"] | "化合物X的荧光可能冒充产物信号；无酶和化合物单独对照用于识别此替代解释。" | PASS |
| E5 | case_json | $.mechanism_context.aggregation_concern | ["H3","C_DETERGENT","R3"] | "化合物聚集可造成非特异性抑制；低浓度非离子洗涤剂反筛用于检验该替代解释，但不把洗涤剂敏感性视为唯一机制证明。" | PASS |
| E6 | case_json | $.resource_contract.disclaimer | ["resource_contract","confirmation_items"] | "仅为合成情景的前瞻资源/价格/预订合同，不是供应商报价、库存确认或采购批准。" | PASS |

## 9. 风险、触发与备选
| ID | 风险 | 可能性 | 影响 | 缓解 | 触发 | 备选 |
|---|---|---|---|---|---|---|
| RISK_OPTICAL | X背景非线性或超过线性检测范围，简单扣除不足。 | unknown_before_measurement | R1不可判定或假阳性/假阴性。 | 固定动力学窗口，保留化合物单独和无酶全梯度，不依赖单终点扣除。 | R2超过预警、背景轨迹非线性或校正改变30%决策。 | 先判光学干扰；在实际设备许可下改用位移光谱/更低X水平或正交非荧光读数，并重新审计参数域。 |
| RISK_BASELINE | 洗涤剂改变载体或K对照基线。 | unknown_before_measurement | R3配对差无法特异地归因于X聚集。 | 每个区组设置±洗涤剂载体与K对照，配对分析。 | 洗涤剂载体CV>10%或K窗口失效。 | 该区组R3标不可判定，不比较跨日期均值；优化相容性后重做失败区组。 |
| RISK_SOLUBILITY | 高浓度X沉淀或可见浑浊。 | unknown_before_measurement | 标称浓度不等于可用浓度，剂量斜率失真。 | 配液后和反应后检查并记录所有孔，保留异常标记。 | 任一浓度出现沉淀、浑浊或散射样轨迹。 | 该水平只判不可判定；下修至参数域内较低水平并考虑溶解度/粒径正交测量，不把表观IC50当直接结合。 |
| RISK_BOOKING | 通用读板机能力或7日内时段不满足。 | unknown_until_confirmed | 无法按3–8 min窗口完成三组独立重复。 | 第1日优先核对温控、滤光片、动力学导出和共8机时预订。 | 第1日无可用设备或原始时间序列不能导出。 | 状态保持partial并请求改期/替代设备；不得虚构设备型号或跳过对照来伪装可执行。 |

## 10. 相对候选方案的修订
```json
{
  "base_candidate_id": "CAND_C_FULL_OVERDUE",
  "changes": [
    {
      "field": "est_days",
      "from": 10,
      "to": 4,
      "reason": "将三个独立区组并行规划在第2–3日，保留完整对照；日程满足7日上限。"
    },
    {
      "field": "parameters.detergent_percent",
      "from": 0.015,
      "to": 0.01,
      "reason": "修正为相对min=0、step=0.01的合法有限域值。"
    },
    {
      "field": "total_cost",
      "from": 333,
      "to": 436,
      "reason": "补齐X单独背景、已知抑制剂和±洗涤剂反筛的实际资源条目，Decimal重算为436。"
    },
    {
      "field": "causal_decision_structure",
      "from": "候选计划仅提供名称/参数/费用，未提供可执行判据",
      "to": "H1–H3、五类映射对照、R1–R3和不可判定分支",
      "reason": "把成本合规与因果可识别性分开；先排除光学解释再解释真实抑制。"
    }
  ],
  "comparison": [
    {
      "dimension": "identifiability",
      "before": "无显式假设—对照—读数映射",
      "after": "每个对照映射替代解释/威胁和假设；先R2再R1，随后R3",
      "effect": "能够区分主要竞争解释，并保留不可判定结论"
    },
    {
      "dimension": "parameter_validity",
      "before": "detergent_percent=0.015偏离step=0.01",
      "after": "0.01；所有可执行参数通过Decimal域审计",
      "effect": "消除机械域违规"
    },
    {
      "dimension": "cost",
      "before": "333（虽算术相等但资源覆盖不足）",
      "after": "436（7项逐项重算，预算800）",
      "effect": "增加103合成预算单位，保留364余量；非报价"
    },
    {
      "dimension": "time",
      "before": "10天，超过7天",
      "after": "4天；单轮步骤150分钟，三轮独立重复展开总工作350分钟；另预订480分钟仪器时段",
      "effect": "排程合规；仪器8小时仍需预订"
    }
  ]
}
```
### 候选方案机械审计（原方案的 FAIL 不自动否决经审计的修订方案）
| 候选 | 状态 | 重算成本 | 错误 | 警告 |
|---|---|---|---|---|
| CAND_A_PARTIAL | FAIL | 184 | ["cost_subtotal 174 != recomputed 184","enzyme_nM: 0.15 is off step 0.1 from 0.1"] | [] |
| CAND_B_OPTICAL_GAP | FAIL | 276 | ["total_cost 266 != recomputed 276","compound_uM: 0.005 is below min 0.01","compound_uM: 0.005 is off step 0.01 from 0.01","technical_wells: 8 is above max 6"] | [] |
| CAND_C_FULL_OVERDUE | FAIL | 333 | ["est_days 10 days exceeds deadline 7 days","detergent_percent: 0.015 is off step 0.01 from 0"] | [] |

## 11. 不确定性、变更与待确认
### 不确定性
[
  "所有浓度、光学/洗涤剂判据和费用都是合成协议假设，不是文献值、实测结果或针对真实分子的有效性声明。",
  "3–8 min线性、底物/酶相容性与X浓度可用性必须先用原始轨迹和QC确认；不可判定时不能自动宣布阴性。",
  "洗涤剂敏感性只提供聚集相关解释的支持，不能单独证明聚集、直接结合、可逆性或选择性。",
  "当前示例没有真实PDF或外部论文输入；没有PDF内容可供推断。"
]
### 变更记录
[
  {
    "id": "CL1",
    "change": "从CAND_C的10日改为4日并将洗涤剂浓度修正为0.01。",
    "reason": "满足case资源合同与参数域。"
  },
  {
    "id": "CL2",
    "change": "增加C_COMPOUND_ONLY、C_NO_ENZYME及配对±洗涤剂条件，费用从333增至436。",
    "reason": "显式检验荧光和聚集替代解释，而非只优化表观剂量曲线。"
  },
  {
    "id": "CL3",
    "change": "把三个独立制备/日期与每条件三个技术孔分层，加入随机化、区组和盲态QC。",
    "reason": "避免伪重复并降低位置/操作者偏倚。"
  }
]
### 待确认事项
[
  "这是一份合成示意案例；实际执行前必须以真实[input]/材料和本地SOP替换全部合成参数与判据。",
  "确认实际读板机型号、滤光片、温控、动力学历程与原始时间序列导出能力；型号目前未知。",
  "确认EQ_READER共8小时的可用预订；当前状态为未预订，且不构成批准。",
  "确认所有耗材价格、供应、化学品安全资料和酶/底物/洗涤剂相容性；资源价格非供应商报价。",
  "确认合成已知抑制剂K在真实体系中是否适用；若不存在合适阳性对照，应把相关系统性假阴性列为未解决威胁。"
]

---
合成示例输出，非正式测评结果。所有阈值和参数均为本合成情景的前瞻性协议假设，不是实验观测或文献事实。
