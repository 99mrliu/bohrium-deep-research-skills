# 结果与诚实降级

动态复制 `case.json.output_contract` 所需全部字段。路径用相对 `/app/output` 的文件名。`content_map` 的每个元素保留 evidence ID、原始文件名、定位和引文；`compliance_checks` 是 `{name,status,detail}` 列表。

`success` 要求全部机械检查通过、实际 PNG/PDF 可回读，且没有未解决科学歧义。`partial` 用于部分产物可用，但缺证据、缺导出、引文不匹配或未决语义问题；exceptions 必须写清限制。`failed` 用于核心目标未完成，仍保留 result 与已有产物。

推荐补充 `sources,uncertainty,change_records,synthetic_example`。正式案例中 `synthetic_example=false`；所有随包示例为 true。

先用 partial 保底再增量更新，不允许用时限作为填造来源、检查或数值的理由。
