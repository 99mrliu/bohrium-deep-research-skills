# 合成示例（SYNTHETIC）— 合成示例，非正式案例数据

本目录是一个**完全虚构**的端到端示例，用于演示与回归测试本 Skill 的实算流水线。
所有价格、合同、参数均为编造，不对应任何真实案例。

## 场景

细胞培养 + ELISA 检测课题，3 个版本化候选方案，预算上限 10000.00 CNY，
细胞房预约窗口 96 小时，4 个有限参数域（含枚举域与区间域）。

## 植入缺陷（planted defects）一览

| # | 位置 | 植入内容 | 期望脚本判定 |
|---|---|---|---|
| 1 | v1 预算 胎牛血清 行2 | `stated_subtotal: 1650.00`，但 800.00×2 = 1600.00（漂移 3.125%） | recalc_budget 标记 unverified，合计按 1600.00 计 |
| 2 | v2 预算 | 合计 11760.00 CNY > 上限 10000.00 | **超支 1760.00 CNY**（gating fail） |
| 3 | v2 参数 | 培养温度 37.5 °C，枚举域 [35, 36, 37] | **out_of_domain**（gating fail） |
| 4 | v3 进度 | 关键路径 S1→S2→S3→S4→S5→S6 = 118 h > 96 h | **超出 22 h**（gating fail） |
| 5 | v3 参数 离心转速 | 300 g vs 域 2000–5000 rpm | unit_unconvertible（rpm↔g 不自动换算，请专家复核） |
| 6 | v3 参数 摇床转速 | 域表中无此参数 | no_domain_found（如实报告，不静默放过） |
| 7 | v1 参数 培养时间/单孔加样量 | 2880 min、100 µL | 单位归一化后 in_domain（48 h ∈ [24,72]；0.1 mL ∈ [0.05,0.2]） |
| 8 | v3 预算 胎牛血清 行2 | `stated_subtotal: 1600.00` 与复算一致 | 不标记（对照组） |

期望总体结论：PLAN-V1 无 gating fail（仅有 1 条 unverified 申报漂移）→ chosen_plan_id = PLAN-V1；
V2（超支+越域）、V3（超期）gating fail。

## 运行

```bash
bash run_example.sh
```

产物写入 `output/`：`inspect_map.json`、每版 `budget_v{N}.md/.json`、`schedule_v{N}.md/.json`、
`domains_v{N}.md/.json`，以及最终 `result.json`。`.md` 报告含逐行公式与关键路径链，
任何人重跑脚本可得到完全相同的数字。

## 负向测试（手工）

把任一 extraction 的依赖改成环（如 S1 的 depends_on 改为 ["S6"]），
`recalc_schedule.py` 应 exit 2 并列出成环节点；改回后恢复正常。
