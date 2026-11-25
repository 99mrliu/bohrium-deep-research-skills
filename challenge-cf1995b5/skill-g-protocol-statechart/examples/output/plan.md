# 合成水样比色硝酸盐测定：有限域优化与有界 QC 重试

> 合成示例输出，非正式测评结果。所有情景均为可执行流程的假设推演，未开展实测实验；成本/期为前瞻性规划值，不是报价、预约或批准。

- Case: `synthetic-nitrate-statechart-001`
- Protocol: `SYN-NO3-COLOR-STATECHART-01`
- Schema: `1.0`

## 可证伪假设

- **H1**：在本合成方案中，选择 30 degC、20 min 的规划组合可在有效校准空白之后进入样品测定；该句仅描述可检验计划，不断言现实方法性能。 **证伪条件**：若现实经批准实验在空白有效后仍不满足预先登记的样品 QC 验收标准，则拒绝此规划组合的适用性假设并修订方案。
- **H2**：一次重新空白可能使合成高空白故障恢复到空白 QC 通过分支。 **证伪条件**：若重新空白后的受控实测仍不满足空白回收率守卫，则 H2 被该次故障处置路径证伪，流程必须进入 QC_FAIL，不得继续消耗样品。

## 变量、参数与控制

### 变量

```json
{
  "independent": [
    {
      "name": "reaction_temperature",
      "unit": "degC",
      "domain": "20..40 step 5"
    },
    {
      "name": "reaction_time",
      "unit": "min",
      "domain": "10..30 step 10"
    }
  ],
  "dependent": [
    {
      "name": "calibration_blank_recovery_percent",
      "unit": "%",
      "record": "run_log.blank_qc.recovery_percent"
    },
    {
      "name": "sample_response",
      "unit": "instrument_defined",
      "record": "run_log.sample.response"
    }
  ],
  "controlled": [
    "sample_matrix=synthetic_freshwater",
    "reagent lot and actual expiry to be recorded before execution",
    "calibration sequence and pipette SOP to be confirmed by method owner"
  ]
}
```

### 有限域内选定参数

| 参数 | 值 |
|---|---|
| reaction_temperature | 30 |
| reaction_time | 20 |
| sample_matrix | synthetic_freshwater |

### 控制

- {"id": "CTRL_BLANK", "procedure_states": ["S20_PREPARE_BLANK", "S30_MEASURE_BLANK", "D30_BLANK_QC"], "purpose": "在消耗样品前隔离高空白/背景故障", "type": "calibration_blank", "unmeasured": true}
- {"id": "CTRL_CALIBRATION", "procedure_states": ["S40_PREPARE_CALIBRATION"], "purpose": "建立并记录合成规划中的校准系列；现实点数以批准 SOP 为准", "type": "calibration_series", "unmeasured": true}
- {"id": "CTRL_FAIL_SAFE", "procedure_states": ["T_QC_FAIL"], "purpose": "持续 QC 故障时阻止样品反应并终止", "type": "negative_process_control", "unmeasured": true}

## 材料与设备（规划绑定）

| 类型 | ID | 名称 | 数量/规格 |
|---|---|---|---|
| 设备 | EQ_BALANCE | 合成分析天平 | 实际量程/校准状态待确认 |
| 设备 | EQ_PIPETTE | 合成移液设备 | 实际规格与 SOP 待确认 |
| 设备 | EQ_THERMOSTAT | 合成恒温反应设备 | 30 degC 设定仅用于合成案例 |
| 设备 | EQ_COLORIMETER | 合成比色检测器 | 波长等现实方法参数未提供，不得补造 |
| 材料 | MAT_REAGENT | 合成硝酸盐显色试剂 | 1 planning_lot；成本 11.00 |
| 材料 | MAT_WATER | 合成无硝酸盐水 | 2 blank_preparation；成本 1.00 |
| 材料 | MAT_STANDARD | 合成硝酸盐校准标准液 | 1 planning_series；成本 4.50 |
| 材料 | MAT_SAMPLE | 合成淡水样 | 1 synthetic_aliquot；成本 0 |

## 状态化操作程序与 QC 守卫

| 状态 | 类型 | 时长 min | 成本 | 最大访问 | 后继/分支 |
|---|---|---:|---:|---:|---|
| S00_START | start | 0 | 0 | 1 | S10_PREPARE_REAGENTS |
| S10_PREPARE_REAGENTS | action | 10 | 5.00 | 1 | S20_PREPARE_BLANK |
| S20_PREPARE_BLANK | action | 5 | 0.50 | 1 | S30_MEASURE_BLANK |
| S30_MEASURE_BLANK | action | 3 | 0.20 | 2 | D30_BLANK_QC |
| D30_BLANK_QC | decision | 0 | 0 | 2 | high_blank→S35_REBLANK; retries_exhausted→T_QC_FAIL; else→S40_PREPARE_CALIBRATION |
| S35_REBLANK | action | 5 | 0.50 | 1 | S30_MEASURE_BLANK |
| S40_PREPARE_CALIBRATION | action | 15 | 4.50 | 1 | S50_REACT_SAMPLES |
| S50_REACT_SAMPLES | action | 20 | 6.00 | 1 | S60_MEASURE_SAMPLES |
| S60_MEASURE_SAMPLES | action | 5 | 0.20 | 1 | T_SUCCESS |
| T_SUCCESS | terminal | 0 | 0 | 1 | terminal:success |
| T_QC_FAIL | terminal | 0 | 0 | 1 | terminal:failure |

