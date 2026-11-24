# 故障分类与处置策略（failure taxonomy）

本文件是 `scripts/failure_classify.py` 的方法学说明。增量导入的每次
「源 × 窗口」拉取，结果必属下表之一。离线评测中，源响应已固化为本地
JSON 快照，故障通过快照本身（截断、结构漂移、缺字段）或模拟钩子
（顶层 `"_simulate_error": "<class>"`）呈现。

## 分类总表

| failure_class | 触发信号 | 处置策略 | 退避计划（秒，确定性） | 耗尽/终止后 |
| --- | --- | --- | --- | --- |
| `rate_limit` | 模拟钩子 / 上游 429 语义 | **可恢复重试** retry | 5 → 30 → 120 | 跳过并降级该源×窗口 |
| `timeout` | 模拟钩子 / 材料文件不可读 | **可恢复重试** retry | 5 → 30 → 120 | 跳过并降级该源×窗口 |
| `parse_error` | `json.JSONDecodeError`（截断、坏字节） | **可恢复重试** retry | 5 → 30 → 120 | 跳过并降级该源×窗口 |
| `source_revision` | JSON 合法但无任何已知结构（`message.items` / `resultList.result` / `items`） | **阻断** block | 0（不重试） | 降级 + 标记需人工确认 |
| `missing_field` | 记录级缺 `doi`/`DOI` 或 `title` | **跳过并降级** skip_degrade（记录级） | 0 | 跳过该记录，源仍可完成 |
| `empty_window` | 条目列表为空 | **跳过并降级** skip_degrade（语义=正常完成） | 0 | 标记完成，note=empty_window |

## 判定要点

1. **parse_error 可重试的理由**：截断响应是传输层事故的固化表现，同一
   源下一轮快照可能完整；故给满 3 次尝试（首次 + 2 次退避重试），
   耗尽后降级而不是阻断。
2. **source_revision 必须阻断**：结构漂移意味着解析器假设已失效，
   盲目重试只会重复错误；继续按旧假设抽取还可能**静默产生错误字段**，
   这比缺失更危险，因此 block 并等待人工核对新结构。
3. **missing_field 是记录级而非源级**：个别记录缺 DOI/标题不应拖垮
   整个源；跳过该记录、把缺口写进 checkpoint 的 `records_skipped`
   与 result.json 的 `uncertainty`。
4. **empty_window 不是故障**：窗口内零更新是正常业务结果，标记完成
   （防止重跑反复处理），仅在 uncertainty 中留一句说明。
5. **退避是确定性计划表**：离线环境不真的 sleep，只把
   `backoff_plan_seconds` 与决策写入 `retry_journal.jsonl`，保证
   任意重跑的计划可复现、可审计。

## 证据要求

每条 journal 记录与每个降级条目都必须能回溯：

- `material`：材料文件相对路径；
- `detail`：分类器给出的原始证据（如 JSONDecodeError 的行列号）；
- 记录级问题给出 locator：`<material>#<items_pointer>/<index>`。

任何字段值只能来自案例材料；分类器自身不生成任何题录内容。
