# 过程质量控制参考（process control reference）

本文件是 run-supervisor 的过程规则手册。监督器只保证**过程完整性与诚实性**；
容差设定、差异归因、候选比较等科学判断一律由 agent 完成。

## 1. 状态机（文本图）

```
                 init
                   │
                   ▼
        ┌──────────────────────┐
        │  六阶段均为 pending   │  result.json 从这一刻起始终合法
        └──────────────────────┘
                   │
   inventory ──▶ targets ──▶ tolerances ──▶ run ──▶ compare ──▶ conclude
   （材料盘点）  （目标指标）  （容差判据）   （受控运行） （比对归因） （结论落盘）
     │             │            │             │           │           │
     ▼             ▼            ▼             ▼           ▼           ▼
  每阶段登记为 done / failed / skipped，必须附真实存在的证据文件（done 强制）
                   │
                   ▼
               finalize：从证据重算总状态 + 合约 lint（FAIL 退出码 1）

  run 阶段内部（可多次执行，候选间相互独立）：
     run --name A ──▶ runs/A/{stdout,stderr,meta}.json
     run --name B ──▶ runs/B/{...}        （A 崩溃/超时不影响 B）
```

阶段原则上按序推进，但监督器不强制顺序（例如材料缺失时可先把 targets 记为
failed 再继续）；**顺序灵活性不等于可漏做**——finalize 会把 pending 阶段列入
uncertainty 并在重算中反映。

## 2. 各阶段最低证据标准

| 阶段 | 目的 | 最低证据（登记 done 的必要条件） |
|---|---|---|
| inventory | 盘点输入材料 | 材料清单笔记（含 PDF 文件名、候选代码清单、缺失项显式登记） |
| targets | 明确验算目标 | 目标指标表笔记（指标名、论文目标值、出处页码/表号） |
| tolerances | 设定判据 | 容差判据笔记（每个指标的容差与理由） |
| run | 实际运行候选 | 每个候选的 `runs/<name>/meta.json`（由 run 子命令自动生成） |
| compare | 比对与归因 | 比对笔记（目标值 vs 实测值、差异、初步归因） |
| conclude | 结论落盘 | 填写完毕的 result.json（全部合约字段非占位） |

skipped 仅用于"材料缺失导致该阶段客观无法执行"（如作者仓库缺失导致无法跑
作者基线），必须附 --note 说明；failed 用于"执行了但未达成"。两者都会使总
状态降为 partial，这比伪造 done 诚实得多。

## 3. 失败分类与 status 映射

| 失败类别 | 例子 | 过程处理 | 对总状态的贡献 |
|---|---|---|---|
| 执行失败 | 候选崩溃 exit≠0、运行超时 | run 子命令记录 meta（exit_code/timeout），流程继续 | 有失败 → 封顶 partial |
| 信息缺失 | 原始数据/作者仓库缺失 | inventory 中显式登记，对应阶段 failed/skipped + data_gaps | 有 failed/skipped → partial；核心阶段全缺 → unable |
| 数值不一致 | 实测指标超容差 | agent 在 compare 归因、在合约字段声明 | 阶段仍可 done；不一致写入 uncertainty 与结论文本 |

finalize 重算规则（不信任记忆，只信 state.json + runs 证据）：

- 核心阶段（inventory / targets / run）**全部未 done** → `unable`
- 六阶段全 `done` 且无阶段 failed/skipped、无候选失败/超时 → `success`
- 其余（有 done 也有 failed/skipped，或任一候选失败/超时） → `partial`
- `refused` 由 agent 在遇到违规请求时人工写入，监督器不自动产生

注意：组织方合成代码 ≠ 作者原代码。即使六阶段全 done 得到 success，
也必须在 reproducibility_verdict 中写明"合成数据上的指标核对通过，
不构成论文数值复现"。

## 4. 幂等与变更记录规则

- **重复 init**：已存在 state.json 时不覆盖、不报错（退出码 0 并提示）；
  确需重建用 `--force`。
- **重复 phase 登记**：打印 WARN 到 stderr、向 change_records 追加
  `phase-duplicate` 条目后覆盖——防止静默改史，全程可追溯。
- **重复 run 同名候选**：WARN + `run-rerun` 变更记录，旧日志被覆盖；
  想保留多次尝试请用不同候选名（如 `methodA_seed1`）。
- **证据文件必须真实存在**：相对路径先相对 work 解析，再相对 cwd；
  不存在则拒绝登记（退出码 2）。done 状态至少一个证据文件。
- **change_records 只增不改**：init、每次 phase、每次 run、finalize 各留
  一条带时间戳的记录；finalize 的合约 lint 要求 change_records 非空。

## 5. result.json 合约 lint 规则（finalize 执行）

1. `case_id` 必须与 case.json 完全一致；
2. `output_contract` 每个字段必须**存在且非 null**；
3. 字段值允许为空占位（`""` / `[]` / `{}`），但**必须**在 `field_notes` 中
   有该字段的非空说明（例：`field_notes.metric_table = "原始数据缺失，
   无指标可报，详见 uncertainty"`）——空值不解释即 FAIL；
4. `change_records` 非空。
lint FAIL 打印完整问题清单并退出码 1；result.json 仍会按重算状态落盘，
修复后重新 finalize 即可（幂等）。

## 6. 预算分配建议（900 秒基准）

| 阶段 | 建议占比 | 秒数（约） | 说明 |
|---|---|---|---|
| inventory | 10% | 90 | 读 case.json/task.md/PDF，列材料与缺失项 |
| targets | 10% | 90 | 从论文摘目标指标与出处 |
| tolerances | 5% | 45 | 定容差，写清理由 |
| run | 45% | 405 | 大头留给受控运行；单候选 timeout 建议 ≤ 剩余预算的 1/3 |
| compare | 15% | 135 | 比对、归因、写笔记 |
| conclude | 15% | 135 | 填合约字段、field_notes、finalize 与返修余量 |

护栏：**预算过半（status 显示 over_half）即停止开展新实验**，先把已得到的
诚实结论填进 result.json 并跑一次 finalize 保底，再用剩余时间增量改进。
run 子命令自带硬超时，候选失控不会吃掉全部预算。
