# 清洗工单（示例·合成）

1. [WO-1] 缺失分类：将 temperature_c、concentration、ph、turbidity_ntu、volume_ml、conductivity_us_cm 中的哨兵值标记为 missing，不得插补。
2. [WO-2] 单位换算：将 concentration 由 mg/L 换算为 μg/L（×1000），保留原列。
3. [WO-3] 去重：按 sample_id 归一化主键去重（去空白、统一大写），保留首条记录。
4. [WO-4] QC 标记：temperature_c 物理界 [-50, 60]，concentration 有效范围 [0, 100)，越界仅标记不修改。
5. [WO-5] 检出限：concentration 低于 0.01 mg/L 标记 <LOD，不改动数值。
