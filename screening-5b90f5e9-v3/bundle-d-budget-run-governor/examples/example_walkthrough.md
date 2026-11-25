# 示例走查：budget-run-governor 多阶段运行与中断续跑

> **合成示例，非真实评测案例。** `case.json` 中 9 条题录全部为演示虚构
> （R05 是 R01 的合成重复导出夹具，R04 带合成冲突双人意见夹具），
> 所有"判定/诊断"均为占位模拟，不构成真实筛选结论。
> 以下命令均真实执行过，exit code 与产物见 `selftest_log.md`。

## 目录约定

```
examples/run_full/     场景一：完整 L0 运行的真实产物（spent=16/64）
examples/run_resumed/  场景二+三：中断续跑、删产物恢复的真实产物（spent=30/64，如实累计）
  ├── input/case.json   输入快照
  ├── work/             run_plan.json / budget_ledger.json / checkpoint.json / 各阶段产物
  └── output/result.json
```

## 场景一：完整运行（L0）

```bash
python3 scripts/simulate_stages.py --case examples/case.json --root examples/run_full
# exit=0
```

调度器依次真实调用四个机制脚本，关键输出：

```
[plan_run] N=9 batch=3 档位=L0 预估请求=16/64 预估秒数=232/900
[plan_run] 风险点: 输入含组织方标注的夹具记录（合成重复导出/冲突双人意见）共 2 条……
-- 阶段 inventory（est_requests=0）--  → charge → checkpoint → flush(status=in_progress)
……（8 个阶段逐一执行）……
[flush] 已落盘 …/output/result.json（status=completed, level=L0, 已完成阶段=全部 8 个）
```

目检 `run_full/output/result.json` 要点：

- `screening_summary`：total=9，decided=8（R05 已并入 R01 不重复判定），
  included=4 / excluded=3 / uncertain=1；
- `dedup_report.duplicate_clusters`：R01←R05，basis 明确；
- `dedup_report.conflict_flags`：R04 冲突双人意见 → 保守置 uncertain 留待人工复核，
  **调度器未伪造复核结论**；
- `change_records`：merge_duplicate_export 一条，含 actor 与时间；
- `uncertainty`：如实列出 R04 待人工复核；
- `scheduler.ledger`：spent_requests=16，reserve=2 始终未被动用。

## 场景二：模拟崩溃 → 从检查点续跑

```bash
python3 scripts/simulate_stages.py --case examples/case.json --root examples/run_resumed --fail-at decide
# exit=3（模拟崩溃）
```

崩溃瞬间的产物现场（这是本技能的核心承诺）：

- `output/result.json`：`status=in_progress`，`decisions=null`，
  uncertainty 如实写明"decisions 尚未生成：判定阶段未完成"——**中断时刻也是合法交付**；
- `work/checkpoint.json`：inventory/scaffold/normalize/dedupe 四阶段的 sha256 记录；
- `work/budget_ledger.json`：已耗 2 次请求，预算现场保留。

定位与续跑：

```bash
python3 scripts/checkpoint.py --work examples/run_resumed/work verify        # exit=0，4 阶段 OK
python3 scripts/checkpoint.py --work examples/run_resumed/work resume-point  # 输出 decide，exit=0
python3 scripts/simulate_stages.py --case examples/case.json --root examples/run_resumed --resume
# exit=0
```

续跑输出节选：

```
[simulate] 续跑模式：保留既有台账，已消耗预算继续计数。
[simulate] 续跑起点：decide（已完成阶段跳过）
-- 阶段 decide -- …… -- 阶段 final_check --
[flush] …（status=completed, level=L0, 已完成阶段=全部 8 个）
```

已完成阶段**没有重跑**：续跑仅新增 14 次请求（2+14=16），台账连续计数。

## 场景三：删掉最后阶段产物 → sha256 发现 → 从检查点恢复

```bash
rm examples/run_resumed/work/{decisions,diagnostics,fill_notes,final_check}.json
python3 scripts/checkpoint.py --work examples/run_resumed/work verify
# exit=3：decide/diagnose/fill/final_check 报"缺失"，续跑将从最早的问题阶段开始
python3 scripts/checkpoint.py --work examples/run_resumed/work resume-point   # 输出 decide
python3 scripts/simulate_stages.py --case examples/case.json --root examples/run_resumed --resume
# exit=0：从 decide 起重做，verify 恢复 8 阶段全 OK
python3 scripts/checkpoint.py --work examples/run_resumed/work verify         # exit=0
```

恢复后 `run_resumed/output/result.json`：`status=completed`，
`scheduler.ledger.spent_requests=30`——重跑消耗的 14 次请求**如实累计**，
不掩饰恢复成本。

## 场景四：预算收紧时的预选降级（计划探针，产物在 /tmp 不落盘于本目录）

```bash
python3 scripts/plan_run.py --case examples/case.json --work /tmp/brg_probe16 --budget-requests 16
# exit=0 → 档位=L1 预估请求=10/16（诊断收缩到 1/3 子集）
python3 scripts/plan_run.py --case examples/case.json --work /tmp/brg_probe10 --budget-requests 10
# exit=0 → 档位=L2 预估请求=7/10（仅核心判定+骨架证据）
python3 scripts/simulate_stages.py --case examples/case.json --root /tmp/brg_l2 --budget-requests 10
# exit=0 → status=completed，decisions 的 evidence_level=skeleton，
#         uncertainty 含"本次运行处于降级档位 L2……缩减的范围不得以任何形式声称已完成。"
```

## 场景五：运行中降级信号（台账实测）

```bash
python3 scripts/budget_ledger.py --work /tmp/brg_sig init --budget-requests 16 --reserve 2
python3 scripts/budget_ledger.py --work /tmp/brg_sig charge --stage decide --requests 10 --seconds 120
# → 剩余 5（预留 2），信号=ok
python3 scripts/budget_ledger.py --work /tmp/brg_sig charge --stage diagnose --requests 3 --seconds 40
# → 剩余 2 ≤ reserve，信号=critical：
#   "立即降至 L3：停止一切非必要模型调用，仅用预留请求完成 fill 与 final_check，以最小诚实 partial 落盘。"
python3 scripts/budget_ledger.py --work /tmp/brg_sig init     # exit=2：拒绝误重置台账
```

## 幂等性

对 `run_full` 连续两次全新运行，result.json 除时间戳外逐字节一致
（`selftest_log.md` 第 9 步：`idempotent: True`）。
