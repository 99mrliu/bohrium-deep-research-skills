> 合成示例输出，非正式测评结果

# 事实登记表（fact registry）

- case_id: MOCK-PEROV-ANNEAL-001
- 生成器: scripts/case_reconcile.py extract（确定性机械提取）
- 事实总数: 138
- 来源类别: case_meta, contract, parameter_domain, candidate_claim, literature, text_embedded, inferred

## 统一设备表（合同 equipment 列表 + 文本内嵌补充合并）

| id | name | model | price_per_hour | origin | jsonpath |
|---|---|---|---|---|---|
| EQ-GB | 充氮手套箱 | MockBox-2 | 80 | contract | resource_contract.equipment[0] |
| EQ-SC | 匀胶机 | MockSpin-8 | 20 | contract | resource_contract.equipment[1] |
| EQ-HP | 精密加热台 | MockHot-300 | 30 | text_embedded | equipment_domain_note~embedded[0] |

## 事实明细（按来源类别分组）

### case_meta（6 条）

| id | value | unit | jsonpath | note |
|---|---|---|---|---|
| F001 | MOCK-PEROV-ANNEAL-001 | None | case_id |  |
| F002 | MAPbI3 钙钛矿薄膜退火工艺优化 | None | title |  |
| F003 | 在给定预算与周期内，从 3 个候选方案中修订出一个可执行的旋涂/退火工艺方案并给出验证设计。 | None | task |  |
| F004 | 优化 MAPbI3 perovskite 薄膜的 anneal 退火温度与 spin coating 旋涂转速组合，目标 PCE >= 19%，薄膜均匀无针孔。 | None | research_goal |  |
| F005 | 合成示意案例：为 exp-source-reconciler 示例手工构造，用于演示 extract/reconcile 对账，非真实测评数据。 | None | note |  |
| F138 | ["case_id", "revised_plan", "candidate_assessment", "validation", "status", "uncertainty", "sources", "change_log", "confirmation_items"] | None | output_contract.required_fields | result.json 必含字段 |

### contract（39 条）

| id | value | unit | jsonpath | note |
|---|---|---|---|---|
| F009 | 组织方前瞻合同：价格与预约信息为计划性约定，不是实际供应商报价或已确认排期。 | None | resource_contract.disclaimer |  |
| F010 | CNY | None | resource_contract.currency |  |
| F011 | 20000 | CNY | resource_contract.budget_cap | 预算上限（前瞻约定） |
| F012 | 30 | day | resource_contract.deadline_days | 周期上限 |
| F013 | EQ-GB | None | resource_contract.equipment[0].id |  |
| F014 | 充氮手套箱 | None | resource_contract.equipment[0].name |  |
| F015 | MockBox-2 | None | resource_contract.equipment[0].model |  |
| F016 | H2O/O2 < 1 ppm | None | resource_contract.equipment[0].spec |  |
| F017 | 80 | CNY/h | resource_contract.equipment[0].price_per_hour | 前瞻约定价，非已确认报价 |
| F018 | 30 | day | resource_contract.equipment[0].booking.window_days | 预约吞吐参数（计划性约定） |
| F019 | 3 | slot/week | resource_contract.equipment[0].booking.slots_per_week | 预约吞吐参数（计划性约定） |
| F020 | 4 | h | resource_contract.equipment[0].booking.slot_hours | 预约吞吐参数（计划性约定） |
| F021 | EQ-SC | None | resource_contract.equipment[1].id |  |
| F022 | 匀胶机 | None | resource_contract.equipment[1].name |  |
| F023 | MockSpin-8 | None | resource_contract.equipment[1].model |  |
| F024 | 500-8000 rpm | None | resource_contract.equipment[1].spec |  |
| F025 | 20 | CNY/h | resource_contract.equipment[1].price_per_hour | 前瞻约定价，非已确认报价 |
| F026 | 30 | day | resource_contract.equipment[1].booking.window_days | 预约吞吐参数（计划性约定） |
| F027 | 5 | slot/week | resource_contract.equipment[1].booking.slots_per_week | 预约吞吐参数（计划性约定） |
| F028 | 2 | h | resource_contract.equipment[1].booking.slot_hours | 预约吞吐参数（计划性约定） |
| F029 | RE-MAI | None | resource_contract.reagents[0].id |  |
| F030 | MAI | None | resource_contract.reagents[0].name |  |
| F031 | >=99.99% | None | resource_contract.reagents[0].spec |  |
| F032 | g | None | resource_contract.reagents[0].unit |  |
| F033 | 5 | None | resource_contract.reagents[0].pack_size |  |
| F034 | 250 | CNY/g | resource_contract.reagents[0].unit_price | 前瞻约定价，非已确认报价 |
| F035 | RE-PBI2 | None | resource_contract.reagents[1].id |  |
| F036 | PbI2 | None | resource_contract.reagents[1].name |  |
| F037 | >=99.99% | None | resource_contract.reagents[1].spec |  |
| F038 | g | None | resource_contract.reagents[1].unit |  |
| F039 | 10 | None | resource_contract.reagents[1].pack_size |  |
| F040 | 180 | CNY/g | resource_contract.reagents[1].unit_price | 前瞻约定价，非已确认报价 |
| F041 | RE-DMF | None | resource_contract.reagents[2].id |  |
| F042 | DMF | None | resource_contract.reagents[2].name |  |
| F043 | 无水级 | None | resource_contract.reagents[2].spec |  |
| F044 | bottle | None | resource_contract.reagents[2].unit |  |
| F045 | 1 | None | resource_contract.reagents[2].pack_size |  |
| F046 | 120 | CNY/bottle | resource_contract.reagents[2].unit_price | 前瞻约定价，非已确认报价 |
| F059 | 补充说明：除 equipment 列表外，本次还可预约一台精密加热台，信息如下片段：{"id":"EQ-HP","name":"精密加热台","model":"MockHot-300","spec":"室温-300 C, +/-1 C","price_per_hour":30,"booking":{"window_days":30,"slots_per_week":7,"slot_hours":8}}，请以该片段为准纳入设备对账。 | None | equipment_domain_note | 自由文本，可能内嵌补充设备片段 |

