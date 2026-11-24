# 合成示例（SYNTHETIC — 合成示例，非正式案例数据）

一个小型"蛋白表达与纯化"课题，3 个方案版本（v1/v2/v3），用于端到端验证
资源到位与契约排期核验管线。case.json、task.md、requirements_v{1,2,3}.json
均为手工构造；`output/` 由 `run_example.sh` 实际运行产生。

## 运行

```bash
bash run_example.sh    # 任意 cwd 下均可，产物写入 output/
```

## 预埋缺陷与期望结果

| 版本 | 预埋缺陷 | 期望捕获 |
|---|---|---|
| v1 | 需求 20000rpm，库存离心机仅 15000rpm | match_v1: eq-01 → **不具备**，含 "需求=20000 库存=15000" 比较 |
| v1 | 纯化仪窗口 03-12~15 与既有预订 03-10~14 重叠 | booking_v1: **冲突**，overlap_days=2，overlap_hours=48 |
| v1 | 血清台账 -20°C vs 需求 -80°C | samples_v1: 存储 **不满足**（-20 > -80） |
| v1 | 血清 ethics_status=pending | samples_v1: **阻断性确认项**（不视为已批准） |
| v2 | Ni-NTA 货期：2026-02-01 下单 + 30 天 = 03-03 到货，晚于 needed_by 03-01 | booking_v2: **赶不上**，slack_days=-2 |
| v2 | Ni-NTA 双供应商报价 150/120 | match_v2: 需采购，按规则选单价最低的华科试剂 |
| v3 | 全部规避：14000rpm 达标、排期避开、货期留足、测序外协、换合规样本、qPCR仪 走别名表 | result.json: v3 = **有条件可行**（条件含采购下单日/货期、外协单位） |

最终结论（result.json 的 feasibility_by_version）：v1 不可行（不具备+预订冲突
+样本不满足+伦理待确认），v2 不可行（货期赶不上），v3 有条件可行。

## 负向测试（手动）

把 case.json 的 `inventory` 段删除后重跑 match_resources：所有无合同覆盖的
条目（如 高速冷冻离心机、LB培养基、IPTG）必须判为 **无法核验** 而非自动通过，
输出 notes 含"案例未提供库存清单"。