### 决策观测记录

- `D30_BLANK_QC/high_blank`：`calibration_blank_recovery_percent > 105 %`，记录于 `run_log.blank_qc.recovery_percent`；缺省分支为 `S40_PREPARE_CALIBRATION`。
- `D30_BLANK_QC/retries_exhausted`：`reblank_attempt_count >= 1 count`，记录于 `run_log.blank_qc.reblank_attempt_count`；缺省分支为 `S40_PREPARE_CALIBRATION`。

## 验收标准

- {"id": "AC_BLANK_RECOVERY", "meaning": "合成规划阈值；不是从现实标准或实验数据取得的性能限值", "metric": "calibration_blank_recovery_percent", "operator": "<=", "record": "run_log.blank_qc.recovery_percent", "threshold": "105", "unit": "%"}
- {"id": "AC_SAMPLE_RECORD", "meaning": "实际执行时的记录要求；本例没有注入样品测量结果，也不声称通过", "metric": "sample_response_within_approved_calibration_range", "operator": "==", "record": "run_log.sample.within_calibration_range", "threshold": "true", "unit": "boolean"}

## 候选方案审计

- `C1_ARITHMETIC_ERROR`：rejected_or_requires_revision；Cost item measurement: declared subtotal 1.8 != recomputed 1.9.；Cost arithmetic mismatch: total_cost=15, recomputed 16.4.
- `C2_DOMAIN_ERROR`：rejected_or_requires_revision；Parameter reaction_temperature: 33 is off the Decimal step grid 5 from 20.
- `C3_DOMAIN_AND_BUDGET_ERRORS`：rejected_or_requires_revision；Cost arithmetic mismatch: total_cost=80, recomputed 90.；Parameter reaction_temperature: 45 outside [20, 40].；Parameter reaction_time: 35 outside [10, 30].；Parameter reaction_time: 35 is off the Decimal step grid 10 from 10.；Recomputed cost 90 exceeds budget_cap 80 CNY.；Candidate est_days 2 exceeds deadline_days 1.

## 路径成本与时间包络（非实测）

- Nominal：58 min，成本 16.4。
- 已给情景逐分量最大值：66 min，成本 17.1。
- 有界图保守上界：66 min，成本 17.1。
- 解释：Conservative sum over every reachable state of max_visits times exact state cost/duration; may include mutually exclusive terminals, so it is a safe upper bound, not a claimed attainable path.

## 风险与修订

- {"detection": "D30_BLANK_QC 的 recovery_percent 与 reblank_attempt_count 记录", "residual_uncertainty": "未实测故障原因和恢复概率", "revision": "允许一次 S35_REBLANK；持续故障进入 T_QC_FAIL，禁止绕过 QC", "risk": "高空白或背景异常"}
- {"detection": "bootstrap 与 compile 的 Decimal min/max/step 审计", "residual_uncertainty": "有限域本身是合成输入，并非现实方法推荐", "revision": "拒绝候选并从 case 声明网格重选；不得用四舍五入掩盖越域", "risk": "温度/时间候选越出有限域"}
- {"detection": "执行前资源负责人核对", "residual_uncertainty": "未确认实际库存、校准状态和价格", "revision": "暂停执行并重新规划；当前状态成本/时长不是报价、预约或批准", "risk": "试剂、仪器或人员资源与现实不符"}

## 规划证据与限制

以下仅为方案内证据/假设登记，不构成外部科学结论或实测结果：

- {"citation": "examples/mock_case.json and examples/materials/assay_notes.txt", "claim": "30 degC、20 min 和 105% 仅用于演示有限域与守卫执行", "evidence_id": "PE1", "measured": false, "source_type": "synthetic_planning_assumption"}
- {"citation": "examples/protocol_spec.json scenarios", "claim": "nominal、recoverable_high_blank、persistent_qc_failure 的决策序列全部是注入的 what-if 标签", "evidence_id": "PE2", "measured": false, "source_type": "synthetic_fault_injection"}

## 专家确认边界

实际执行前必须由方法负责人确认仪器 SOP、试剂适用性、校准/QC 标准、安全处置、真实资源价格与可用性。状态图编译和仿真通过不等于科学有效性、安全性或实验成功。
