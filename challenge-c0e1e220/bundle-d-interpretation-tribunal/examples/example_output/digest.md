# digest.md — 待确认裁决（≤5 项）

## 候选列

group(文本,缺失0,取值2)；score(数值,缺失0,取值3786)

## 待确认项

1. **结果变量 / 分组变量**：当前 outcome=`score`（启发式：列名出现在 task.md 中），group=`group`（启发式：首个非数值列且取值数>=2），levels=None。核对 task.md 后如需覆盖：`python3 $SKILL_DIR/scripts/pipeline_d.py decide --work /app/work --set outcome=列名 --set group=列名 --set levels=a,b`
2. **单位**：当前 `分`（来自 task.md 或人工指定）。覆盖：`decide --work /app/work --set unit=单位名`
3. **检验路线**：Student 独立样本 t 检验（理由码 normal_ok_var_equal）。敏感性对照：Welch t 检验。
4. **claims**：共 1 条，其中显著 1 条；每条结论句在 report.md 中以 [ev:Hk] 绑定，可用 claim_bind.py 复核。
5. **警示**：置信区间刻画的是估计量的不确定性，并非个体取值的范围。；bootstrap CI 基于 B=2000、seed=20240501，复跑可完全复现。；敏感性对照（Welch t 检验）与主检验结论一致。

确认无误或完成 decide 后执行：`python3 $SKILL_DIR/scripts/pipeline_d.py finalize --input /input --work /app/work --output /app/output`
