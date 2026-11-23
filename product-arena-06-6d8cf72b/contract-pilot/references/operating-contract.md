# 运行契约与检查点（contract-pilot）

## 预算与节奏

- 预算：64 次模型请求、900 秒、单次响应 16384 tokens。
- 检查点（pilot checkpoint 打印对应期望）：

| phase | 时点 | 期望状态 |
|---|---|---|
| `init` | 0% | 骨架 result.json + plan.json + audit-trail.jsonl 已落盘 |
| `t40` | ~40% | 完整但浅的交付：合同每个必需字段已有初稿值或 null+理由 |
| `t70` | ~70% | 每个请求项都有答案与锚点；剩余时间只做决定性核查与修复 |
| `t100` | ~100% | 停止新增内容；validate → 修复 → finalize |

## 纪律

1. 交付先行：任何时刻被打断，`/app/output/result.json` 都必须是合法 JSON 且带 `case_id`。
2. 不造工具：阅读/提取优先用平台工具与本 Skill 之外的既有能力；pilot 只管过程。
3. 诚实状态：`success` 是校验结论，不是愿望；finalize 是唯一允许写 success 的地方。
4. 审计留痕：init / checkpoint / finalize 自动追加 audit-trail.jsonl；Agent 的重大修正（改锚点、改裁定、降级）也应自行追加一条。
5. 不把校验通过当成内容正确：pilot 只保证结构合法与状态诚实；语义正确性由阅读质量决定。

## 状态语义

- `in_progress`：骨架或撰写中，仅 init 阶段出现。
- `success`：finalize 时零硬问题。
- `partial`：可交付但有缺口，`limits` 逐项命名。
- `failed`：材料不可读或运行失败，`failure` 写明原因与接管位置。
- `refused`：任务本身越界（如要求编造数据），`reason` 写明依据。
