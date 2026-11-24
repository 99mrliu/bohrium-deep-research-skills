---
name: premise-first-stats
description: 统计推断严谨取向的多步骤数据分析规程。premise_stats.py 把每个组间比较当作一次裁决：先前提（各组 Shapiro 正态性 + Levene 方差齐性）后检验（参数/非参决策树），强制效应量、两两比较 Bonferroni 与特征族多重比较口径，输出区分度排序；回归模式给 Spearman 相关 + 标准化 OLS（VIF、残差诊断）并强制"相关≠因果"声明。适用于要求"检验前提先行、方法选择有据、区分度排序"的科研表格案例（如 Iris/Wine 组间差异、Concrete 强度影响因素）。
---

# Premise-First Stats —— 没有通过前提的检验结果不予交付

核心主张：**统计结论失真的首要原因是方法选错——前提没验就上参数检验。**
本 Skill 的重心是推断层的裁决质量：每个检验记录前提、方法、依据、效应量与
多重比较口径。导入/清洗/绘图/报告按通用要求完成，但 statistics.json 只能由
`premise_stats.py` 产出（或在 scipy 不可用时如实标注），报告中的统计表述必须与
之一字不差地对应。

## 运行契约（评测环境）

- 输入 `/input/case.json`（`case_id`、`output_contract.fields`）、`/input/task.md`。
- 工作于 `/app/work`，交付入 `/app/output`；`result.json` 含原样 `case_id` + 全部
  契约字段 + `status`/`sources`/`uncertainty`；先 partial 后增强。
- 预算约 8–12 次请求。

## 流程

**0. 读题 + 保底 partial。** 记录契约字段与任务专项（组间差异？连续目标？区分度
排序？）。立即写 partial result.json（case_id + 空契约字段 + status=partial）。

**1. 导入与清洗（通用要求，简短执行）。** pandas 读 CSV/SQLite；双源案例逐列核对
一致性（一致→声明并任选其一，建议 CSV；不一致→写 uncertainty 并说明主源选择）。
清洗口径：完全重复行删（保留首条）并记数；缺失 ≤5% 中位数/众数填补、>5% 保留并
声明；异常值 1.5×IQR 只标记不删除。行数变化记入 `/app/work/cleaning_log.json`，
cleaned 表存 `/app/output/cleaned_data.csv`。

**2. 统计裁决（本重心）。**

组间差异案例（task.md 提到分组/class/种/类别差异）：

```
python3 /skills/weekly-skill/scripts/premise_stats.py group \
    --table /app/output/cleaned_data.csv --group <分组列> --out /app/output
```

- 决策树与口径见 `references/test_selection_tree.md`；引擎输出
  `statistics_group.json`，含每特征的前提 p、所选方法、p、效应量、
  特征族 Bonferroni α 与 `discrimination_ranking`。
- 任务要求"区分度最强指标"时，直接引用 `discrimination_ranking` 的 Top-N，
  并注明其方法路径（参数 η² 或非参 ε² 不可混排比较绝对值，报告需说明）。

连续目标案例（task.md 提到"影响因素"/强度/回归）：

```
python3 /skills/weekly-skill/scripts/premise_stats.py regress \
    --table /app/output/cleaned_data.csv --target <目标列> --out /app/output
```

- 解读顺序：Spearman 相关 → 标准化 β（结合 VIF）→ R²/残差诊断；VIF>10 的变量
  不得解释为独立贡献。强制写入"相关≠因果"声明。

把对应 JSON 复制/引用为 result.json 的 `statistics` 字段（两模式都跑了就合并为
`statistics.json`，注明各节来源文件）。

**3. 可视化（通用要求）。** matplotlib（Agg，150dpi → `/app/output/figures/`）：
组间分布用分组箱线+散点；关联用 Spearman 热图；区分度排序用横向条形图；回归
加残差-拟合散点。登记 `figures_manifest.json`（file/intent/columns/source_table）。
图上标注的统计量（如中位数线）必须与 statistics JSON 同源。

**4. 报告与 result.json。** `report.md` 结构：①数据与清洗口径 ②前提检验结论表
（每特征：Shapiro/Levene p → 所选方法及依据）③检验结果（p、效应量、校正后
显著性）④区分度排序或回归解读 ⑤图目录 ⑥结论 ⑦异常与不确定性。
**报告中每个统计数字必须能在 statistics JSON 中找到同值**，禁止凭记忆改写。
result.json 填全部契约字段；`quality_evidence` 含 cleaning_log.json、
statistics JSON、figures_manifest.json；`exceptions` 如实列出未解决问题。
缺什么就 partial + uncertainty，不补造。

## 异常处置表

| 情形 | 处置 |
|-|-|
| 某组 n<3 | 引擎记 error 不检验；报告如实说明该特征无法检验 |
| 正态性边界（n 大、p 略低于 α） | 按规则走非参，并在报告中注明人工复核意见（见 references） |
| scipy 缺失 | 引擎不可用：退回描述统计（pandas），result.json 标 partial 并声明推断层缺失 |
| 分组列不是类别/水平数 >12 | 先检查是否误选列；确实多水平时按任务要求聚合或声明超出范围 |
| VIF>10 | β 降级为相关结构描述，报告中显式声明 |
| p 不显著但任务断言有差异 | 如实报告不显著 + 效应量 + 检验力限制，不得迎合任务措辞 |

## 资源

- `scripts/premise_stats.py` — 前提裁决引擎（group / regress 两模式，本重心）。
- `references/test_selection_tree.md` — 决策树、多重比较与排序口径、已知边界。
- `examples/make_example.py` + `examples/README.md` — 合成示例（正态/偏态/无差异
  三特征走不同路径 + 回归模式）。

## 边界与不适用

- 仅单因素设计；多因素、协变量、重复测量超出范围（案例要求时声明）。
- 不做事后检验力分析；检验力限制以定性声明处理。
- 分类结果变量（如预测 class 标签）不是本引擎任务；案例要求时只做分组描述并声明。
