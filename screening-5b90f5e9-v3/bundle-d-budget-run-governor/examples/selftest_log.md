# 自测日志（selftest_log）

> 全部命令于 2026-11-25 在 macOS（darwin arm64）+ Python 3 标准库环境真实执行。
> 工作目录除注明外均为 bundle 根目录 `bundle-d-budget-run-governor/`。
> 长输出仅摘录关键行；完整现场保留在 `examples/run_full/` 与 `examples/run_resumed/`。

## 1. plan_run.py 单测（正常 + 非法输入）

```
$ python3 scripts/plan_run.py --case examples/case.json --work /tmp/brg_t1_work
[plan_run] N=9 batch=3 档位=L0 预估请求=16/64 预估秒数=232/900
[plan_run] 风险点: 输入含组织方标注的夹具记录……共 2 条……
exit=0

$ python3 scripts/plan_run.py --case /nonexistent.json --work /tmp/brg_x
[plan_run] 错误：case.json 不存在: /nonexistent.json
exit=2
```

## 2. budget_ledger.py 单测（init / charge / status / 信号 / 防误重置）

```
$ python3 scripts/budget_ledger.py --work /tmp/brg_t1_work init --budget-requests 64 --budget-seconds 900 --reserve 2
exit=0
$ python3 scripts/budget_ledger.py --work /tmp/brg_t1_work charge --stage decide --requests 3 --seconds 41.0
[ledger] …已用 3/64，剩余 61（预留 2），信号=ok        exit=0
$ python3 scripts/budget_ledger.py --work /tmp/brg_t1_work status
…"spent_requests": 3, "remaining_requests": 61, "signal": "ok"…   exit=0

# 降级信号实测（预算 16）：
charge scaffold 1 次  → 剩余 15，信号=ok                 exit=0
charge decide  10 次  → 剩余 5，信号=ok                  exit=0
charge diagnose 3 次  → 剩余 2 ≤ reserve，信号=critical
[ledger] 降级信号 critical：立即降至 L3……以最小诚实 partial 落盘。   exit=0

$ python3 scripts/budget_ledger.py --work /tmp/brg_sig init   # 不加 --force
[ledger] 错误：台账已存在……断点续跑时切勿重置台账……           exit=2
```

## 3. 场景一：完整运行（simulate_stages.py 端到端）

```
$ python3 scripts/simulate_stages.py --case examples/case.json --root examples/run_full
== 1/4 plan == 档位=L0 预估请求=16/64
== 2/4 ledger init ==  == 3/4 resume-point ==  == 4/4 逐阶段 ==
inventory(0)→scaffold(1)→normalize(0)→dedupe(1)→decide(3)→diagnose(9)→fill(1)→final_check(1)
每阶段均真实执行 charge → checkpoint record → flush_partial
[flush] 已落盘 examples/run_full/output/result.json（status=completed, level=L0, 已完成阶段=8/8）
台账终态：spent=16, remaining=48, reserve=2, elapsed=232.0s/900, signal=ok
exit=0
```

## 4. 场景一产物目检（run_full/output/result.json）

- status=completed；合同 9 字段全部在位；
- decisions 8 条（R05 重复导出已并入 R01，不重复判定），R04=uncertain；
- dedup_report 含 duplicate_clusters(R01←R05) 与 conflict_flags(R04 双人冲突→留待人工复核)；
- change_records 含 merge_duplicate_export 1 条；uncertainty 如实列出 R04 待复核；
- scheduler.ledger.spent_requests=16，reserve=2 未动用。结论：与预期一致，无伪造完成项。

## 5. 场景二：模拟崩溃（--fail-at decide）

```
$ python3 scripts/simulate_stages.py --case examples/case.json --root examples/run_resumed --fail-at decide
…4 阶段完成后：
!! [simulate] 模拟崩溃：在阶段 decide 前中断（exit 3）。现场已保留在 examples/run_resumed/work
exit=3
```

崩溃瞬间目检 result.json：status=in_progress；decisions=null；
uncertainty=["decisions 尚未生成：判定阶段未完成……","字段 decisions 为 null：decide 阶段尚未完成。"]；
completed_stages=[inventory,scaffold,normalize,dedupe]；spent=2。结论：诚实 partial，合法交付。

