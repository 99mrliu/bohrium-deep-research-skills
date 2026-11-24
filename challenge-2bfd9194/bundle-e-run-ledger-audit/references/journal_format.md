# operations_journal.jsonl 格式规范（WAL 台账）

每行一个 JSON 对象（UTF-8，`ensure_ascii=False`，键排序），追加写入 + fsync。
两行公共字段：

- `seq`：单调递增整数，= 历史最大 seq + 1（重跑不重置、不复用）。
- `ts`：UTC ISO-8601 时间（毫秒精度）。

## 记录类型

### begin —— 复制动作开始（写前日志）

```json
{"op":"begin","id":"op0001","src":"report_v1.txt","dst":"library/drafts/report_v1.txt",
 "dst_staging":"/app/work/staging/op0001.part","sha256_src":"<hex>","bytes":97,
 "seq":1,"ts":"..."}
```

- `src` 相对 /input，`dst` 相对 /app/output，`dst_staging` 为 staging 绝对路径。
- 先写 begin 再动手：任何时候崩溃，journal 里都有"打算做什么、源哈希是什么"。

### done —— 两段式提交完成

```json
{"op":"done","id":"op0001","src":"report_v1.txt","dst":"library/drafts/report_v1.txt",
 "sha256_dst":"<hex>","bytes":97,"seq":2,"ts":"..."}
```

仅在「staging 哈希 == sha256_src 且 os.replace 成功且最终文件哈希 == sha256_src」后写入。
`sha256_dst` 是对最终文件重新计算的，不是照抄。

### failed —— 任一阶段失败

```json
{"op":"failed","id":"op0001","src":"...","dst":"...","phase":"copy","error":"...","seq":3,"ts":"..."}
```

`phase ∈ {hash_src, staging_hash_mismatch, final_hash_mismatch, copy}`。
failed 之后允许同 id 重试；审计只追究"有 failed 且无后续同 id done"的未恢复项。

### reconciled —— 启动时对崩溃残留的收尾

```json
{"op":"reconciled","id":"op0007","src":"...","dst":"...","staging_removed":true,
 "staging_path":"...","error":null,
 "reason":"begin_without_close_at_startup; staged copy discarded","seq":9,"ts":"..."}
```

apply 启动时扫描 journal：begin 无 done/failed/reconciled 闭合 → 删除其 staging 残留，
补 reconciled。保证中断后重跑从干净状态继续，且收尾本身也留痕。

### corrupt_line —— 坏行不静默

读取时遇到无法解析的行，记 `{"op":"corrupt_line","line_no":N,"raw":"..."}` 参与审计
（审计 C 项会 FAIL），绝不悄悄跳过。

## 不变量（审计依据）

1. 每条 begin 必有同 id 的 done/failed/reconciled 之一闭合；
2. library/ 中每个文件存在至少一条 dst 相同的 done，且 sha256_dst == 文件实测哈希；
3. 同一 id 的序列只允许 begin → (done | failed | reconciled)（failed 后可再次 begin 重试）；
4. replay 仅复放 done 记录（按 seq 升序），failed/reconciled 一律跳过。
