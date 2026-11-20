# 筛选判定模板：/app/work/screen_judgments.jsonl

每行一个 JSON 对象，对 `canonical_records.json` 中**每一个** canonical_id 恰好一条判定。
缺判定、重复判定、理由码前缀不符、锚定失败都会使 `screen_canonical.py` exit 3
并写 `anchor_failures.json`；按失败项重锚后重跑即可。

## 行格式

```json
{"canonical_id": "can-001", "decision": "include|exclude|needs_human",
 "reason_code": "IN-*|EX-*|BND-*", "evidence_quote": "title/abstract 原文片段", "note": "可选说明"}
```

## 校验规则

- `decision` ∈ {include, exclude, needs_human}；
  reason_code 前缀必须一致（IN-/EX-/BND-，见 rules/reason_codes.md）。
- include / exclude：`evidence_quote` 必填，且经 NFKC+小写+压缩空白归一化后
  是该 canonical 记录 title 或 abstract 的子串（锚定）。**引用必须是原文，
  不得改写、不得凭印象编造**——锚定失败即 exit 3。
- needs_human：可免 `evidence_quote`，但 `note` 必填，说明无法自动判定的原因
  （如摘要缺失、标注冲突）。禁止把 needs_human 伪装成已裁定结论。

## 示例（合成，对应 examples/ 虚构数据）

```jsonl
{"canonical_id": "can-004", "decision": "include", "reason_code": "IN-INT", "evidence_quote": "deep learning models on 40,000 ICU admissions to predict in-hospital mortality", "note": "深度学习用于重症管理的原始临床研究"}
{"canonical_id": "can-002", "decision": "exclude", "reason_code": "EX-DESIGN", "evidence_quote": "We synthesized 38 studies evaluating deep learning algorithms", "note": "系统综述，非原始临床研究"}
{"canonical_id": "can-005", "decision": "needs_human", "reason_code": "BND-ABSTRACT-ONLY", "evidence_quote": null, "note": "摘要缺失，无法锚定证据，需人工获取全文"}
```