## 6. 场景二：检查点定位与续跑

```
$ python3 scripts/checkpoint.py --work examples/run_resumed/work verify
inventory/scaffold/normalize/dedupe 全部 OK；全部 4 个阶段产物完好。   exit=0
$ python3 scripts/checkpoint.py --work examples/run_resumed/work resume-point
decide                                                                 exit=0
$ python3 scripts/simulate_stages.py --case examples/case.json --root examples/run_resumed --resume
[simulate] 续跑模式：保留既有台账，已消耗预算继续计数。
[simulate] 续跑起点：decide（已完成阶段跳过）
…仅执行 decide→diagnose→fill→final_check…
[flush] …status=completed…                                              exit=0
```

目检：result.json status=completed，spent=16（2+14 连续计数，完成阶段未重跑）。

## 7. 场景三：删最后阶段产物 → sha256 发现 → 恢复

```
$ rm examples/run_resumed/work/{decisions,diagnostics,fill_notes,final_check}.json
$ python3 scripts/checkpoint.py --work examples/run_resumed/work verify
decide/diagnose/fill/final_check 报"缺失: …"；4 个阶段校验不通过        exit=3
$ python3 scripts/checkpoint.py --work examples/run_resumed/work resume-point
decide                                                                 exit=0
$ python3 scripts/simulate_stages.py --case examples/case.json --root examples/run_resumed --resume
续跑起点：decide；重跑 4 个阶段                                        exit=0
$ python3 scripts/checkpoint.py --work examples/run_resumed/work verify
全部 8 个阶段产物完好。                                                exit=0
```

目检：result.json status=completed，spent=30（16+14 重跑成本如实累计）。

## 8. 场景四/五：预选降级探针与 L2 端到端（产物在 /tmp）

```
$ python3 scripts/plan_run.py --case examples/case.json --work /tmp/brg_probe16 --budget-requests 16
档位=L1 预估请求=10/16   exit=0
$ python3 scripts/plan_run.py --case examples/case.json --work /tmp/brg_probe10 --budget-requests 10
档位=L2 预估请求=7/10    exit=0
$ python3 scripts/simulate_stages.py --case examples/case.json --root /tmp/brg_l2 --budget-requests 10
exit=0；status=completed；decisions[].evidence_level=skeleton；spent=7/10；
uncertainty 含"本次运行处于降级档位 L2……缩减的范围不得以任何形式声称已完成。"
```

## 9. 幂等性

```
对 examples/run_full 连续两次全新运行，result.json 除时间戳字段外逐字段相等：
idempotent (除时间戳外完全一致): True                                   两次均 exit=0
```

## 10. 平台约束自查（selfcheck.py）

```
$ python3 scripts/selfcheck.py
[selfcheck] 文件数: 41 / 50；总大小: 129589 / 2097152 字节
[selfcheck] frontmatter: name='budget-run-governor', description 长度=353
[selfcheck] 结果: PASS                                                exit=0
```

## 退出码汇总

| 步骤 | 命令（缩写） | exit |
|---|---|---|
| 1 | plan_run 正常 | 0 |
| 1 | plan_run 输入缺失 | 2 |
| 2 | ledger init / charge / status | 0 |
| 2 | ledger 无 --force 重复 init | 2 |
| 3 | simulate 完整运行 | 0 |
| 5 | simulate --fail-at decide（模拟崩溃） | 3 |
| 6 | checkpoint verify（崩溃现场） | 0 |
| 6 | checkpoint resume-point | 0 |
| 6 | simulate --resume | 0 |
| 7 | checkpoint verify（删产物后） | 3 |
| 7 | simulate --resume（恢复） | 0 |
| 7 | checkpoint verify（恢复后） | 0 |
| 8 | plan_run 预算 16 / 10（预选 L1/L2） | 0 |
| 8 | simulate L2 端到端 | 0 |
| 9 | simulate 重跑（幂等） | 0 |
| 10 | selfcheck | 0 |