### parameter_domain（12 条）

| id | value | unit | jsonpath | note |
|---|---|---|---|---|
| F047 | {"min": 80, "max": 150, "step": 5} | C | parameter_domains.anneal_temperature_C | 区间域 |
| F048 | 设备手册+预实验 | None | parameter_domains.anneal_temperature_C.basis | 参数域依据类别 |
| F049 | case:resource_contract.equipment | None | parameter_domains.anneal_temperature_C.source | 参数域依据定位路径 |
| F050 | [2000, 3000, 4000, 6000] | rpm | parameter_domains.spin_coating_rpm.values | 枚举域 |
| F051 | 组织方有限参数域 | None | parameter_domains.spin_coating_rpm.basis | 参数域依据类别 |
| F052 | case:parameter_domains.spin_coating_rpm | None | parameter_domains.spin_coating_rpm.source | 参数域依据定位路径 |
| F053 | {"min": 5, "max": 30, "step": 5} | min | parameter_domains.anneal_time_min | 区间域 |
| F054 | 文献 | None | parameter_domains.anneal_time_min.basis | 参数域依据类别 |
| F055 | case:source.paper_pdf | None | parameter_domains.anneal_time_min.source | 参数域依据定位路径 |
| F056 | {"min": 0, "max": 2, "step": 0.5} | slm | parameter_domains.n2_flow_rate_slm | 区间域 |
| F057 | 预实验报告 | None | parameter_domains.n2_flow_rate_slm.basis | 参数域依据类别 |
| F058 | case:pre_experiment.report | None | parameter_domains.n2_flow_rate_slm.source | 参数域依据定位路径 |

### candidate_claim（72 条）

