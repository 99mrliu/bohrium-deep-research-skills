# 人工复核工作流

## 1. 复核单元与顺序

review.md 按 status 分组：`conflict` 与 `not_reported` 优先复核（决定交付边界），
`inferred` 次之（检查推理链），`asserted` 最后（抽查 + 数值全查）。

每条断言的勾核位：

```
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______
```

## 2. 逐条勾核要点

1. **对得上**：引文是否逐字？位置能否回到原文？（拿 review.md 对照原 PDF）
2. **拆得细**：这一条是否还藏着第二个关系？限定是否完整（条件/数据集/版本/时间）？
3. **方向对**：主客体方向、被动语态、比较基准是否正确？
4. **模态对**：may/suggest/proposed 是否被保留？否定句是否 polarity=negative？
5. **置信度对**：rationale 是否指向具体证据而非套话？

## 3. 复核结论的回填

- 接受：无需改动；
- 修改：改断言（不是改引文凑断言），改后重跑导出与回读；
- 删除：删除并在 result.json 的 change_records 记录原因；
- 复核人信息（姓名/日期/样本量）写入交付物的 review_record 字段
  （任务契约要求时）；agent 自复核标 `reviewer: agent`。

## 4. 抽样规则（大集合）

- 全部 conflict/not_reported/inferred 必查；
- asserted：数值类全查，其余随机抽 20% 且不少于 10 条；
- 发现任何一条系统性错误（如同一页全部页码错 1）→ 扩大为全查该类。

## 5. 复核与导出的闭环

复核改动 → 重跑 export_bundle.py → 重跑 check_exports.py → manifest 哈希更新 →
change_records 记录。任何一步缺失都视为交付未完成。
