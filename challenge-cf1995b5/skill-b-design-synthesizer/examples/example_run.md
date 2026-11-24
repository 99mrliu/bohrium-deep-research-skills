# 合成示例说明（exp-design-synthesizer）

**合成示例输出，非正式测评结果。** 本目录演示 bundle B 的完整链路：
`mock_case.json` 是虚构的钙钛矿退火工艺优化案例（note 字段已标明"合成示意案例"），
`output/` 下的全部文件由 `run_example.sh` 真实运行生成。

## 如何复跑

```bash
bash examples/run_example.sh
```

脚本依次执行：
1. `enumerate`：展开 3 个参数域（退火温度 80–150°C step 5 × 转速 4 档 ×
   退火时间 10–60 min step 10）→ `design_space.json`（360 个合法组合）；
   再用 `--levels 3` 生成缩减网格 `design_space_3lvl.json`（27 组合）；
2. `score`：对 case 里的 3 个候选方案 + `strategies.json` 的 4 个新策略
   共 7 个设计逐点核算 → `design_table.json`；
3. `select`：在 feasible 设计中按 可行性→信息度→成本 排序 → `selection.json`。

## 输出如何解读（真实运行结果）

### 候选方案量化体检（score 的算术结论）

| 设计 | 条件×重复 | 核算成本 (CNY) | est_days | 结论 |
|---|---|---|---|---|
| candidate_v1 | 5×3=15 | 7270 | 14 | feasible；但自报 2030 与核算不符（warning：差 5240，候选把 MAI/PbI2 的"包"按单价计了一次） |
| **candidate_v2** | 96×5=480 | **145350** | **336** | **REJECTED**：核算成本超预算 20000；关键设备 EQ-HP 需 480h/每周 10h = 48 周 → 336 天，超截止 30 天；且自报 total_cost 9500 与 cost_items 合计 8900 不符 |
| candidate_v3 | 4×2=8 | 3730 | 7 | feasible；自报 1110 与核算不符（同 v1 的计价错误）；只扫转速一个因子，信息度低 |

v2 的 9500 CNY / 25 天是肉眼看似合理的数字，只有逐点核算才暴露它
实际需要 480 个样品 × 1h 加热台机时。注意 EQ-HP 不在
`resource_contract.equipment` 列表里，而是内嵌在 `equipment_domain_note`
文本中——脚本的 `equipment_register` 显示其来源为
"equipment_domain_note(内嵌解析)"，若漏算它，工期核算会整体失真。

### 新策略与 select 结论

| 策略 | 类型 | 样品数 | 成本 | est_days | info_score | 结论 |
|---|---|---|---|---|---|---|
| S1 | 3 水平全因子, r=1 | 27 | 9360 | 21 | 304 | REJECTED：replicates=1 < 2，无法估计实验误差 |
| S2 | 循环正交主效应, r=4 | 12 | 4010 | 14 | 51 | feasible（便宜但估不了交互） |
| **S3** | 温度×转速 3×3 部分因子, r=2 | 18 | 7480 | 14 | **111** | **推荐**：唯一保留关键交互网格且全部可行的设计 |
| S4 | OFAT 链式扫描, r=3 | 21 | 7690 | 21 | 106 | 备选 1（条件多但无共变因子对） |

select 的实际结论：**推荐 strategy_S3_fractional_temp_x_rpm_r2**
（info=111, cost=7480, est_days=14），备选 S4 与 candidate_v1；
否决 v2（超预算+超工期+自报数三处不一致）与 S1（重复不足）。
否决表 `rejected` 带完整理由，可直接抄进 result.json 的
candidate_assessment。

## 成本核算口径（可用 design_table.json 的 cost_breakdown 手工重算）

- 试剂按 pack_size 向上取整：v1 需 MAI 6.0 g → 买 2 包 × 5 g × 250 = 2500
  （候选 v1 自报只算了 2×250=500，这是它被标记 warning 的原因）；
- 设备并行预约：est_days = max(各设备周数)×7，本例关键设备均为 EQ-HP；
- 全部算术为 int/Decimal，重算不会遇到浮点尾差。
