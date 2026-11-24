# 冲突证据与研究空白登记（conflict_matrix）

## 冲突证据登记格式

conflicts.jsonl 每行一个 JSON 对象：

```json
{"topic": "冲突主题",
 "claim_id_a": "CL-02", "claim_id_b": "CL-06",
 "nature": "冲突性质与可能解释（人群/剂量/随访期/测量方式差异）"}
```

登记规则：

1. **双方都必须有回链证据**：audit_claims.py 校验 claim_id_a / claim_id_b
   均存在于 claims.jsonl 且各有 ≥1 条通过 C2 的证据，否则拒绝登记
   （status=rejected，仅警告）。没有证据支撑的"冲突"只是观点不合。
2. **不擅自取舍**：双方论断都保留在 claims.jsonl 与 coverage.md 中；
   冲突对写入 conflict_matrix.md；可能的解释（人群、干预剂量、随访期、
   测量方式、发表年份差异）由模型在综述中讨论，并列入 result.json 的
   uncertainty。
3. 冲突无法在现有材料内调和时，对应的综合论断应降级为 uncertain，
   并在 note 中指向冲突对。

## 研究空白登记格式

研究空白作为 uncertain 论断登记在 claims.jsonl（允许 0 证据），note 按
下列格式说明：

```json
{"claim_id": "CL-10", "strength": "uncertain", "section": "研究空白",
 "text": "75 岁以上高龄人群的运动干预效果尚不确定。",
 "note": "空白类型：人群空白；依据：R003 亚组 OR=0.88（95%CI 0.60-1.29）无统计学意义，且无专门 RCT；建议：未来研究应针对高龄亚组设计充分效能的试验。",
 "evidence": []}
```

空白类型建议取值：人群空白 / 干预空白 / 结局空白 / 随访期空白 /
方法学空白 / 地域空白。每条空白须注明"依据"（哪条证据或缺失暴露了它），
禁止凭空宣布"研究不足"。

## 与孤儿证据的关系

已提取却从未被任何论断引用的 span（C7 孤儿）是发现冲突与空白的候选池：
审计结束后应人工过一遍孤儿清单，确认是"提取冗余"还是"漏写的论断"，
后者须补登记 claim 后重跑审计。
