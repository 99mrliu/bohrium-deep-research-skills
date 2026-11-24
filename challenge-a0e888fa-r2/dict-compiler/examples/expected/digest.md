# 执行摘要 digest

## 规模（从产物重算）
- 输入数据行: 10
- 去重丢弃: 1
- 输出数据行: 9
- 输出列数: 15

## 变更统计（从 ledger.csv 重算）
- 缺失标记 marked_missing: 6（concentration:1, conductivity_us_cm:1, ph:1, temperature_c:1, turbidity_ntu:1, volume_ml:1）
- 单位换算 unit_convert: 8
- QC 标记 qc_flag: 6（below_lod:1, non_numeric:1, out_of_range:4）
- 无法解释 uninterpretable: 0
- 台账记录总数: 21

## 完整性
- cleaned.csv sha256: `f41cf191c31b4675aa5e2a3b578974c529530ed5370780a203821a3620807b21`
- ledger.csv  sha256: `11530c6afc0b88768a2bda9ca2e968f31c8eea3836d0fd95db1e91128c4c07af`

## 覆盖缺口与不确定性（来自 rules.final.json）
- 未覆盖字段 `remark_note`：原样保留，未做任何处理。

## 诚实声明
- 未插补任何缺失/非法源值；缺失值仅被分类标记（置空 + QC 标记）。
- 未推断任何总体统计量；QC 物理界/范围/检出限仅做逐格标记，不修改数值。
- 每一处改动均见 ledger.csv 逐格记录（rule_id + 字典/工单文件行号），无可追溯出处的处理不存在。
