# 运行日志格式(journal_schema)

运行日志使审查过程可独立复跑:任何评审人拿到同一份输入文件与
run_journal.jsonl,应能重放全部步骤并得到同一张审查单。格式为 JSONL
(每行一个 JSON 对象),由 journal_check.py 校验。

## 一、条目字段(每条必填)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 顺序编号 `J-001`、`J-002`……,从 J-001 连续递增,不得跳号 |
| step | int | 步骤序号,严格递增,与 id 同序 |
| action | string | 该步做什么(如 "adjudicate D-03"、"run ledger_check.py") |
| tool | string | 使用的工具/命令;模型自身判断写 "model-reasoning" |
| inputs | array | 输入文件列表,每项 `{"path": ..., "sha256": ...}`;无输入给 `[]` |
| outputs | array | 输出文件列表,同构;无输出给 `[]` |
| decision | string | 该步的关键决定及理由(一句即可) |
| timestamp | string | ISO 8601 时间戳,全日志内非递减 |

可选字段:`final`(bool,仅末条为 true)、`note`。

## 二、强制规则(journal_check.py 校验,违反即交付失败)

1. 条目按 id 顺序排列、字段齐全、step 严格递增、timestamp 非递减。
2. 所有 sha256 为 64 位小写十六进制;声明的输入/输出文件必须在对应目录
   (--input-dir / --output-dir)存在且哈希一致——哈希对不上视为过程被篡改,
   直接失败。
3. 台账中每一个状态非"未检查"的单元,其 journal_ref 必须指向存在的日志
   条目 id(单元如何从未检查变为当前状态,必须可追溯)。
4. 末条必须 `final: true` 且 outputs 非空,即明确声明本轮交付了哪些文件;
   result.json 中每个关键字段(状态、发现数、来源、不确定性)应能回溯到
   某条日志条目的 decision。
5. 写日志的纪律:先批量裁决、再补日志时,日志时间戳也必须保持非递减,
   不得伪造与文件实际哈希不符的记录。

## 三、最小骨架示例

```jsonl
{"id":"J-001","step":1,"action":"read case.json + task.md, scaffold result.json","tool":"read + write","inputs":[{"path":"input/case.json","sha256":"<64hex>"}],"outputs":[{"path":"result.json","sha256":"<64hex>"}],"decision":"按 output_contract 建立 PENDING::* 骨架,status=partial","timestamp":"2026-01-15T09:00:00+08:00"}
{"id":"J-002","step":2,"action":"adjudicate D-03","tool":"model-reasoning","inputs":[{"path":"input/paper.txt","sha256":"<64hex>"}],"outputs":[],"decision":"方法部分未描述随机序列产生方法,记问题 F-001","timestamp":"2026-01-15T09:05:00+08:00"}
```
