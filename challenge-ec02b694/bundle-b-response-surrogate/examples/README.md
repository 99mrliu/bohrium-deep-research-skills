# examples — 合成示例（synthetic example）

**本目录全部数据为人工合成**，仅用于演示与回归测试技能流水线，不对应任何真实实验。
`history.csv` 由 `conversion = 20 + 0.9·T + 2·t − 0.006·T² − 0.15·t² + 0.02·T·t`
加上 ±1.5 个百分点内的手工小噪声生成（T=温度 degC，t=时间 h）。

## 输入（synthetic-input/）

| 文件 | 说明 |
|---|---|
| `case.json` | 合成案例：case_id、三字段 output_contract（experiment_plan / evidence_and_risk / confirmation_items）、材料路径、因子与响应指标规格 |
| `history.csv` | 12 组实验：temp_C × time_h → conversion_pct（%） |
| `small_history.csv` | n=4 的小样本，用于触发"拒绝拟合 + 降级路径"负例 |

## 输出（synthetic-output/，全部为脚本真实运行产物）

| 文件 | 对应步骤 | 关键结果 |
|---|---|---|
| `metric_registry.json` | (a) 指标注册 | status=ok，1 个指标（conversion_pct，%，maximize，波动限 1.5 pp） |
| `surrogate.json` | (b) 二次 RSM 拟合 | mode=rsm(quadratic)，n=12，R²≈0.977，LOO-CV RMSE≈1.49，有效域 temp∈[50,90], time∈[4,12] |
| `prediction_in_domain.json` | (c) 域内预测 | (70 °C, 8 h) → ≈70.8 %，extrapolation=false，带 95% 预测区间 |
| `extrapolation_flagged.json` | (d) 域外负例 | (110 °C, 16 h) → extrapolation=true，区间显式放大，附"该预测为待确认假设，不得作为可执行事实" |
| `small_surrogate.json` | (e) n=4 拟合 | 拒绝拟合：quadratic 需 n≥8、linear 需 n≥5，mode=fallback |
| `small_sample_fallback.json` | (e) 降级预测 | 最近邻/均值估计 + 放大区间 + 强制 extrapolation 级警告 |

## 复现命令

在 bundle 根目录执行：

```bash
# (a) 指标注册
python3 scripts/metric_registry.py \
    --case examples/synthetic-input/case.json \
    --csv examples/synthetic-input/history.csv \
    --out examples/synthetic-output/metric_registry.json

# (b) 二次 RSM 拟合（检查 R² 与 LOO-CV RMSE 是否合理）
python3 scripts/fit_surrogate.py \
    --csv examples/synthetic-input/history.csv \
    --factors temp_C,time_h --response conversion_pct \
    --model quadratic \
    --out examples/synthetic-output/surrogate.json

# (c) 域内点预测
python3 scripts/predict.py \
    --surrogate examples/synthetic-output/surrogate.json \
    --point '{"temp_C": 70, "time_h": 8}' \
    --out examples/synthetic-output/prediction_in_domain.json

# (d) 域外点预测（负例：触发 extrapolation 警告，退出码 1）
python3 scripts/predict.py \
    --surrogate examples/synthetic-output/surrogate.json \
    --point '{"temp_C": 110, "time_h": 16}' \
    --out examples/synthetic-output/extrapolation_flagged.json

# (e) n=4 小样本：拒绝拟合 + 降级路径（退出码均为 1）
python3 scripts/fit_surrogate.py \
    --csv examples/synthetic-input/small_history.csv \
    --factors temp_C,time_h --response conversion_pct \
    --model auto \
    --out examples/synthetic-output/small_surrogate.json
python3 scripts/predict.py \
    --surrogate examples/synthetic-output/small_surrogate.json \
    --point '{"temp_C": 70, "time_h": 8}' \
    --out examples/synthetic-output/small_sample_fallback.json
```

退出码约定：`0` 正常；`1` 降级/外推（产物有效但须如实上报）；`2` 输入级错误。
