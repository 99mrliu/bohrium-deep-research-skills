# 合成示例任务（SYNTHETIC, not real papers, 非正式案例结果）

> 本文件是 budget-warden-qc Skill 的**合成最小示例**配套任务说明。全部文献均为虚构，
> DOI 使用 `10.0000/synth.*` 保留测试段，不对应任何真实出版物。

## 任务

围绕种子论文 `10.0000/synth.001`（Adaptive Gradient Sketching for Sparse Citation
Networks，2021，虚构），在 `examples/corpus/` 的本地语料缓存内完成引文追踪：

1. 解析种子，沿后向参考文献找到其方法出处；
2. 沿前向引用（语料只给参考文献列表时用反向索引恢复方向）找到后续工作；
3. 扩展到第 2 层，找出不直接引用种子的平行工作；
4. 跨库去重（同一篇可能同时出现在 Crossref 与 OpenAlex 风格记录中）；
5. 语料内无法解析的引用目标保留为 stub，不补造元数据；
6. 按 `case.json` 的 `output_contract` 逐字段交付 `result.json`。

## 预期要点

- 候选 6 条：种子 synth.001；一层出处 synth.002、synth.004；一层后续 synth.003；
  二层平行工作 synth.005；外加 1 个 stub（synth.404，故意不可解析）。
- synth.002 同时出现在 Crossref 与 OpenAlex 风格语料中，应按 DOI 合并为一条记录。
- 前向边（如 synth.003 → synth.001 的 citation 关系）由反向索引恢复，边上标注
  `direction_restored: true`。
