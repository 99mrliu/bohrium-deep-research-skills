> 合成示例 / SYNTHETIC EXAMPLE：本报告由虚构输入生成，仅演示接口与流程，非正式案例结果。

# 质量门报告（decision-forge-qc / quality_gate.py）

- case_id: SYNTH-EXP-2026-001
- 结论: 拦截（FAIL）
- 缺陷数: 4

| # | 缺陷代码 | 说明 |
|---|---------|------|
| 1 | FIELD_GROUP_EMPTY | 方案 P_B 的字段组 controls 缺失或为空 |
| 2 | ELIMINATION_EVIDENCE_MISSING | eliminations[0]（方案 P_C）缺少 evidence_refs |
| 3 | SELECTION_CITES_PENDING | selection.rationale 引用了未确认（pending）确认项 CONF-EQP-01；未确认项不得写成已确认事实 |
| 4 | CONTRACT_KEY_MISSING | result_skeleton 缺少 output_contract 键: 'key_risks' |
