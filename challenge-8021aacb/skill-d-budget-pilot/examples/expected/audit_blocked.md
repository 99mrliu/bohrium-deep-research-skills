# 交付终检报告（quality_gate）

- result.json: `/Users/liuhengshen/Desktop/bhr_product/8021-five-v2/skill-d-budget-pilot/examples/expected/result.json`
- 检查通过: 7/8
- 结论: **BLOCK**

| 检查项 | 结果 | 说明 |
|---|---|---|
| case_id_present | ✅ | case_id='SYNTH-D-001' |
| contract_fields_declared | ✅ | 2 fields |
| contract_fields_filled | ❌ | unfilled: diagnosis, editing_plan |
| status_legal | ✅ | status='partial' |
| partial_has_reason | ✅ | partial 必须说明限制 |
| checkpoints_cover_phases | ✅ | 4 checkpoints |
| deliverable_files_exist | ✅ | present |
| change_record_present | ✅ | change_record 为列表（可为空） |
