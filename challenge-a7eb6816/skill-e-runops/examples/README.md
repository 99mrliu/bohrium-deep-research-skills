# 合成示例（非正式案例结果）

> **声明：本目录全部内容为合成示例，用于演示 runops 管线的真实运行行为，
> 非正式案例结果，不得作为评测答案。** 所有 expected/ 产物均为下列命令
> 真实运行产生（时间戳与 sha256 为真实值），复现会得到新的时间戳/hash。

## 素材设计（故意埋入四类异常）

- `case.json` 引用 `inputs/missing_table.csv`，但该文件**故意缺失**
  → missing_input；
- `inputs/main.md` 含"未发表数据 / 保密 / 不得外传"字样 → confidentiality；
- `task.md` 口径"能量密度以 350 Wh/kg 为准"与 main.md 的"能量密度 320 Wh/kg"
  故意冲突 → conflict；
- `task.md` 要求"不超过 300 字"，而 main.md 含 35 个关键信息点
  （25 字/点 ≈ 875 字下限）→ length_conflict。
- `case_fixed.json`：修复版（删掉 missing 引用与冲突口径任务句），
  供第二轮跑出 complete。

## 真实运行命令与结果

以下命令在 `examples/` 的上级目录（bundle 根）执行，Python 3.12：

```bash
# 1) 异常分流：退出码 0（无 halt），检出 6 条
python3 scripts/anomaly_triage.py --case examples/case.json \
  --task examples/task.md --indir examples/inputs --outdir /tmp/runops_r1
# → 6 条：missing_input=1, conflict=1, confidentiality=3, length_conflict=1
#   抄存：expected/anomaly_register.json / anomaly_register.md

# 2) 第一轮管线（含保底 init → stats → draft → finalize）：退出码 0
python3 scripts/run_pipeline.py --plan examples/pipeline_plan.json --root examples
# → 3 阶段全部 success；finalize 判为 partial（limitations 3 项：表格缺失、
#   能量密度口径冲突、涉密限制）。抄存：expected/checkpoint.json（首轮）、
#   expected/result.json（partial）、expected/draft_partial.md

# 3) 断点续跑演示：删除 stage1 产物后 --resume，退出码 0
rm examples/work/stats.json
python3 scripts/run_pipeline.py --plan examples/pipeline_plan.json \
  --root examples --resume 2>&1 | tee examples/expected/resume_log.txt
# → stats 重跑（产物缺失），draft / finalize SKIP（hash 未变）。
#   日志原文见 expected/resume_log.txt（run=1 skip=2）。

# 4) 修复后第二轮（case_fixed.json + 空 limitations）：退出码 0
python3 scripts/run_pipeline.py --plan examples/pipeline_plan_fixed.json \
  --root examples
# → finalize 判为 complete（word_count=92）。抄存：expected/result_complete.json
```

## expected/ 清单

| 文件 | 来源 |
| --- | --- |
| `anomaly_register.json` / `.md` | 第 1 步真实输出（6 条异常） |
| `checkpoint.json` | 第 2 步首轮完成时的检查点（3 阶段 success + 真实 sha256） |
| `result.json` | 第 2 步 partial 结果（limitations 含缺失表格等 3 项） |
| `draft_partial.md` | 第 2 步草稿（含数据缺口占位行） |
| `resume_log.txt` | 第 3 步续跑完整 stdout（stats 重跑、其余 SKIP） |
| `result_complete.json` | 第 4 步 complete 结果（limitations 为空） |

## 另已验证的边界行为（未留存产物）

- 全部引用输入缺失 → triage 退出码 2，条目 disposition=halt；
- 阶段命令非零退出 → run_pipeline 退出码 8，checkpoint 记 failed 与
  stderr_tail，result.json 自动定 failed 并附 failure.stage/reason；
- result_guard 操作错误（文件缺失/JSON 非法）→ 退出码 9。
