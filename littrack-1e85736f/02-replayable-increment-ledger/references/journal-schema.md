# increment_journal.jsonl 模式（journal-schema）

`increment_journal.jsonl` 是 **append-only** 的 JSONL 证据账本：每行一个
完整 JSON 对象，永不修改、永不删除已有行。当前只定义一种记录类型
`record_type="run"`（一轮增量导入）。所有行以 canonical JSON
（键排序、无多余空白、UTF-8 不转义）写入，因此整文件可做逐字节比较。

## run 记录字段

| 字段 | 类型 | 含义 |
|---|---|---|
| `record_type` | string | 固定 `"run"` |
| `schema_version` | string | 当前 `"increment-journal/1.0"` |
| `run_id` | string | `run-` + sha256({window_start, window_end, input_digest}) 前 16 位十六进制；确定性导出，天然幂等键 |
| `window` | object | `{start_utc, end_utc}`，半开区间 `[start, end)` |
| `input_digest` | string | sha256(canonical([{source, 文件sha256}...]))；输入材料的内容指纹 |
| `alert_channel` | string | 投递渠道（本 skill 离线，固定为日志型，如 `"log"`） |
| `sources` | array | 每源 `{name, locator_file, file_sha256, items_path, item_count}` |
| `watermarks_before` / `watermarks_after` | object | per-source `{last_seen_date, last_seen_id}` 水位。推进规则：窗口内所有判定条目（new / version_update / duplicate）都参与取 max(日期)；skipped（窗口外 / 无日期）不推进 |
| `counts` | object | `{candidates, in_window, new, version_updates, duplicates, skipped_out_of_window, skipped_no_date}` |
| `events` | array | 每条候选题录一条判定事件（见下） |
| `deliveries` | array | 每条提醒投递记录（见下） |
| `events_sha256` / `deliveries_sha256` | string | 对应数组 canonical JSON 的 sha256，供快速逐字节核对 |
| `record_sha256` | string | 除本字段外整条记录 canonical JSON 的 sha256 |

## event（判定事件）

| 字段 | 含义 |
|---|---|
| `source` / `item_index` | 来源名与条目在源数组中的下标 |
| `locator` | `{file, json_path, file_sha256}`——复核锚点，如 `$.message.items[0]` |
| `title` / `item_date` | 规范化后的标题与 UTC 日期（无法解析时保留原值） |
| `identifiers` | `{doi, arxiv_base, arxiv_version, title_fp}` 全部规范化标识 |
| `dedup_key` / `key_rule` | 本条目的稳定键及其优先级链规则（K1/K2/K3） |
| `decision` | `new` / `duplicate` / `version_update` / `skipped` |
| `rule` | 命中规则号（见 dedup-key-rules.md） |
| `matched` | 命中已有条目时：`{dedup_key, first_seen_run, locator}`；否则 null |

## delivery（投递记录）

`{channel, delivered_to, dedup_key, decision, delivery_hash}`，其中
`delivery_hash = sha256(canonical({run_id, channel, window, dedup_key, decision, title}))`。
同一轮重放必然得到同一 hash，因此“是否重复投递”可机械核验。

## snapshot（increment-snapshot/1.0）

journal 的物化缓存，加速下一轮启动；**journal 才是权威来源**。

```json
{
  "schema": "increment-snapshot/1.0",
  "as_of_utc": "<本轮窗口终点>",
  "sources": {"<source>": {"last_seen_date": "...", "last_seen_id": "..."}},
  "seen_items": [{"dedup_key", "doi", "arxiv_base", "arxiv_version_max",
                  "title_fp", "title", "first_seen_run", "locator"}]
}
```

## 幂等性约定

`run_id` 由窗口与输入内容确定性导出。`record_run.py` 追加前检查：
若 journal 已含相同 `run_id`，则**不追加、不投递**，`--snapshot-out`
原样复制 `--snapshot-in`，summary 记 `appended=false` 与
`reason="run-already-recorded-idempotent-noop"`。
