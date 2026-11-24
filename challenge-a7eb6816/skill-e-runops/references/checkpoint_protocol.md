# 检查点与续跑协议（checkpoint protocol）

## 1. 管线形态

`pipeline_plan.json` 声明阶段序列：

```json
{
  "case": "case.json",
  "workdir": "work",
  "outdir": "output",
  "warn_threshold": {"stage_seconds": 30, "total_seconds": 120},
  "stages": [{"name": "...", "command": "...", "outputs": ["相对 root 的产物"]}]
}
```

- 每阶段 `command` 由 `subprocess` 经 `sh -c` **真实执行**，cwd=root；
  stdout/stderr 全文落 `workdir/logs/NN_<name>.log`。
- **第 0 步永远是保底**：`result_guard init` 在 outdir 落 partial 脚手架
  （已存在则跳过）。此后任何时刻 result.json 都存在且状态诚实。
- 阶段命令必须确定性：禁止时间戳、随机数、网络结果进入产物内容，
  否则 hash 续跑判定失效。

## 2. checkpoint.json 结构

```json
{
  "plan": "<plan 绝对路径>",
  "root": "<root 绝对路径>",
  "started_at": "<ISO8601>",
  "stages": {
    "<name>": {
      "status": "success | failed",
      "finished_at": "<ISO8601>",
      "duration_s": 0.0,
      "outputs": {"<相对路径>": "<sha256>"},
      "returncode": 0,
      "stderr_tail": "<失败时保留，至多 800 字符>"
    }
  },
  "ledger": {"stages_run": 0, "stages_skipped": 0, "total_seconds": 0.0},
  "warnings": ["budget_ledger 告警: ..."]
}
```

- 每阶段结束立即整文件重写 checkpoint（先写后报，崩溃不丢已完成记录）。
- 时间戳与 sha256 一律为真实运行产生，禁止手填。

## 3. 续跑规则（--resume）

对每个阶段依次判定：

| checkpoint 状态 | 产物文件 | 产物 sha256 | 动作 |
| --- | --- | --- | --- |
| success | 全部存在 | 全部一致 | **SKIP**（ledger.stages_skipped+1） |
| success | 有缺失 | — | **重跑**该阶段 |
| success | 全部存在 | 任一变化 | **重跑**该阶段 |
| failed / 无记录 | — | — | **重跑**该阶段 |

- 重跑成功的阶段会刷新其 checkpoint 条目；被 SKIP 的阶段条目原样保留。
- 下游阶段产物 hash 未变时即使上游重跑过也可 SKIP（幂等阶段的收益）。

## 4. 失败处理

- 阶段 returncode≠0 或声明产物未生成 → 该阶段记 `failed`，保留
  `stderr_tail` 与原因；自动调用
  `result_guard finalize --fail-stage <name> --fail-reason <原因>`
  将 result.json 定为 failed；`run_pipeline.py` 退出码 **8**。
- checkpoint 原地保留，修复后 `--resume` 从失败阶段续跑。

## 5. 预算台账（budget_ledger）

- `ledger` 记录：已执行阶段数、跳过阶段数、累计耗时（秒，三位小数）。
- `warn_threshold`：`stage_seconds`（单阶段）、`total_seconds`（累计）。
  超限时告警同时写入 `checkpoint.warnings` 与 stdout（`WARNING` 前缀）。
- 告警不中断执行；是否降级（缩小篇幅、删减阶段）由人/上层 harness 决定。
- 模型请求数与 token 预算不在本层计量，需与 harness 台账合并后对账。

## 6. 诚实状态判定表（写死）

| 条件 | status |
| --- | --- |
| output_contract 全部必填非空 **且** limitations 为空 **且** 产物路径全部存在 | `complete` |
| 有实质交付但上述任一条不满足（缺口逐项列于 limitations） | `partial` |
| 阶段崩溃无可用产物，或存在 halt 级异常（附 failure.stage/reason） | `failed` |

- 判定只由 `result_guard.py finalize` 执行；人工不得直接编辑 status。
- 空值定义：`null`、空字符串、空数组/对象为空；数字 `0` 与 `false` 是合法已填值。
- 产物路径识别：字符串字段以常见产物扩展名结尾或含路径分隔符；
  按"相对 cwd"与"相对 outdir"两种基准各查一次。
