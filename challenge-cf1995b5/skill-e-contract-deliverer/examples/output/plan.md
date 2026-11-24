> 合成示例输出，非正式测评结果

# 实验方案（人读渲染件）

- case_id: MOCK-PEROV-ANNEAL-001
- title: MAPbI3 钙钛矿薄膜退火工艺优化
- status: complete
- validation: PASS

## 1. 假设与变量

- 假设：MAPbI3 结晶质量对退火温度敏感区间在 100-120°C（source.key_claim，合成示例论断）
- 自变量：anneal_temperature_C（域内 100/110/120）；因变量：薄膜覆盖率、PL 强度
- 控制变量：spin_coating_rpm=4000、anneal_time_min=10 固定

## 2. 对照组

- 未退火对照（同批旋涂后直接表征）
- candidate v1 的 125°C 单点作为域内参照

## 3. 设备与材料

- id: EQ-GB，name: 充氮手套箱，source: resource_contract.equipment[0]
- id: EQ-HP，name: 精密加热台，source: equipment_domain_note（内嵌，可用性待确认）
- id: RE-MAI，name: MAI ≥99.99%，source: resource_contract.reagents[0]
- id: RE-PBI2，name: PbI2 ≥99.99%，source: resource_contract.reagents[1]

## 4. 时间与成本

- **est_days**: 14
- **basis**: 6 次实验 × 4h/次；手套箱 3 档/周 → 2 周，window_days=30 内可行

| 项目 | 单价 | 数量 | 小计 |
| --- | ---: | ---: | ---: |
| 手套箱 | 80 | 24 | 1920 |
| 加热台 | 40 | 12 | 480 |
| MAI | 250 | 5 | 1250 |
| PbI2 | 180 | 5 | 900 |
| **合计** | | | **4550** |

## 5. 参数范围

- **anneal_temperature_C**:
  - 100
  - 110
  - 120
- **spin_coating_rpm**: 4000
- **anneal_time_min**: 10

## 6. 风险与异常

- 手套箱预约冲突 → 提前 7 天锁档，冲突时顺延并在 change_log 记录
- EQ-HP 为内嵌设备、可用性未确认 → 已列入 confirmation_items，确认前不排产
- 湿气侵入 → 手套箱水氧 <1ppm 监控，超阈中止当次实验

## 校验摘要

- overall: **PASS**（status_after_validate=complete）

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| required_fields | PASS | 全部 9 个 required 字段存在且非占位 |
| case_id_match | PASS | result.case_id='MOCK-PEROV-ANNEAL-001' 与 case.json 一致 |
| fields_final | PASS | 全部 required 字段 fields_status=final |
| status_consistency | PASS | status=partial 与 fields_status 自洽 |
| cost_arithmetic | PASS | cost_items 与 total_cost 算术可重算（4 项） |
| parameter_domains | PASS | 全部参数落在 parameter_domains 内 |

## 确认项清单（confirmation_items）

- [ ] EQ-HP 精密加热台（equipment_domain_note 内嵌设备）是否在合同内可用？确认前不排产
- [ ] resource_contract 全部价格与预约信息为组织方前瞻约定，需委托方书面确认后方可作为执行依据
- [ ] MAI/PbI2 各 1 包（5g）是否覆盖 6 次实验用量？不足需追加采购（预算内）
