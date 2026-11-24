# 断点续跑与确定性纪律（resume guide）

## 1. 中断恢复操作序列

任务中断（预算耗尽、会话崩溃、换人接手）后，**不要凭记忆续跑**，按固定序列定位断点：

```
① runlog.py --log runlog.jsonl status    # 看已完成步骤与"首个未登记标准环节"
② runlog.py --log runlog.jsonl verify    # 确认已登记产物未被篡改/缺失
③ 从 status 指示的首个未登记环节继续；其输入必须是已登记且 verify 通过的产物
```

- 若 verify exit 3：按报错指名的**步骤+文件**处置——
  - 产物被外部修改：从该步骤的已登记输入重新生成该产物，重新登记（note 说明原因）；
  - 产物缺失：同上；若输入也丢了，向上回溯到最近一个完整登记的环节；
  - 若是**有意的人工修改**：补一条 `--actor human` 的登记与 change_records 记录。
- 若 runlog 本身丢失：以 `scaffold_result.py` 骨架和现存产物重建流程，status 视为
  "全部未登记"，从 ingest 重新登记现存文件（note 注明"runlog 重建"），并在
  result.json.status 降为 partial 说明账本断档。
- 恢复后继续正常流程；deliver 环节的 replay 会最终证明重跑一致性。

## 2. 确定性写作纪律（replay 不漂移的前提）

replay.py 把每个 manifest 步骤**连跑两次**并互比，再与 runlog 登记哈希比对。
以下写法必然导致 V4（非确定性）或 V8（漂移），写脚本时逐条自查：

1. **时间戳进产物**：`datetime.now()`、文件 mtime 嵌入 JSON/文本 → 必漂移。
   例外：runlog.jsonl 是账本不是产物，允许含时间戳；result.json 是交付物、
   不进 manifest 重放比对。
2. **随机数**：`random.random()`、`os.urandom`、未设种子的抽样 → 必漂移。
   确需抽样用固定种子并写进代码注释。
3. **绝对路径进产物**：把 `/Users/...` 写进输出文件 → 换机器/换目录 replay 必漂移。
   产物内只写相对路径或文件名。
4. **字典序/集合序不稳定**：`json.dump` 不加 `sort_keys=True`；直接序列化 set；
   遍历 `os.listdir()` 不排序 → 逐字节比对失败。统一 `sort_keys=True`、列表显式排序。
5. **环境依赖**：读环境变量、依赖本机 locale/时区格式化数字与日期、依赖网络接口
   返回顺序 → 重放环境稍变即漂移。确定性步骤必须离线、参数全显式。
6. **自读写不幂等**：脚本读取自己上一轮的输出再追加（如不判 stage 直接累加决策
   文件）→ 重跑第二次结果不同。重跑必须幂等：输入按类型/stage 过滤后再处理。
7. **浮点格式化不一致**：直接 `str(float)` 跨平台可能不同；需要时固定格式
   （如 `"%.4f"`）。

## 3. 步骤确实无法确定性化时

含模型判断的环节（筛选判定、质量评价、综合写作）天然不可重放，处置：

1. **不进 manifest**：manifest 只收确定性脚本步骤；
2. **冻结登记**：模型产物立即 `runlog.py record` 登记哈希，作为后续确定性步骤的
   冻结输入——这样 replay 仍能覆盖"冻结输入之后的全部计算"；
3. **若某脚本步骤经整改仍非确定性**（如必须调外部接口）：在 manifest 中移除该步骤，
   其产物按冻结输入登记，并在 result.json 中 `status=partial`、`uncertainty` 注明
   "步骤 X 不可重放及原因"；
4. 绝不允许为了让 replay 通过而删除产物或伪造哈希——verify/replay 指名的故障点
   必须如实进入 change_records。

## 4. 超时与预算保护

- replay.py 单步超时 120s：超时步骤多半依赖外部服务，按第 3 条整改；
- 平台预算耗尽时：result.json 骨架（scaffold_result.py 第 2 步落盘）+ runlog 已登记
  步骤保证"已完成的步骤不丢"，恢复时按第 1 条续跑，无需从头再来。
