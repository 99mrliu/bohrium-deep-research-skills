# 检查点格式与恢复语义

> `checkpoint.py` 读写的 `<workdir>/checkpoint.json` 结构，以及与账本链的关系。

## 账本行格式（ledger.jsonl）

每行一个 JSON 对象：

```json
{"seq": 0, "ts": "ISO-8601 UTC", "kind": "plan|spend|checkpoint|degrade|note",
 "payload": {...}, "prev_hash": "<64 hex>", "line_hash": "<64 hex>"}
```

- `prev_hash`：上一行的 `line_hash`；首行为创世值 `000…0`（64 个 0）。
- `line_hash`：`sha256(canonical_json({seq,ts,kind,payload,prev_hash}))`，其中
  规范 JSON = 键排序、紧凑分隔符、保留非 ASCII（UTF-8）。
- 校验：逐行重算 + 链式比对；任一行不符即"账本损坏"，所有读取方退出码 1。

## 检查点结构

```json
{
  "version": 1,
  "kind": "checkpoint",
  "created_at": "ISO-8601 UTC",
  "completed": ["v01", "v02"],
  "pending": ["v03", "..."],
  "result_draft": { "...result.json 草稿..." },
  "result_draft_sha256": "<sha256(canonical_json(result_draft))>",
  "ledger_head": "<写入时账本末行 line_hash，或创世值>",
  "prev_chain": "<上一检查点的 state_hash，或创世值>",
  "state_hash": "<sha256(canonical_json(除本字段外的全部字段))>"
}
```

`prev_chain` 使连续检查点自身也构成哈希链：改写任一历史检查点都会使其后的
`prev_chain` 失效。

## 恢复语义（restore 的三重校验）

1. `result_draft` 重算哈希 == `result_draft_sha256`（草稿未被改动）；
2. 全体字段重算 == `state_hash`（元数据未被改动）；
3. 若提供 `--ledger`：检查点记录的 `ledger_head` == 当前账本末行哈希
   （账本与检查点互为锚点，单边改动即被发现）。

任一校验失败：退出码 1，**绝不**静默地从被篡改状态恢复。恢复成功时输出
`restored_state.json`（completed / pending / result_draft），调用方以此为唯一
续跑依据：重算 `budget_state.json` → 以 `--completed` 传入已完成项 → 重新生成
计划。由于调度器是确定性的，同一状态必然得到同一后续计划，续跑位置精确无漂移。

## 写入纪律

- 第 0 步（计划生成后立即）写第一份检查点：诚实部分骨架——`case_id` 逐字保留、
  `status="partial"`、output_contract 全部字段镜像（未填者 null + uncertainty 占位）。
- 之后每完成若干核验项或每次降级前重写检查点；重写前先读旧 `state_hash` 作为
  `prev_chain`；旧检查点若是非法 JSON 则拒绝覆盖（退出码 1），先审计再处理。
- 检查点只写工作目录；交付物 `/app/output/result.json` 由最终步骤从草稿 + 成本报告
  汇总生成。
