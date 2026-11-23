# 状态决策树与判定检查表

## 决策树

```
输入可读取、可解析？
  否 → input_error：骨架落盘（含 case_id 占位与错误说明），不编造内容。
  是 ↓
对该题的每个子问：
  通读相关章节（方法/结果/讨论/表格/图注）后，
  子问有材料支撑的论断？ ── 全部有 ──> answered
                          ── 部分有 ──> partial
                          ── 都没有 ──> 确认"确实未报告"（非"没找到"）──> insufficient_evidence
```

## 各状态的判定检查表

**answered**
- [ ] 每个子问至少一条 `reported` 论断支撑；
- [ ] `unanswered_parts` 为空（lint 的 E3 强制）；
- [ ] 所有比较论断已给出两个对象的数值。

**partial**
- [ ] 每个缺口在 `unanswered_parts` 中有 `part`（哪个子问）与 `reason`
  （材料未报告/只报告了 X 未报告 Y/段落损坏）；
- [ ] 已答部分的论断完整、可核对。

**insufficient_evidence**
- [ ] answer 中写明"已核对 P…、P… 等段落，材料未报告 X"（E3 的 WARN 检查词面）；
- [ ] claims 中可挂支撑"未报告"判断的段落（如原文明确否定句 "was not evaluated"）；
- [ ] 这是**有效回答**，不是失败。

**input_error**
- [ ] 输入确实无法读取/解析（文件缺失、非 UTF-8、非法 JSON、缺必要字段）；
- [ ] result.json 顶层 `status` 与错误说明如实写出；
- [ ] 绝不在 input_error 之后凭记忆补写"答案"。

## 状态与评分的关系

"材料未报告"若判断有依据（通读记录 + 明确核对段落），与完整作答同价；
漏答（题目在 answers 中缺席）与含糊（有支撑却不写）才是真正的失分点。
`unanswered_parts` 为空不代表 answered 成立——判定看论断与材料边界。