| id | value | unit | jsonpath | note |
|---|---|---|---|---|
| F066 | 五温度梯度退火筛选，使用 EQ-GB 手套箱与匀胶机。 | None | candidate_plans[0].summary | 版本 v1 |
| F067 | 4000 | None | candidate_plans[0].parameters.spin_coating_rpm | 候选 v1 宣称参数 |
| F068 | [80, 95, 110, 125, 140] | None | candidate_plans[0].parameters.anneal_temperature_C | 候选 v1 宣称参数 |
| F069 | [10] | None | candidate_plans[0].parameters.anneal_time_min | 候选 v1 宣称参数 |
| F070 | 手套箱 | None | candidate_plans[0].cost_items[0].item | 候选 v1 成本行 |
| F071 | 80 | CNY | candidate_plans[0].cost_items[0].unit_price | 候选 v1 成本行 |
| F072 | 40 | None | candidate_plans[0].cost_items[0].quantity | 候选 v1 成本行 |
| F073 | 3200 | CNY | candidate_plans[0].cost_items[0].subtotal | 候选 v1 成本行 |
| F074 | 匀胶机 | None | candidate_plans[0].cost_items[1].item | 候选 v1 成本行 |
| F075 | 20 | CNY | candidate_plans[0].cost_items[1].unit_price | 候选 v1 成本行 |
| F076 | 16 | None | candidate_plans[0].cost_items[1].quantity | 候选 v1 成本行 |
| F077 | 320 | CNY | candidate_plans[0].cost_items[1].subtotal | 候选 v1 成本行 |
| F078 | MAI | None | candidate_plans[0].cost_items[2].item | 候选 v1 成本行 |
| F079 | 250 | CNY | candidate_plans[0].cost_items[2].unit_price | 候选 v1 成本行 |
| F080 | 4 | None | candidate_plans[0].cost_items[2].quantity | 候选 v1 成本行 |
| F081 | 1000 | CNY | candidate_plans[0].cost_items[2].subtotal | 候选 v1 成本行 |
| F082 | PbI2 | None | candidate_plans[0].cost_items[3].item | 候选 v1 成本行 |
| F083 | 180 | CNY | candidate_plans[0].cost_items[3].unit_price | 候选 v1 成本行 |
| F084 | 5 | None | candidate_plans[0].cost_items[3].quantity | 候选 v1 成本行 |
| F085 | 900 | CNY | candidate_plans[0].cost_items[3].subtotal | 候选 v1 成本行 |
| F086 | DMF | None | candidate_plans[0].cost_items[4].item | 候选 v1 成本行 |
| F087 | 120 | CNY | candidate_plans[0].cost_items[4].unit_price | 候选 v1 成本行 |
| F088 | 2 | None | candidate_plans[0].cost_items[4].quantity | 候选 v1 成本行 |
| F089 | 240 | CNY | candidate_plans[0].cost_items[4].subtotal | 候选 v1 成本行 |
| F090 | 5760 | CNY | candidate_plans[0].total_cost | 候选 v1 宣称总价 |
| F091 | 26 | day | candidate_plans[0].est_days | 候选 v1 宣称周期 |
| F092 | 高速旋涂加电子传输层，使用 EQ-GB 与 EQ-HP。 | None | candidate_plans[1].summary | 版本 v2 |
| F093 | 5000 | None | candidate_plans[1].parameters.spin_coating_rpm | 候选 v2 宣称参数 |
| F094 | [100, 110, 120] | None | candidate_plans[1].parameters.anneal_temperature_C | 候选 v2 宣称参数 |
| F095 | [10, 20] | None | candidate_plans[1].parameters.anneal_time_min | 候选 v2 宣称参数 |
| F096 | 手套箱 | None | candidate_plans[1].cost_items[0].item | 候选 v2 成本行 |
| F097 | 80 | CNY | candidate_plans[1].cost_items[0].unit_price | 候选 v2 成本行 |
| F098 | 30 | None | candidate_plans[1].cost_items[0].quantity | 候选 v2 成本行 |
| F099 | 2400 | CNY | candidate_plans[1].cost_items[0].subtotal | 候选 v2 成本行 |
| F100 | 加热台 | None | candidate_plans[1].cost_items[1].item | 候选 v2 成本行 |
| F101 | 30 | CNY | candidate_plans[1].cost_items[1].unit_price | 候选 v2 成本行 |
| F102 | 20 | None | candidate_plans[1].cost_items[1].quantity | 候选 v2 成本行 |
| F103 | 600 | CNY | candidate_plans[1].cost_items[1].subtotal | 候选 v2 成本行 |
| F104 | PCBM | None | candidate_plans[1].cost_items[2].item | 候选 v2 成本行 |
| F105 | 400 | CNY | candidate_plans[1].cost_items[2].unit_price | 候选 v2 成本行 |
| F106 | 2 | None | candidate_plans[1].cost_items[2].quantity | 候选 v2 成本行 |
| F107 | 800 | CNY | candidate_plans[1].cost_items[2].subtotal | 候选 v2 成本行 |
| F108 | 3800 | CNY | candidate_plans[1].total_cost | 候选 v2 宣称总价 |
| F109 | 35 | day | candidate_plans[1].est_days | 候选 v2 宣称周期 |
| F110 | 围绕文献最优温度细扫，使用 EQ-GB、EQ-HP 与氮气吹扫。 | None | candidate_plans[2].summary | 版本 v3 |
| F111 | 3000 | None | candidate_plans[2].parameters.spin_coating_rpm | 候选 v3 宣称参数 |
| F112 | [105, 110, 115] | None | candidate_plans[2].parameters.anneal_temperature_C | 候选 v3 宣称参数 |
| F113 | [10] | None | candidate_plans[2].parameters.anneal_time_min | 候选 v3 宣称参数 |
| F114 | [1.0] | None | candidate_plans[2].parameters.n2_flow_rate_slm | 候选 v3 宣称参数 |
| F115 | 12 | None | candidate_plans[2].parameters.antisolvent_drip_s | 候选 v3 宣称参数 |
| F116 | 手套箱 | None | candidate_plans[2].cost_items[0].item | 候选 v3 成本行 |
| F117 | 80 | CNY | candidate_plans[2].cost_items[0].unit_price | 候选 v3 成本行 |
| F118 | 24 | None | candidate_plans[2].cost_items[0].quantity | 候选 v3 成本行 |
| F119 | 1920 | CNY | candidate_plans[2].cost_items[0].subtotal | 候选 v3 成本行 |
| F120 | 加热台 | None | candidate_plans[2].cost_items[1].item | 候选 v3 成本行 |
| F121 | 30 | CNY | candidate_plans[2].cost_items[1].unit_price | 候选 v3 成本行 |
| F122 | 12 | None | candidate_plans[2].cost_items[1].quantity | 候选 v3 成本行 |
| F123 | 360 | CNY | candidate_plans[2].cost_items[1].subtotal | 候选 v3 成本行 |
| F124 | MAI | None | candidate_plans[2].cost_items[2].item | 候选 v3 成本行 |
| F125 | 250 | CNY | candidate_plans[2].cost_items[2].unit_price | 候选 v3 成本行 |
| F126 | 2 | None | candidate_plans[2].cost_items[2].quantity | 候选 v3 成本行 |
| F127 | 500 | CNY | candidate_plans[2].cost_items[2].subtotal | 候选 v3 成本行 |
| F128 | PbI2 | None | candidate_plans[2].cost_items[3].item | 候选 v3 成本行 |
| F129 | 180 | CNY | candidate_plans[2].cost_items[3].unit_price | 候选 v3 成本行 |
| F130 | 2 | None | candidate_plans[2].cost_items[3].quantity | 候选 v3 成本行 |
| F131 | 360 | CNY | candidate_plans[2].cost_items[3].subtotal | 候选 v3 成本行 |
| F132 | DMF | None | candidate_plans[2].cost_items[4].item | 候选 v3 成本行 |
| F133 | 120 | CNY | candidate_plans[2].cost_items[4].unit_price | 候选 v3 成本行 |
| F134 | 1 | None | candidate_plans[2].cost_items[4].quantity | 候选 v3 成本行 |
| F135 | 120 | CNY | candidate_plans[2].cost_items[4].subtotal | 候选 v3 成本行 |
| F136 | 3260 | CNY | candidate_plans[2].total_cost | 候选 v3 宣称总价 |
| F137 | 21 | day | candidate_plans[2].est_days | 候选 v3 宣称周期 |

