# 回归判定阈值

回归检测回答一个问题：**同一真值基准下，本次运行相比基线运行是否变差？**
实现见 `scripts/regression.py`；基线取 `run_history.json` 中最后一个 run。

## 1. 默认阈值（绝对百分点）

| 标记 | 触发条件 | 默认阈值 |
| --- | --- | --- |
| `recall_regression` | recall 下降 | > 0.05 |
| `false_alert_regression` | false_alert_rate 上升 | > 0.05 |
| `duplicate_regression` | duplicate_rate 上升 | > 0.02 |
| `new_false_negatives` | 本次 FN 集合 − 基线 FN 集合 非空 | 逐条列出 canonical_key |
| `new_false_positives` | 本次 FP 集合 − 基线 FP 集合 非空 | 逐条列出 canonical_key |

同时报告改善面：`resolved_fn_keys` / `resolved_fp_keys`（基线漏/误报而本次已修复）。

## 2. 阈值依据

- 使用**绝对百分点差**而非相对变化：小样本（真值仅个位数）下相对变化极不稳定，
  例如 recall 从 1/2 到 1/3 是 −33% 相对但只差一条文献。
- recall / false_alert_rate 阈值 0.05：在真值规模 ≥20 时约等于 1 条文献的波动，
  小于此视为噪声；真值规模更小时，应主要依据 `new_false_negatives` 的逐条清单
  做人工判定，而非仅看比率。
- duplicate_rate 阈值 0.02：重复声明是纯噪声（不含任何新信息），容忍度更低。
- 三个阈值均可用命令行参数 `--recall-drop / --far-increase / --dup-increase` 覆盖；
  调整时必须把所用阈值写入 regression.json 的 `thresholds` 字段（实现已默认如此），
  保证判定可回放。

## 3. 判定流程

1. 仅当两次运行使用**同一真值基准**（同一快照对与窗口）时，回归对比才有意义；
   若基线是在不同窗口/快照上算的，必须在报告中显式声明，不得直接比较。
2. 计算各指标 delta（本次 − 基线）；
3. 逐条比对 FN/FP 的 canonical_key 集合，给出新增与消除的漏报/误报；
4. 汇总 flags；任一 flag 触发即 verdict = `REGRESSION`，否则 `NO_REGRESSION`；
5. 无历史记录时输出 status = `no_history`——这不是失败，如实报告"无基线可比"。

## 4. 合成示例中的预期

基线 run1：recall=0.75, false_alert_rate=0.25, duplicate_rate=0.0；
本次 run2：recall=0.50, false_alert_rate≈0.3333, duplicate_rate=0.25。

预期触发：`recall_regression`（−0.25）、`false_alert_regression`（+0.0833）、
`duplicate_regression`（+0.25）、`new_false_negatives`（doi:10.1000/syn.203）。
