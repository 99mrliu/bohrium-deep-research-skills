# SYNTHETIC 合成任务说明（仅演示接口，非正式案例）

围绕"锂离子电池正极材料"主题，对两篇合成论文构建增量文献知识图谱：

1. 先用 `primary-material.json`（溶胶凝胶 LiFePO4/C 论文）建 baseline v1 并封存；
2. 再以 `secondary-material.json`（水热 LFP/C 论文）为变更集做增量更新：
   - 合并真别名（LFP/C = LiFePO4/C，有显式原文证据）；
   - 保持通用样品"commercial carbon black"区分（不同物理样品，不可合并）；
   - 保留两篇相反的"谁优于谁"结论为冲突，不得覆盖、不得合成单一结论；
   - 不同论文的容量数值（158 vs 149 mAh/g）分开保存，不得合并。
3. 对 baseline 与 current 两个版本各执行查询，输出可回查证据。

根 case.json 的 DOI/title/authors 属于第一篇，不得套到第二篇。
段落定位为组织方 JATS paragraph_id，本包无 PDF 页码。
