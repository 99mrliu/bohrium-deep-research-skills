# 质量控制协议（replay-custody references）

## 三道机器门槛

### 1. 保管链（journal.jsonl）

每条记录 `hash = sha256(不含 hash 字段的规范化 JSON)`，`prev_hash` 指向
上一条。任何事后插入、删除、修改都会使 `seal` 校验失败。日志只增不改；
记错的处理方式是追加一条更正记录，而不是编辑旧记录。

### 2. 证据核验门（gate）

一张证据卡通过的条件（三条同时满足）：

1. 所引文件当前 sha256 与登记值一致（登记后被改动即全部相关卡拦截）；
2. `quote` 是该文件**当前抽取文本**的逐字子串（改写、概括、翻译均判负）；
3. 若提供 `char_start/char_end`，切片必须与 `quote` 完全相等。

拦截的论断进入 `rejected_claims` 并写入 uncertainty；**不允许** Agent
把被拦截的论断改写后再次提交同一文件同一区间——需要先回到原文重新
登记证据卡。`not_found` 卡作为诚实的阴性结果直接通过。

### 3. 契约检查（contract）

- `case_id` 与 case.json 完全一致；
- `output_contract` 每个字段在 result.json 中存在（可为 null，但
  必须在 uncertainty 说明原因）；
- `status ∈ {complete, partial}`；
- 被拦截论断不得出现在 answers 中。
- 检查器退出码非 0 时禁止提交该 result.json。

## 第三方复核（REPLAY.md 内容）

1. 用同一文档库与 case.json 重放 journal 中记录的命令序列；
2. 对任一结论按 `file` + `char_start/char_end` 定位，逐字比对 `quote`；
3. 重跑 `custody_journal.py seal` 复验保管链；
4. 重跑 `custody_contract.py` 复验契约。

## 诚实性红线

- 找不到 → `not_found`（记录检索词与覆盖文件数），不虚构。
- 抽取失败（无权限/加密/无文本层）→ 该文件不计入覆盖数，列入
  uncertainty。
- 部分完成 → `status: partial`，已完成与未完成的分界写进 summary。
