# 校准日志（合成示例输出，非正式测评结果）

管道：severity_gate（R1–R8）→ fp_screen（FP-01…FP-10）→ adjudicate（A1–A5）

| finding | type | 草稿严重度 | 闸门后 | 闸门触发规则 | 误报鉴别 | 终审裁定 | 最终严重度 | 最终状态 |
|---|---|---|---|---|---|---|---|---|
| F-001 | image_reuse | critical | minor | R3_integrity_needs_external(severity_cap), R1_inference_cap(severity_cap) | keep(FP-00_no_rule_hit) | 待复核 | minor | 待复核 |
| F-002 | missing_doi | minor | minor | R8_keep(keep) | drop(FP-01_no_doi_convention) | （fp_screen 已排除） | minor | 误报排除 |
| F-003 | metadata_mismatch | major | major | R8_keep(keep) | drop(FP-03_author_name_variant) | （fp_screen 已排除） | major | 误报排除 |
| F-004 | metadata_mismatch | major | major | R8_keep(keep) | keep(FP-00_no_rule_hit) | 维持 | major | 确认 |
| F-005 | missing_ethics | major | major | R8_keep(keep) | keep(FP-00_no_rule_hit) | 维持 | major | 确认 |
| F-006 | suggestion | minor | info | R1_inference_cap(severity_ok), R5_suggestion_info(severity_cap) | keep(FP-00_no_rule_hit) | 维持 | info | 确认 |
| F-007 | unsupported_claim | major | major | R8_keep(keep) | keep(FP-00_no_rule_hit) | 维持 | major | 确认 |
| F-008 | fabrication_suspected | critical | major | R3_integrity_needs_external(severity_cap) | keep(FP-00_no_rule_hit) | 待复核 | major | 待复核 |
| F-009 | statistics_error | major | minor | R1_inference_cap(severity_cap), R2_inference_pending(status_pending) | drop(FP-07_p_value_style) | （fp_screen 已排除） | minor | 误报排除 |
| F-010 | abstract_inconsistency | minor | minor | R1_inference_cap(severity_ok), R2_inference_pending(status_pending) | drop(FP-10_abstract_detail_diff) | （fp_screen 已排除） | minor | 误报排除 |

## 终审汇总

```json
{
  "total": 10,
  "upheld": 4,
  "downgraded": 0,
  "pending_review": 2,
  "dropped_by_fp_screen": 4
}
```
