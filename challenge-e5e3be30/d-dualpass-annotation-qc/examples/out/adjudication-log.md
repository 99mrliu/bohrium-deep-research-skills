# 双通道标注仲裁日志

- 论断总数：5
- Cohen's kappa：0.7368
- 平均页码 Jaccard：0.7
- 至少一页精确重合比例：0.8
- 需复核（needs_review）：2 条；其中冲突标记（conflict）：0 条

## 终判分布

- supported: 1
- partially_supported: 2
- contradicted: 1
- insufficient_evidence: 1

## 逐条仲裁明细

### C1 → supported（一致采纳）

- 仲裁理由：两通道判定与定位一致，直接采纳
- 合并证据页码：[1]

| 通道 | 判定 | 证据页 | 原文引句 | 理由 |
|---|---|---|---|---|
| pass_a | supported | [1] | NPC-800 delivers a specific capacity of 412 mAh/g after 200 cycles at 0.1 A/g, corresponding to a capacity retention of 91%. | 摘要逐字给出 0.1 A/g、200 次、412 mAh/g，全部槽位吻合 |
| pass_b | supported | [1] | 在 0.1 A/g 下循环 200 次后比容量为 412 mAh/g，容量保持率 91%。 | 摘要中文段逐字对应，四槽位全部吻合 |

### C2 → partially_supported（provisional，needs_review）

- 仲裁理由：判定一致但证据页码无重合（location_divergence），页码取并集，建议复核定位
- 合并证据页码：[2, 4]

| 通道 | 判定 | 证据页 | 原文引句 | 理由 |
|---|---|---|---|---|
| pass_a | partially_supported | [4] | We tentatively attribute the capacity advantage of NPC-800 over NPC-900 in part to its higher nitrogen content... the present data do not allow a definitive causal assignment. | 原文为 tentative/in part 的弱归因，论断称'明确归因'，断言升级 |
| pass_b | partially_supported | [2] | Nitrogen content measured by XPS was 8.7 at% for NPC-800 and 4.2 at% for NPC-900. | 仅定位到氮含量数据（页2），未见明确归因句；判部分支持（演示定位分歧：漏检页4讨论） |

### C3 → partially_supported（provisional，needs_review）

- 仲裁理由：保守默认：分歧对 (supported, insufficient_evidence) 取更不乐观判定 → partially_supported
- 合并证据页码：[3, 4]

| 通道 | 判定 | 证据页 | 原文引句 | 理由 |
|---|---|---|---|---|
| pass_a | supported | [4] | The hierarchical pore structure facilitates electrolyte infiltration and shortens ion diffusion pathways. | 摘要与讨论均将孔结构与性能关联，判支持（Pass A 演示判定，偏宽松） |
| pass_b | insufficient_evidence | [3, 4] | 分级孔结构在多个样品中均与更好的倍率表现相关（相关性观察，非因果证明）。 | 原文明确标注'相关性观察，非因果证明'，因果断言无充分证据（Pass B 演示判定，偏严格） |

### C4 → contradicted（一致采纳）

- 仲裁理由：两通道判定与定位一致，直接采纳
- 合并证据页码：[3]

| 通道 | 判定 | 证据页 | 原文引句 | 理由 |
|---|---|---|---|---|
| pass_a | contradicted | [3] | At 1 A/g, NPC-800 retains 78% of its initial capacity after 1000 cycles. | 原文 78% 与论断'超过 80%'直接冲突 |
| pass_b | contradicted | [3] | At 1 A/g, NPC-800 retains 78% of its initial capacity after 1000 cycles (Figure 4). | 78% < 80%，与论断直接冲突 |

### C5 → insufficient_evidence（一致采纳）

- 仲裁理由：两通道判定与定位一致，直接采纳
- 合并证据页码：[]

| 通道 | 判定 | 证据页 | 原文引句 | 理由 |
|---|---|---|---|---|
| pass_a | insufficient_evidence | [] | （无） | 原文明确所有测试在 25 °C 进行，未报告 55 °C 工况 |
| pass_b | insufficient_evidence | [] | （无） | 检索 温度/高温/55 均无命中；实验节注明 25 °C 环境温度 |
