# 操作日志契约（journal contract）

日志是过程质量控制的唯一事实来源：**没记进日志的操作视同未发生**。

## 记录格式（journal.jsonl，每行一条，append-only）

```json
{"seq": 7, "ts": "2026-11-24T08:00:00Z", "op": "verify",
 "detail": {"citations_total": 5, "passed": 5},
 "files": [{"path": "/app/output/citation_verification.json", "sha256": "..."}],
 "prev": "a1b2c3d4e5f6a7b8"}
```

- `prev` 为前一条记录的哈希（sha256(JSON) 前 16 位），构成防篡改链；
  任何事后删改都会在 journal_audit.py 的链校验中断裂。
- `files` 记录操作对象的 SHA-256，即"我读的/我写的就是这个版本"的坐标。

## 操作类型与记录时机

| op | 时机 | detail 建议 |
|-|-|-|
| scan | 盘点输入目录后 | 文件数、各 text_status 计数 |
| read | 读取关键文件后 | 文件、读取目的 |
| search | 每次检索后（含零命中） | 检索式、命中数 |
| skip | 决定不处理某文件时 | 文件名、原因（不可读/无关/超预算） |
| decide | 每个实质性判断（版本取舍、拒答、采用某来源） | 结论 + 一句话依据 |
| verify | 每次机器核验后 | 总数、通过数 |
| write | 交付物落盘后 | 路径 |
| error | 任何失败 | 错误、影响范围 |
| seal | 收尾 | 最终 status |

## 最低齐备性（journal_audit.py 判定）

- scan ≥1、search/read ≥1、verify ≥1、seal =1；
- /input 下每个真实文件至少被一条日志触及（未触及 = 未检查，审计不通过）；
- 哈希链完整；seal 之后的追加会被标记 post_seal 并计入 issues。

## 诚实性

- skip 与 error 必须记录；漏记失败与伪造成功同罪。
- 预算或时间原因放弃的操作，记 skip 并说明，不允许静默省略。
