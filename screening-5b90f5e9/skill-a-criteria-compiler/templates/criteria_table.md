# criteria_table.json 填写模板

由 `build_criteria_skeleton.py` 生成骨架后，模型按案例标准文本填充 `criteria` 数组。

## 结构

```json
{
  "version": "v1.0.0",
  "research_question": "<研究问题原文>",
  "eligible_languages": ["en"],
  "criteria": [
    {
      "criterion_id": "INC1",
      "type": "inclusion",
      "statement": "<案例标准原文>",
      "predicate": "<可判定检查点描述：模型仅凭题名/摘要即可给出 pass/fail/uncertain 的判据>",
      "evidence_required": true,
      "reason_code": "<rules/reason_codes.md 中已注册的码>",
      "boundary_notes": "<边界情形说明：何种情况判 uncertain 并转人工>"
    }
  ],
  "changelog": []
}
```

## 字段要求

- `criterion_id`：纳入用 INC1、INC2…；排除用 EXC1、EXC2…。合成规则按表内顺序取"第一个失败"标准。
- `predicate` 必须可判定：写清"看到什么证据算 pass / 看到什么证据算 fail / 什么情况只能 uncertain"。禁止只抄 statement。
- `evidence_required`：默认 true（pass/fail 必须引用题录原文片段）。
- `reason_code`：只用 rules/reason_codes.md 注册码。
- `eligible_languages`：允许的语言代码列表；空数组表示不限制。语言不符由引擎强制 needs_human（EX-LANGUAGE），不自动排除。

## 填充示例一（虚构主题：咖啡因摄入与成人睡眠质量）

```json
{
  "criterion_id": "INC1",
  "type": "inclusion",
  "statement": "研究对象为健康成年人（18–65 岁）",
  "predicate": "题名/摘要明确报告受试者为 18–65 岁成人则 pass；明确为未成年人、老年人(>65)或动物则 fail；年龄段未报告则 uncertain",
  "evidence_required": true,
  "reason_code": "EX-POPULATION",
  "boundary_notes": "年龄范围部分超出 18–65（如 18–80）判 uncertain，注 BND-PARTIAL-OVERLAP"
}
```

## 填充示例二（虚构主题：退役太阳能板回收技术）

```json
{
  "criterion_id": "EXC2",
  "type": "exclusion",
  "statement": "排除综述、社论与会议摘要",
  "predicate": "题名/摘要明示为 review / editorial / conference abstract 且无原始数据则 fail；明确报告原始实验数据则 pass；文献类型不明则 uncertain",
  "evidence_required": true,
  "reason_code": "EX-DESIGN",
  "boundary_notes": "系统综述若含原始荟萃数据判 uncertain，注 BND-ABSTRACT-ONLY"
}
```
