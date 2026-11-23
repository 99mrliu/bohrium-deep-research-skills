# 降级梯（budget ladder）：任何时刻都能安全交付

预算：64 次模型请求 / 900 秒。原则：**每个阶段结束都是可交付状态**；
预算见底时沿梯子下降，任何降级必须如实体现在 `result.json` 的 `status` 与
`uncertainty` 中。诚实标注的 partial 优于伪造完整的 success。

## 分级

| 级别 | 名称 | 触发条件 | 必须落盘的产物 | result.json 标注 |
|---|---|---|---|---|
| L0 | 完整交付 | 预算充足 | comparison-matrix.md、integration-report.md、result.json（lint 通过）、replay-report.json | `status=success`（仅当无不可比/未报告项）或如实 `partial` |
| L1 | 骨架矩阵 + 义务清单 | 抽取/判定做不完（时间或请求将尽） | 对已写入的 cells/decisions 立即跑 render_all + contract_lint：矩阵覆盖到哪算哪；uncertainty 逐条列出未覆盖的文档/字段/维度（义务清单） | `status=partial`，uncertainty 写明"哪些论文/字段尚未抽取" |
| L2 | 仅诚实 partial | 几乎无可用记录（如 PDF 提取全部失败） | init_contract 生成的契约骨架 result.json；在 uncertainty 中写明失败原因与缺失边界（哪些文档无法读取、哪个环节失败） | `status=partial`（骨架默认即是）；提取工具全军覆没可 `failed` |

## 操作要点

- **降到 L1**：停止抽取新记录 → `python3 scripts/render_all.py --force --workdir /app/work --outdir /app/output`
  → `python3 scripts/contract_lint.py ...`。记录写到哪，矩阵就渲染到哪——这是
  "记录为体"的直接收益：不需要为降级单独写任何产物。
- **降到 L2**：`init_contract.py` 跑完即是 L2 状态；只需把失败原因追加进
  work/ 中（可写一条 field 为 `_extraction_failure` 的 cells 记录，comparability
  全 `not_reported`，note 写明原因），重渲染后 uncertainty 自动带上。
- **时间盒守卫**：阶段 1（抽取）超过 360s 或请求用掉 40 次即停止抽取进入渲染；
  全程预留 ≥180s 给渲染+lint+replay+降级落盘。
- **恢复续跑**：预算恢复或重跑时，manifest 会跳过输入未变的阶段；只需继续往
  cells.jsonl / decisions.jsonl 追加记录再渲染。
- **禁止**：为赶预算而跳过 contract_lint；手改产物补齐缺失字段；把 L1/L2 包装成
  success。
