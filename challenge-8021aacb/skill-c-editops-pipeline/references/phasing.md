# 编辑操作排序规则（执行相位）

ops 的执行顺序影响结果正确性：先动结构，再动句子。按以下相位排列，相位内按原文顺序。

| 相位 | 包含 op | 理由 |
|---|---|---|
| P1 章节级 | `reorder_section` | 整节移动改变后续所有块的位置参照 |
| P2 段落级结构 | `move` `merge` `delete_duplicate` | 块集合变化；删重先于移动，避免搬动将被删的块 |
| P3 段内结构 | `split` | 拆分产生新块（原 ID + `b` 后缀），其后的 move 可引用新块 |
| P4 句级修改 | `narrow` | 在最终落位的块上改句子 |
| P5 插入 | `insert_transition` `add_limitation` | 过渡与限制说明必须插到最终位置 |

## 排序检查清单

- [ ] 没有任何 op 引用将被 `delete_duplicate` 删除的块作为 `after`/`into` 锚
- [ ] `split` 之后引用新块的 op 使用 `Bxxx b` 形式的新 ID
- [ ] `narrow` 的 target 在应用序列中未被 merge 吞并
- [ ] 每个相位的 ops 在 JSON 数组中按相位递增排列

## 与六维诊断的映射

| 诊断维度 | 常用 op |
|---|---|
| 研究问题 | `narrow`（贡献主张收窄）、`move`（RQ 句前置） |
| 章节结构 | `reorder_section`、`merge`（该合未合）、`move`（细节后移） |
| 论证链 | `move`（论据靠近论断）、`split`（杂糅段拆开）、`insert_transition`（补推理衔接） |
| 段落关系 | `insert_transition`、`move`、`split` |
| 重复内容 | `delete_duplicate`、`merge`（同义复述合并） |
| 结论边界 | `narrow`、`add_limitation` |
