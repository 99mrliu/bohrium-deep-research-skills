# 运行契约（runtime contract）

本文件是 grant-e-contract-guard 的运行契约全文。任何步骤与本文件冲突时，以本文件与当次案例的 `output_contract` 为准。

## 1. 目录与文件

| 位置 | 用途 |
| --- | --- |
| `/input/case.json` | 案例定义。必读。含 `case_id` 与 `output_contract`（字段名运行时读取，**不得硬编码**）。 |
| `/input/task.md` | 任务说明与写作要求。必读。 |
| `/input/organizer-workorder.json` | 组织方工单，**可能存在**。存在则必读；其声明的"申请人证据缺失"按缺失处理。 |
| `environment/resources.yaml` | 资源说明，**可能存在**。 |
| `/app/work` | 工作目录：笔记、中间稿、账本 `ledger.json`、`checkpoints.jsonl`。 |
| `/app/output` | 交付目录：最终产物与可编辑稿件。**必须有 `result.json`**。 |

材料文件（PDF 等）按题目给定；PDF 是真实文件、**没有预抽取答案层**，必须实际读取（如 pdftotext），不得按文件名或领域标签补造内容。

## 2. result.json 合同

`result.json` 必须包含：

1. **原始 `case_id`**：与 `/input/case.json` 中的值精确一致（逐字符）。
2. **全部 `output_contract` 字段**：字段清单在运行时从案例读取；每个案例的清单可能不同。
3. **诚实的状态与记录**：
   - `status`：枚举见下；
   - `reason`：当 `status != success` 时说明原因；
   - `sources`：来源台账（每条论断/数字/引用的出处）；
   - `uncertainty`：不确定项与缺口说明；
   - 变更记录（如合同含 `change_record` 类字段）：每次就地迭代追加一条。

### status 枚举语义

| 值 | 语义 | 使用条件 |
| --- | --- | --- |
| `success` | 全部合同字段均有实质内容，无未声明缺口 | 所有要素成稿、引用全部核验、无占位残留 |
| `partial` | 部分内容完成，存在已声明的缺口 | **必须有非空 `reason`** 与缺口说明（`uncertainty` 或 `gaps` 至少其一为非空字符串列表） |
| `unable_to_determine` | 材料不足到无法对核心要求作出判断 | 说明缺什么、为何无法继续 |
| `refused` | 任务要求本身无法执行（如要求编造证据） | 说明拒绝理由 |

## 3. 诚实 partial 的判定标准

一份 `partial` 是"诚实的"，当且仅当同时满足：

- 已完成与未完成部分**边界清晰**：哪些章节成稿、哪些是占位，逐条可查；
- 每个占位都使用规范写法 `【待申请人确认：…】` 并在缺口清单中有对应条目；
- 不夸大完成度：含占位的章节不得计入"已完成"；
- `uncertainty`/`gaps` 覆盖全部已知缺失、冲突与未核验项；
- 绝不在异常后静默失败或把 `status` 编造为 `success`。

## 4. 运行纪律（合同优先、先落保底、就地迭代）

1. 材料清单一出来 **60 秒内**，先用 `contract_probe.py` 落一份 `status: partial` 的合法 `result.json`（保底）。此后任何时刻被截断，交付目录里都存在合法结果。
2. 每次改进**就地更新** `result.json` 与章节稿，并用 `checkpoint.py save` 留快照。
3. 用 `budget_ledger.py` 记账；近阈值时按降级建议转入"保底交付"（已写部分 + 缺口清单）。
4. 交付前必须 `contract_probe.py --validate` 通过（退出码 0）。
5. 预算：64 次模型请求 / 900 秒 / 每次响应 16384 tokens（含 reasoning）。
