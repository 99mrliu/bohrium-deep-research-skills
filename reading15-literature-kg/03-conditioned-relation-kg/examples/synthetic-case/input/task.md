# 任务说明（SYNTHETIC 演示案例，非平台正式案例）

围绕两篇合成论文构建**条件化关系知识图谱**：

1. 抽取实体（模型/数据集/指标/条件/任务），每个节点绑定
   source_id + JATS paragraph_id + 逐字短引。
2. 只建立有证据的关系；区分 author voice：
   primary-results / cited-background / interpretation / hypothesis。
   背景转述（cited-background）永远不得当作一手证据。
3. 比较与数值必须带条件作用域（dataset/metric/condition 等）；
   禁止全局赢家、禁止无单位或无条件数值。
4. 跨篇合并/不合并必须显式记录依据；共现不是直接关系。
5. 冲突（同源或跨源）全部保留并显式标注，绝不静默解决。
6. 执行至少 3 个真实查询，输出结果子图与证据。
