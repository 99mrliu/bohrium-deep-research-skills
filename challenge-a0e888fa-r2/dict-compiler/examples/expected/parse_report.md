# 解析报告（compile_dictionary 生成）

## 概要
- 输入（dictionary）: `examples/dictionary.md`（19 行）
- 输入（workorder）: `examples/workorder.md`（7 行）
- 编译规则: 14 条（R001…R014）
- 未解析/歧义: 2 条 → 须在 resolutions.json 中逐条裁决
- 工单条目: 5 条

## 未解析 / 歧义项（需人工裁决）

| 编号 | 文件 | 行号 | 原文 | 原因 |
| --- | --- | --- | --- | --- |
| U001 | examples/dictionary.md | 13 | \| turbidity_ntu \| NTU \| NA \| [0, 4000] \| 见附录 B \| 浊度 \| | 检出限表述无法解析：单元格「见附录 B」 |
| U002 | examples/dictionary.md | 18 | - conductivity_us_cm: 单位 μS/cm；哨兵 -999；范围 0 ~ 2000 μS/cm | 范围写法无法解析（支持 [a,b] / (a,b) / a–b）：单元格「0 ~ 2000 μS/cm」 |

## 逐行登记

| 文件 | 行号 | 分类 | 说明 | 原文 |
| --- | --- | --- | --- | --- |
| examples/dictionary.md | 1 | skipped | 标题行 | # 数据字典（示例） |
| examples/dictionary.md | 3 | skipped | 引用/说明行 | > 本文件为人工编造的合成示例，用于演示 dict-compiler 技能，不对应任何真实实验。 |
| examples/dictionary.md | 5 | skipped | 标题行 | ## 字段表 |
| examples/dictionary.md | 7 | skipped | 表头行 | \| 字段 \| 单位 \| 哨兵值 \| 有效范围 \| 检出限 \| 说明 \| |
| examples/dictionary.md | 8 | skipped | 表格分隔行 | \| --- \| --- \| --- \| --- \| --- \| --- \| |
| examples/dictionary.md | 10 | parsed | 登记单位 °C；哨兵 -999 → R001；range [-50, 60] → R002 | \| temperature_c \| °C \| -999 \| [-50, 60] \| - \| 测量温度 \| |
| examples/dictionary.md | 11 | parsed | 登记单位 mg/L；哨兵 -999, ND → R003；range [0, 100) → R004；检出限 0.01 → R005 | \| concentration \| mg/L \| -999, ND \| [0, 100) \| 0.01 \| 目标物浓度 \| |
| examples/dictionary.md | 12 | parsed | 哨兵 blank → R006；range [0, 14] → R007 | \| ph \| - \| blank \| [0, 14] \| - \| pH 值 \| |
| examples/dictionary.md | 13 | unparsed | 字段 turbidity_ntu 的检出限单元格未解析 | \| turbidity_ntu \| NTU \| NA \| [0, 4000] \| 见附录 B \| 浊度 \| |
| examples/dictionary.md | 13 | parsed | 登记单位 NTU；哨兵 NA → R008；range [0, 4000] → R009；检出限单元格「见附录 B」未解析 → U001 | \| turbidity_ntu \| NTU \| NA \| [0, 4000] \| 见附录 B \| 浊度 \| |
| examples/dictionary.md | 15 | skipped | 标题行 | ## 补充条目 |
| examples/dictionary.md | 17 | parsed | 登记单位 mL；哨兵 -999 → R010；physical [0, 1000] → R011；忽略描述段「量取样体积」 | - volume_ml: 单位 mL；哨兵 -999；物理界 [0, 1000]；量取样体积 |
| examples/dictionary.md | 18 | unparsed | 字段 conductivity_us_cm 的范围/物理界单元格未解析 | - conductivity_us_cm: 单位 μS/cm；哨兵 -999；范围 0 ~ 2000 μS/cm |
| examples/dictionary.md | 18 | parsed | 登记单位 μS/cm；哨兵 -999 → R012；范围单元格「0 ~ 2000 μS/cm」未解析 → U002 | - conductivity_us_cm: 单位 μS/cm；哨兵 -999；范围 0 ~ 2000 μS/cm |
| examples/dictionary.md | 19 | parsed | 忽略描述段「自由文本备注，无 QC 规则」 | - remark_note: 自由文本备注，无 QC 规则 |
| examples/workorder.md | 3 | workorder | 工单条目 WO-1；动作 ['sentinel_missing']；涉及字段 ['temperature_c', 'concentration', 'ph', 'turbidity_ntu', 'volume_ml', 'conductivity_us_cm'] | 1. [WO-1] 缺失分类：将 temperature_c、concentration、ph、turbidity_ntu、volume_ml、conductivity_us_cm 中的哨兵值标记为 missing，不得插补。 |
| examples/workorder.md | 4 | workorder | 工单条目 WO-2；动作 ['unit_scale']；涉及字段 ['concentration'] | 2. [WO-2] 单位换算：将 concentration 由 mg/L 换算为 μg/L（×1000），保留原列。 |
| examples/workorder.md | 5 | workorder | 工单条目 WO-3；动作 ['dedup']；涉及字段 ['sample_id'] | 3. [WO-3] 去重：按 sample_id 归一化主键去重（去空白、统一大写），保留首条记录。 |
| examples/workorder.md | 6 | workorder | 工单条目 WO-4；动作 ['range_qc']；涉及字段 ['temperature_c', 'concentration'] | 4. [WO-4] QC 标记：temperature_c 物理界 [-50, 60]，concentration 有效范围 [0, 100)，越界仅标记不修改。 |
| examples/workorder.md | 7 | workorder | 工单条目 WO-5；动作 ['lod_below']；涉及字段 ['concentration'] | 5. [WO-5] 检出限：concentration 低于 0.01 mg/L 标记 <LOD，不改动数值。 |

> 分类含义：parsed=已编译为规则；workorder=工单条目；unparsed=未解析（需裁决）；skipped=结构性/说明性行。
