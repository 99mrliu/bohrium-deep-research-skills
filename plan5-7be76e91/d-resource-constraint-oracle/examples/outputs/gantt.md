> 合成示例 / SYNTHETIC EXAMPLE：本报告由虚构输入生成，仅演示接口与裁决逻辑，非正式案例结果或真实实验室/供应商数据。

# 排期甘特表（gantt）

- case_id: case-syn-resource-001；基准日 2026-01-05；deadline 2026-03-31；1 格 = 1 天；半开区间 [start, end)。

| 方案 | 阶段 | 资源 | 开始 | 结束 |
| --- | --- | --- | --- | --- |
| P1 | prepare | - | 2026-01-05 | 2026-01-06 |
| P1 | execute | FURNACE-01 | 2026-01-06 | 2026-01-09 |
| P1 | characterize | XRD-01 | 2026-01-09 | 2026-01-10 |
| P2 | prepare | - | 2026-01-15 | 2026-01-17 |
| P2 | execute | PRESS-01 | 2026-01-31 | 2026-02-05 |
| P2 | characterize | XRD-01 | 2026-02-05 | 2026-02-06 |
| P3 | skipped_infeasible | - | - | - |

```
t0 = 2026-01-05（行首字符对应日期 t0+列偏移天）；'|' 列 = deadline （超出图幅或未给）
列偏移(十位): 0         1         2         3 
列偏移(个位): 01234567890123456789012345678901
基准线       : --------------------------------
P1 prepare     : #
P1 execute     :  ###
P1 characterize:     #
P2 prepare     :           ##
P2 execute     :                           #####
P2 characterize:                                #
```
