# 人工确认门（Human Confirmation Gates）

本 skill **不伪造人工复核**。下列结论模型只能给出「待复核建议」，必须标记
`human_confirmation_required: true` 且 `final_decision: needs_human`：

## 触发条件（任一命中即入门）

1. **D3 元数据缺失型分歧的终判**——摘要/关键字段缺失时，任何方向（含倾向纳入或
   倾向排除）都只能建议，需人工获取全文后确认。
2. **所有 uncertain 升级的记录**——S1/S2 一致 uncertain，或仲裁后仍为 uncertain 的
   记录，一律升级为 needs_human。
3. **涉及案例未提供之全文信息的判断**——凡判定依据需要全文方法学细节、补充材料、
   作者通讯确认等 /input 中不存在的信息时，只能建议。
4. **abstract_missing 且非排除的记录**——记录本身摘要缺失却被（一致或仲裁）判为
   include/uncertain 时，入门。

## 措辞规范

- result.json 的 uncertainty/局限字段必须包含显式声明：
  「needs_human 记录（human_confirmation_required=true）仅为**待复核建议**，
  **未经人工复核确认**；本结果基于案例提供的有限快照，未做实时数据库检索，
  不保证全局召回。」
- 对每条入门记录，在交付清单中给出 record_id + 入门原因（D3 / uncertain 升级 /
  全文信息缺失 / 摘要缺失）。
- **禁止**的表述：「已人工复核」「已确认」「专家审定」等暗示人工已介入的措辞；
  fixture 中任何一方标注也不得表述为「正确答案」或「金标准」。
- 疑似模糊重复（dedup suspected_pairs）同样只列为待人工复核事项，不自动合并。

## 与计数闭合的关系

入门记录从 include/exclude 中移出，计入 needs_human：
`screened = included + excluded + needs_human`（audit_log.py 强制校验）。
