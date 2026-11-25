# 合成示例任务说明（SYNTHETIC, not real papers / 非正式案例）

本任务是 v2-d-contract-first-deliverable-forge Skill 的**合成最小示例**，全部文献为虚构
（DOI 形如 `10.0000/synth.*`），仅用于演示与自查，不代表任何真实科研结论。

## 任务

围绕种子论文 *Adaptive Graph Kernels for Retinal Vessel Segmentation*
（DOI `10.0000/synth.001`，2021）执行引文追踪：

1. 后向追踪：沿种子论文的参考文献找到其方法与数据出处；
2. 前向追踪：利用全语料反向索引恢复施引文献边（标注 `direction_restored`）；
3. 身份合并：DOI 规范化键＋标题规范化键去重（语料中有一篇无 DOI 的重复记录）；
4. 解析不出的引用目标保留为 stub，不得补造元数据；
5. 按 `case.json` 的 `output_contract` 逐字段镜像填充 `result.json`，
   并渲染人读交付包（证据表、CSV、网络预览图）。

## 输入

- `examples/case.json`（含带自定义字段的 output_contract）
- `examples/corpus/`：4 个文件、5 篇虚构文献记录（其中 2 篇为同一工作的重复记录）

## 预期输出要点

- 候选 4 条：`synth.002`、`synth.003`、`synth.004` 与 1 个 stub（`synth.999` 未收录）；
- 扩展边 10 条，其中前向 citation 边由反向索引恢复并标注 `direction_restored: true`；
- 身份合并 1 次（EuropePMC 记录按标题键并入 `10.0000/synth.002`）；
- `status = partial`（因存在 stub，诚实降级），`verify` 仍应通过（ok=true）。
