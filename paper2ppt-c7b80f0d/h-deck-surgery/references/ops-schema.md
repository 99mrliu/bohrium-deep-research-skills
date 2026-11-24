# ops-schema.md — ops_journal.json 全部 op 的 schema、幂等语义、失败处理

## 顶层结构

```json
{
  "journal_id": "稳定标识（同一手术复跑保持不变）",
  "base_deck": "起始稿路径（记录用）",
  "ops": [ { "op_id": "op-001", "op": "set_title", "slide": 2, "params": {}, "reason": "..." } ]
}
```

- `op_id`：全局唯一、稳定。**同一 journal 复跑时靠它去重**，改名等于新 op。
- `reason`：必填、非空，写明为什么改（引用诊断/证据/task）。surgery_lint 校验非空。
- **页码语义（关键）**：`slide`/`after`/`from`/`to` 一律指**该 op 被应用那一刻**的
  deck 状态（1 起）。ops 按数组顺序依次应用；insert/delete/move 会改变后续 op 的页码坐标系。
  推荐写法：先做完所有针对原始页码的文本修改，再 insert/delete/move，最后按最终页码写 notes。

## op 一览

### set_title — 改页标题
```json
{"op_id":"op-001","op":"set_title","slide":2,"params":{"title":"Background and Motivation"},"reason":"..."}
```
幂等：当前标题已等于目标 → skipped(no-op)。失败：页无标题占位符 → failed。

### replace_text — 页内文本替换
```json
{"op_id":"op-002","op":"replace_text","slide":3,"params":{"old":"99.9 ms","new":"42.7 ms"},"reason":"..."}
```
在该页全部文本框内按段落替换。幂等：old 不存在且 new 已存在 → skipped(already applied)；
old 与 new 都不存在 → failed（old text not found）。

### set_bullets — 重写正文要点
```json
{"op_id":"op-003","op":"set_bullets","slide":4,"params":{"bullets":["...","..."],"placeholder_idx":1},"reason":"..."}
```
`placeholder_idx` 可省（默认第一个非标题占位符/文本框）。幂等：现有要点与目标完全一致 → skipped(no-op)。

### insert_slide — 插页
```json
{"op_id":"op-006","op":"insert_slide","after":4,"params":{"layout":"Title and Content","title":"Table 1 Summary","bullets":["..."],"notes":"..."},"reason":"..."}
```
`after` 为之前置页数（0 = 插到最前）；新页落在 after+1 位。layout 按名匹配，缺省/找不到用
"Title and Content" 或版式 1。**页预算**：插入后总页数不得超过 task.md 上限。

### delete_slide — 删页（受最小改动原则约束，见 minimal-change.md）
```json
{"op_id":"op-010","op":"delete_slide","slide":8,"reason":"..."}
```

### move_slide — 移页
```json
{"op_id":"op-011","op":"move_slide","params":{"from":7,"to":5},"reason":"..."}
```

### set_notes — 写演讲备注
```json
{"op_id":"op-007","op":"set_notes","slide":1,"params":{"notes":"..."},"reason":"..."}
```
不改变页文本哈希（text_hash 只含标题+正文），因此不触发"未涉及页变动"告警。幂等：内容相同 → skipped。

### add_figure — 贴图
```json
{"op_id":"op-004","op":"add_figure","slide":4,"params":{"image":"../input/figure1.png","left_in":3.5,"top_in":5.4,"width_in":3.0},"reason":"..."}
```
`image` 相对路径相对 ops_journal.json 所在目录解析；尺寸单位英寸（4:3 页面 10×7.5，
注意与正文占位符避让）。失败：文件不存在 → failed。

## 幂等语义（deck_ops.py）

1. **op_id 去重**：`--log` 已存在时，已 applied 的 op_id 一律 skipped，不重复应用、不产生新版本；
   上次 failed 的 op 会重试（修正 journal 后复跑的标准路径）。
2. **内容级幂等**：replace_text/set_title/set_bullets/set_notes 检测目标状态已达 → skipped(no-op)。
3. **版本连续性**：版本号从 versions/ 目录现有最大 vN 续编；首次运行先把原稿复制为 v1.pptx。
4. 复跑输出与状态（同 journal_id、同 log、同 versions 目录）确定一致。

## 失败处理

- 单个 op failed 不中断后续 op；全部处理完后统一汇报，**有 failed 退出码 2**。
- failed 记录进 ops_log.json（status/failed + detail），surgery_lint 将 failed op 记为 error。
- 缺 python-pptx：deck_ops 无法编辑，退出码 3 + stderr 说明（stdlib-fallback 只读，不伪造编辑）。
- rollback 指针：每个 applied op 记录应用前的版本文件绝对路径（versions/vK.pptx），
  回滚 = 用该文件覆盖当前 deck，或从该版本续跑新 journal。

## ops_log.json 形态

```json
{
  "journal_id": "...",
  "base_deck": "/abs/starting-deck.pptx",
  "runs": [{"run": 1, "ops_in_journal": 13, "applied": 13, "skipped": 0, "failed": 0, "out": "/abs/deck_final.pptx"}],
  "ops": [{"op_id": "op-001", "op": "set_title", "slide": 2, "status": "applied",
           "detail": "title set to '...'", "version_after": "v2",
           "rollback": "/abs/versions/v1.pptx", "reason": "..."}]
}
```

`runs` 逐次追加（幂等复跑会看到 applied=0、skipped=N）；`ops` 保留每个 op 的首次应用记录，
对接 result.json 的 `change_records: [{version, slide, change, reason, rollback}]`。
