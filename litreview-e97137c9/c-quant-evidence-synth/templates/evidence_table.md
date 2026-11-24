# 定量证据表模板

填写规则：每行绑定一个 quant candidate（`Q#` 来自 `work/quant_normalized.jsonl`）；
"数值(原文)"列照抄候选的 `value`+`unit`，"归一化值"列照抄 `value_canonical`+`unit_canonical`，
不得改动数值；解读写入备注列。冲突对在备注中给出对象/条件差异假设并标 contested。
单源数值禁止写"平均提升/总体效应"；unnormalized 候选只定性提及。

```markdown
# 定量证据表（数值均回链 quant candidates）

| 证据ID | qid | 文献 | 定位 | 指标 | 数值(原文) | 归一化值 | 量纲 | 强度 | 备注 |
|-|-|-|-|-|-|-|-|-|-|
| E1 | Q1 | D1 | p1.¶5 | recall@10 | 0.74 | 0.74 ratio | ratio | suggestive | 95% CI [0.68, 0.80], n = 480, p < 0.01 |
| E2 | Q5 | D2 | p1.¶4 | recall@10 | 0.52 | 0.52 ratio | ratio | contested | 与 E1 冲突（C1）：相对差异>20% 且 CI 不重叠；对象/条件差异假设：…… |
| E3 | Q2 | D1 | p1.¶6 | latency | 350 ms | 0.35 s | time | suggestive | 原文单位 ms |
| E4 | Q6 | D2 | p1.¶5 | latency | 0.31 s | 0.31 s | time | suggestive | 原文单位 s；与 E3 归一化后方可比较 |
| E5 | Q9 | D3 | p1.¶2 | precision | 0.81 | 0.81 ratio | ratio | suggestive | abstract_only，单源，不得称"平均提升" |
| E6 | Q10 | D3 | p1.¶3 | rmse | 4.2 | —（unnormalized） | — | suggestive | 无单位无默认量纲，不参与跨文献比较 |
```
