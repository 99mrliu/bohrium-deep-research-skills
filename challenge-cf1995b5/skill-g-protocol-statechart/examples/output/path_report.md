# 路径仿真与覆盖报告

> 合成示例输出，非正式测评结果；以下均为 `synthetic_what_if`，不是实测结局。

| 情景 | 路径 | 终止 | 访问数 | 时长 min | 成本 |
|---|---|---|---:|---:|---:|
| nominal | S00_START → S10_PREPARE_REAGENTS → S20_PREPARE_BLANK → S30_MEASURE_BLANK → D30_BLANK_QC → S40_PREPARE_CALIBRATION → S50_REACT_SAMPLES → S60_MEASURE_SAMPLES → T_SUCCESS | T_SUCCESS | 9 | 58 | 16.4 |
| recoverable_high_blank | S00_START → S10_PREPARE_REAGENTS → S20_PREPARE_BLANK → S30_MEASURE_BLANK → D30_BLANK_QC → S35_REBLANK → S30_MEASURE_BLANK → D30_BLANK_QC → S40_PREPARE_CALIBRATION → S50_REACT_SAMPLES → S60_MEASURE_SAMPLES → T_SUCCESS | T_SUCCESS | 12 | 66 | 17.1 |
| persistent_qc_failure | S00_START → S10_PREPARE_REAGENTS → S20_PREPARE_BLANK → S30_MEASURE_BLANK → D30_BLANK_QC → S35_REBLANK → S30_MEASURE_BLANK → D30_BLANK_QC → T_QC_FAIL | T_QC_FAIL | 9 | 26 | 6.4 |

## 已覆盖判分支

- `D30_BLANK_QC/else`（仅为注入路径覆盖）
- `D30_BLANK_QC/high_blank`（仅为注入路径覆盖）
- `D30_BLANK_QC/retries_exhausted`（仅为注入路径覆盖）

## 未覆盖判分支

- 无（仅限已声明的决策分支；不表示科学或实测覆盖）。

## 有界性

Conservative sum over every reachable state of max_visits times exact state cost/duration; may include mutually exclusive terminals, so it is a safe upper bound, not a claimed attainable path.
全局步数上限：`13` 为按状态访问界之和；仿真另有规格中的 global_step_cap 硬停止。越界会成为 detected_failure，不会被静默忽略。