### literature（3 条）

| id | value | unit | jsonpath | note |
|---|---|---|---|---|
| F006 | mock_paper.pdf | None | source.paper_pdf |  |
| F007 | Mock, A. et al., J. Synth. Perov., 2024（合成引用，非真实文献） | None | source.citation |  |
| F008 | 110 C 退火 10 min 的 MAPbI3 薄膜获得 20.1% PCE（合成文献数据，仅作示例）。 | None | source.key_claim |  |

### text_embedded（6 条）

| id | value | unit | jsonpath | note |
|---|---|---|---|---|
| F060 | EQ-HP | None | equipment_domain_note~embedded[0].id | 文本内嵌补充 |
| F061 | 精密加热台 | None | equipment_domain_note~embedded[0].name | 文本内嵌补充 |
| F062 | MockHot-300 | None | equipment_domain_note~embedded[0].model | 文本内嵌补充 |
| F063 | 室温-300 C, +/-1 C | None | equipment_domain_note~embedded[0].spec | 文本内嵌补充 |
| F064 | 30 | CNY/h | equipment_domain_note~embedded[0].price_per_hour | 文本内嵌补充 |
| F065 | {"window_days": 30, "slots_per_week": 7, "slot_hours": 8} | None | equipment_domain_note~embedded[0].booking | 文本内嵌补充 |
