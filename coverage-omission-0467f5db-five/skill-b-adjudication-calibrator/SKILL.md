---
name: adjudication-instrument-calibrator
description: 命中判定仪器标定技能。用于"检索覆盖率与遗漏分析"类任务：把命中判定当作一台需要先标定再使用的测量仪器——规则版本化（L1 标识符精确匹配 / L2 标题+年份近似匹配 / L3 人工裁决队列），在带标签的标定片段上计算混淆矩阵、Wilson 95% 置信区间与阈值扫描，灰区记录进入人工队列而非强行判定，最终以带置信区间的覆盖率完成"算覆盖—列漏检—做补检"闭环。当案例材料含标定片段或需要可辩护的命中判定口径时使用。边界：不做参考集上游取证（撤稿/标识符冲突只做基础标记），不以标定片段结论自动改写冻结规则，不报告无置信区间的点估计充当精确覆盖率。
---

# 命中判定仪器标定（adjudication-instrument-calibrator）

## 重心与适用条件

重心是**测量有效性**：覆盖率数字的可信度取决于判定仪器。同一个检索结果集，阈值 0.70 与 0.90 算出的覆盖率可以相差十几个百分点——不标定仪器就报覆盖率，等于用没校过的天平称样。本技能：

1. **规则版本化**：三级判定规则集中在脚本常量 `RULE_SPEC` 与 `references/match_rule_spec.md`，二者必须同步；任何改动升 `spec_version`；
2. **标定先行**：材料中若有带标签片段（文件名含 `calibration` 的 JSON，元素为 `{"ref":…, "candidate":…, "label":"hit"|"miss"}`），先产出 `calibration_report.json`：混淆矩阵、precision/recall 的 Wilson 95% 区间、0.60–0.95 阈值扫描；阈值调整只给建议，不自动改写冻结规则；
3. **灰区不硬判**：L2 相似度落在 [0.65, 0.80) 的记录进入 L3 人工裁决队列，主统计中**保守计为 miss** 并注明，避免高估覆盖率；
4. **带区间的覆盖率**：报告覆盖率点估计 + Wilson 95% 区间 + 仪器标定状态。

## 运行环境

- 输入 `/input/case.json`、`/task.md`，材料递归扫描；工作 `/app/work`；交付 `/app/output`。
- Python 3 标准库，零依赖，不联网。
- 预算 ≤64 请求 / ≤900 秒：一条命令跑完，模型请求只用于读说明与核对。

## 调用方式

```bash
python3 /skills/weekly-skill/scripts/adjudication_engine.py \
  --input /input --work /app/work --output /app/output
```

退出码：`0` 完成；`2` 材料不足（partial，产物照交）；`3` result.json 缺契约字段。先 `ls /skills/weekly-skill/scripts/` 确认实际安装路径。

## 判定规则（与 references/match_rule_spec.md 同步）

| 级 | 规则 | 判定 |
|---|---|---|
| L1 | DOI 或 PMID 规范化后精确相等 | hit；双方都有标识符且不等 → miss（标识符冲突） |
| L2 | 标题 token Jaccard ≥ 0.80 且年份一致（或一方缺年份） | hit，附 score |
| L2 灰区 | Jaccard ∈ [0.65, 0.80) 且年份一致 | defer_L3 → 人工队列，主统计保守计 miss |
| L3 | 人工裁决 | 仪器绝不自动判定 |

## 产物

| 产物 | 内容 |
|---|---|
| /app/output/result.json | case_id、output_contract 全字段、status、sources、uncertainty、change_log |
| /app/output/coverage_report.md | 覆盖率 + Wilson 区间 + 标定摘要 + 逐条裁决表 |
| /app/work/calibration_report.json | 混淆矩阵、阈值扫描、阈值建议（有标定片段时） |
| /app/work/adjudication_ledger.json | 逐条裁决台账（level、score、证据）、L3 队列 |

## 异常处理

- 无标定片段：照常运行，报告与 result.json 明确写"未标定"，该事实进 uncertainty；
- 标定片段标签异常（label 非 hit/miss）：跳过该条并计数；
- 参考集或检索结果缺失：status=partial，change_log 记录，已得产物照交；
- L3 队列非空：报告显式列出，提醒覆盖率是保守下界。

## 最小调用示例（合成示例）

`examples/input/` 为**合成**数据：10 条参考题录、3 条查询命中、8 对带标签标定片段（含 2 对灰区样本）。运行：

```bash
python3 scripts/adjudication_engine.py --input examples/input --work examples/run/work --output examples/run/output
```

预期（合成示例，非正式案例结果）：标定报告含 8 对样本的混淆矩阵与阈值扫描；主裁决命中 6、漏检 3、1 条进 L3 队列（保守计 miss），覆盖率带 Wilson95 区间。详见 examples/README.md。

## 自查方法

1. result.json 含 case_id 与契约全部字段；
2. `coverage.instrument.calibrated` 与 calibration_report.json 是否存在一致；
3. 逐条裁决表中每条 hit 都有 level 与 score，无 score 的 L2 hit 不存在；
4. L3 队列中的记录在主统计中均为 miss 且带 conservative_note。
