# /app/work 目录约定（由 result_scaffold.py 生成）

- `contract.json`：contract_probe.py 的输出，契约字段清单的唯一权威来源。
- `result.skeleton.json`：result.json 骨架。写作过程中**增量填充**本文件：
  每个字段填 `status`/`value`/`sources`/`uncertainty`/`assumptions`/`notes`，
  完成后导出为 `/app/output/result.json`。
- `chapter.md`：章节正文草稿；定稿后复制到 `/app/output/chapter.md`。
- `snippets/`：建议存放中间片段，实现"尽早保存部分产物"。
- 最终产物一律放 `/app/output`；`/app/work` 内容不视为交付。
- 填充规则：字段语义不明时保守填充并在 `assumptions` 记录解释；
  材料缺失用 `status:"unavailable"` + 原因；最终交付不允许残留 `pending`。
