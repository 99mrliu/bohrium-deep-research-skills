# 幂等与断点续跑设计（idempotency design）

目标：任意时刻中断、任意次数重跑，最终结果一致 —— 不重复处理、
不重复投递、不丢失已完成工作。

## 1. 三层状态文件

| 文件 | 语义 | 写策略 |
| --- | --- | --- |
| `checkpoint.json` | 「源 × 窗口」粒度的 completed / degraded | 每处理完一个源即**原子落盘**（tmp + rename） |
| `retry_journal.jsonl` | 每次尝试一条：attempt_no、failure_class、backoff_plan、decision | append-only |
| `delivery_log.jsonl` | 投递账本，每条带 `delivery_key` | append-only，写前查重 |
| `runs.jsonl` | 每轮运行摘要（供 change_records 组装） | append-only，每轮一条 |

## 2. 幂等键设计

- **处理幂等键**：`source_id|window`。重跑时命中 `completed` 即跳过，
  **不写任何新日志、不产生新事件** —— 因此第 N 次空跑的 journal 行数
  与投递行数增长为零。
- **投递幂等键**：`case_id|window|item_key`，`item_key` 取题录稳定标识
  （优先 DOI，其次源内 id）。`delivery_dedup.append_if_new` 先查重
  再追加，重复键一律抑制。

## 3. 崩溃窗口分析

```
读取材料 -> 投递（可能多条） -> 写 checkpoint
```

- 崩溃于「投递前」：重跑重新处理该源，无重复投递，安全。
- 崩溃于「投递中 / 投递后、checkpoint 前」：重跑会重新尝试投递，
  由 **delivery_dedup 按 delivery_key 抑制**，零二次推送；journal
  会多一条成功尝试记录（可接受的审计冗余）。
- 崩溃于「写 checkpoint 时」：原子写保证 checkpoint 要么是旧版
  要么是新版，不会是半截文件。
- degraded **不等于** completed：降级源在下一轮会被重新尝试，
  这正是「上一轮处理到一半中断 → 续跑只补未完成部分」的机制。

## 4. case 隔离

checkpoint 内嵌 `case_id`，加载时校验不匹配即拒绝复用，防止把
别的案例的完成状态错带进本案例。

## 5. 诚实降级

- 降级源进入 `degraded_sources`（含 failure_class、reason、attempts）；
- 存在任何降级/阻断/未处理的源×窗口 → `status = "partial"`；
- `uncertainty` 逐条说明缺失覆盖（哪个源、哪个窗口、什么原因、
  哪些记录被跳过）；
- `output_contract` 中本流水线无法产出的字段置 `null` 并在
  `uncertainty` 中声明，绝不编造。

## 6. 验证方法（合成示例已演示）

1. run1：源 B 截断 → partial，journal 记录 3 次尝试 + 确定性退避计划；
2. run2：源 B 修复 → checkpoint 命中跳过 A/C，只补 B → ok；
3. run3：无变化重跑 → journal / delivery_log 行数零增长；
4. 主动用已存在的 delivery_key 再投递一次 → 被抑制，账本行数不变。
