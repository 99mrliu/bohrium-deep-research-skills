# 审计裁决

总体: **PASS ✅**

- ✅ A_input_freeze — `{"mismatched": []}`
- ✅ B_row_reconciliation — `{"raw_rows": 6, "cleaned_rows": 5, "dedup_drops_in_ledger": 1, "expected_raw": 6}`
- ✅ C_no_invented_rows — `{"invented_keys": []}`
- ✅ C_no_silent_edits — `{"unlogged_diffs": [], "unlogged_count": 0}`
- ✅ D_dropped_rows_logged — `{"keys_only_in_raw": 0, "dedup_drops_in_ledger": 1, "note": "每个消失的键至少需一条 dedup_drop 台账"}`
- ✅ E_unit_inverse — `{"checked": 1, "bad": []}`
- ✅ F_report_recompute — `{"diffs": {}}`
- ✅ G_workorder_coverage — `{"items": 4, "uncovered": []}`
