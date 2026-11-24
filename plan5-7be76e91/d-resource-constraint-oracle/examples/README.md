# examples — 合成示例 / SYNTHETIC EXAMPLE

本目录全部输入与输出均为**合成示例（SYNTHETIC EXAMPLE）**：虚构契约、虚构方案、虚构数字，
仅演示用法与裁决逻辑，不得冒充正式案例结果或真实实验室/供应商数据。

## 文件

| 文件 | 内容 |
| --- | --- |
| `case.example.json` | 合成 case：基准日 2026-01-05，deadline 2026-03-31，预算 20000 元，契约参数域 |
| `contract.example.json` | 虚构契约：设备档期表、耗材货期表、参数域、审批、人员（模型抽取 facts 的原始材料） |
| `facts.example.json` | 正例 facts（模型抽取产物样例）：P1 全满足、P2 档期冲突、P3 参数空交集负例 |
| `facts_all_infeasible.json` | 负例变体：Q1 设备档期全占、Q2 耗材货期超 deadline、Q3 参数空交集 → 全部 infeasible |
| `outputs/` | 下述命令真实跑出的产物（含 `all_infeasible/` 子目录与示例 result.json） |

## 命令序列（在本目录下执行）

```bash
NOTE="合成示例 / SYNTHETIC EXAMPLE：本报告由虚构输入生成，仅演示接口与裁决逻辑，非正式案例结果或真实实验室/供应商数据。"

# 1) 约束满足裁决（正例 → exit 0）
python3 ../scripts/constraints.py --facts facts.example.json --case case.example.json \
  --out-dir outputs --note "$NOTE"

# 2) 参数窗口三方对照（P3 空交集 → exit 3，报告仍写出）
python3 ../scripts/window_check.py --facts facts.example.json --case case.example.json \
  --out-dir outputs --note "$NOTE"

# 3) 最早可启动排期（P3 依 constraints 报告跳过 → exit 0）
python3 ../scripts/timeline.py --facts facts.example.json --case case.example.json \
  --constraints outputs/constraints_report.json --out-dir outputs --note "$NOTE"

# 4) 全部不可行变体（→ exit 3 + relax_hints；timeline 无可排 → exit 3）
python3 ../scripts/constraints.py --facts facts_all_infeasible.json --case case.example.json \
  --out-dir outputs/all_infeasible --note "$NOTE"
python3 ../scripts/timeline.py --facts facts_all_infeasible.json --case case.example.json \
  --constraints outputs/all_infeasible/constraints_report.json \
  --out-dir outputs/all_infeasible --note "$NOTE"

# 5) 自查（正/负例精确命中 + 双跑字节一致 → exit 0）
python3 ../scripts/selfcheck.py
```

## 期望裁决与手算验算

日期约定：**半开区间 [start, end)**。基准日 2026-01-05；deadline 2026-03-31。

### P1 → feasible_now（exit 0）

- 耗材 MAT-AL2O3 现货；审批 APPR-HT / APPR-XRD 均 granted → start_bound = 2026-01-05 = 基准日。
- 参数窗口：temperature_C 要求 [850,1000] ⊆ 设备 [20,1150] ∩ 契约域 [600,1050] = [600,1050] ✓；
  hold_time_h [20,30] ⊆ [0.5,72] ∩ [1,48] = [1,48] ✓；xrd_2theta_deg [10,80] ⊆ [5,90] ∩ [10,80] ✓。
- 时间线：ready 01-05 → 准备 1 天 → FURNACE-01 执行 01-06~01-09（维保 02-02 起不冲突）
  → XRD-01 表征 01-09~01-10（校准 01-12 起不冲突）→ earliest_finish **2026-01-10**，未超期。

### P2 → feasible_after(2026-01-31)（手算验算）

1. 耗材：MAT-LATP 无现货，货期 10 天 → 到货 2026-01-05 + 10 天 = **2026-01-15**（≤ needed_by 2026-02-01 ✓）。
2. 准备：prep_days=2 → 2026-01-15 + 2 天 = 2026-01-17 起可执行。
3. 设备：PRESS-01 档期占用 [2026-01-05, 2026-01-31)（即 1 月 5 日至 1 月 30 日含），
   需求窗口 [2026-01-05, 2026-03-15) 内首个 ≥5 天空档起点 = **2026-01-31**。
4. start_bound = max(基准日 01-05, 到货 01-15, 设备空档 01-31) = **2026-01-31** > 基准日
   → verdict = feasible_after(**2026-01-31**)。
5. 时间线：准备 01-15~01-17 → 执行顺延至 01-31~02-05（5 天）→ XRD 表征 02-05~02-06
   → earliest_start=**2026-01-15**，first_execution_start=**2026-01-31**，
   earliest_finish=**2026-02-06**，past_deadline=false（02-06 ≤ 03-31）。
   关键等待项：MAT-LATP 到货 01-15；PRESS-01 档期顺延至 01-31。

### P3 → infeasible（参数窗口空交集负例，被精确捕获）

- temperature_C 要求 [1100,1200]；允许区间 = 设备极限 [20,1150] ∩ 契约域 [600,1050] = [600,1050]；
  [1100,1200] ∩ [600,1050] = **∅** → blocking `parameter_window_conflict`。
- `window_check.py` 因此 exit 3，空交集精确为 P3/temperature_C（典型的"照搬文献超高温流程、
  未核对契约域上限 1050°C"失败）。

### all_infeasible 变体 → exit 3 + relax_hints

- Q1：PRESS-01 档期改为 [2026-01-05, 2026-03-31) 全占 → `equipment_booking_conflict`。
- Q2：MAT-AU 货期 120 天 → 2026-05-05 到货，晚于 needed_by 2026-02-01（也超 deadline 2026-03-31）
  → `consumable_lead_time_exceeded`。
- Q3：同 P3 空交集 → `parameter_window_conflict`。
- 三方案全部 infeasible → constraints exit 3，relax_hints 逐条给出解除条件；
  timeline 全部跳过 → exit 3。
