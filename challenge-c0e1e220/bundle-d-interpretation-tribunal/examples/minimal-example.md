# 最小示例（合成示例，非真实数据）

本示例数据由 `make_synthetic.py` 用固定种子（20240501）**合成**：对照组 /
处理组各 2000 行，score 分别服从 N(50, 10²) 与 N(51, 10²)——大样本小差异，
专门制造「统计显著但实际意义有限」的情形，用于演示措辞纪律。

## 输入

`make_synthetic.py --out <目录>` 生成：

- `synthetic.csv`：两列 `group,score`（单位 分）；
- `case.json`：case_id=case-synthetic-demo，9 个契约字段声明，α=0.05；
- `task.md`：合成示例任务说明。

## 调用

```bash
bash examples/run_example.sh
```

脚本自动：生成合成数据 → `pipeline_d.py run` → 断言 result.json 9 字段与
claims → `wording_lint.py` + `claim_bind.py`（好例 exit 0）→ 五组埋雷
（BANNED_PHRASE / P_WORDING / CI_MISREAD / DANGLING_EVIDENCE /
NUMBER_MISMATCH / UNHEDGED_PARTIAL，各自 exit 1 且命中违例码）→
归档好例产物到 `example_output/`。全部断言通过脚本才 exit 0。

## 示意输出（好例报告「结果解释」章节，真实文本见 example_output/report.md）

> 在 α=0.05 水平下，对照组与处理组的 score 差异具有统计学意义
> （Student 独立样本 t 检验，p<0.0001）；处理组的均值更高，均值差
> （对照组−处理组）为 -1.568 分。[ev:H1]效应量 Hedges g = -0.155，
> 95% 置信区间为 [-0.217, -0.093]，按常用阈值属于可忽略效应；
> 统计显著并不等同于实际重要，该差异的实际意义有限，是否达到最小
> 实际重要差异 Δ 需结合领域标准判断。[ev:H1]

要点：显著性句与实际意义句分离；数值与 `result.json.claims[0]` 存储值
逐字对应；`[ev:H1]` 标签可被 claim_bind.py 解析复核。
