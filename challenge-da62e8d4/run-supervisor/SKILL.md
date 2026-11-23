---
name: run-supervisor
description: >-
  过程质量控制监督器，用于论文复现/方法验证类任务：当案例需要分阶段实际运行候选代码、
  核对指标，并在有限时间预算（约900秒/64次请求）内交付诚实的结构化 result.json 时触发。
  核心是状态机检查点与增量落盘，保证任何时候中断都留有合法的部分结果；候选失败/超时记为
  证据而非中断；finalize 从过程证据重算总状态并做合约 lint，杜绝漏阶段、缺字段、
  结果与过程证据矛盾。
---

# run-supervisor：复现任务的过程质量控制监督器

## 用途与适用条件

适用于「论文复现与方法验证」类评测案例：输入给一篇真实论文 PDF、两份候选数值
方法代码，要求**实际运行**候选、核对指标、做差异归因，并交付符合
output_contract 的 result.json。本子场景为「参数/代码/指标验算与差异归因」。

本 Skill 的重心**只是过程质量控制**：900 秒预算下复现任务的典型失败不是科学
判断错，而是过程失控——跑到一半超时什么都没留下、某个候选崩了被默默跳过、
阶段漏做、result.json 缺字段或与过程证据矛盾、重复执行覆盖了好结果。容差设
定、指标比对、差异归因等科学判断由你（agent）完成，监督器不做裁决。

不适用：纯文献综述、无需运行代码的任务、无结构化输出合约的任务。

## 背景：评测契约（必须遵守）

- Skill 安装于 `/skills/weekly-skill`，由官方 DeepSeek Harness 跑 3 个固定案例。
- 每案例输入在 `/input/case.json` 与 `/input/task.md`；case.json 含 `case_id`
  与 `output_contract` 字段清单。材料按题目提供：真实 PDF 论文、两份候选数值
  方法代码；**原始数据/作者仓库缺失是预期情况**，必须显式登记而非假装存在。
- 工作在 `/app/work`，最终产物在 `/app/output`，必须含 `result.json`：含
  `case_id` 与 output_contract **全部字段**、诚实的
  `status: success/partial/unable/refused`、来源定位、不确定性、变更记录。
- 预算约 **64 次模型请求 / 900 秒**；平台要求「尽早保存诚实部分结果并增量改进」。
- 组织方合成代码 ≠ 作者原代码；**合成数据上的指标通过不能写成论文数值复现**。
- 禁止编造数据。缺失就登记缺失，`partial`/`unable` 永远好过伪造的 `success`。

## 核心思想

1. **状态机 + 检查点 + 增量落盘**：六阶段
   `inventory → targets → tolerances → run → compare → conclude`，每阶段完成
   必须登记真实存在的证据文件路径；每次登记/运行都原子地重写 result.json，
   因此**任何时刻被打断，磁盘上的 result.json 都是合法且诚实的**。
2. **失败是证据，不是中断**：候选崩溃、超时、无法启动，一律写入
   `runs/<name>/meta.json` 与 runs 索引，流程继续下一个候选。绝不允许"A 崩了
   所以 B 没跑"。
3. **finalize 重算，不信任记忆**：最终 status 只从 `state.json` 的阶段记录与
   `runs/` 的证据文件重新计算，再做合约 lint（case_id 匹配、全字段非占位、
   变更记录齐全），lint FAIL 退出码 1，PASS 前任务不算结束。
4. **预算台账**：每次 status 报告已用/剩余墙钟；预算过半强制提醒"先保存部分
   结果"。

## 铁律（不可违反）

1. **result.json 始终合法**：从 init 起每一刻磁盘上的 result.json 都能被 JSON
   解析，含 case_id 与全部合约字段（未完成时为占位 null），status 诚实。
2. **每个声明都有证据文件**：阶段登记必须附真实存在的文件；结论里的每个指标
   必须能指到 `runs/<name>/stdout.txt` 或你写的分析笔记。
3. **一个候选失败不跳过另一个**：失败记为证据，继续运行其余候选。
4. **预算过半停止新实验**：先填写已得到的诚实结论并 finalize 保底，再增量改进。
5. **finalize PASS 前不结束**：lint 不过就修复问题重新 finalize。

## 命令流程（`$SKILL` 指代技能目录，如 /skills/weekly-skill）

监督器为纯标准库 Python3 脚本，五个子命令覆盖全周期。

### 1) init —— 建立状态机与合法骨架（拿到案例后第一件事）

```bash
python3 $SKILL/scripts/supervisor.py init \
  --case /input/case.json --work /app/work --output /app/output \
  [--budget-seconds 900] [--force]
```

- 解析 case_id 与 output_contract（兼容 list/dict 两种写法）；
- 写 `/app/work/state.json`（六阶段 pending、起始时间戳、预算）；
- 写 `/app/output/result.json` 骨架：全合约字段 null、`status=partial`、
  change_records 含 init 条目。**从这一刻起中断也有合法部分结果**。
- 已存在 state.json 时不覆盖并提示（幂等），除非 `--force`。

### 2) phase —— 登记阶段检查点（每完成一个阶段做一次）

```bash
python3 $SKILL/scripts/supervisor.py phase --work /app/work \
  --name inventory --status done \
  --evidence /app/work/notes/inventory.md [--note "说明"]
```

- 阶段名限六个之一；状态限 `done|failed|skipped`；`--evidence` 可重复。
- 证据文件必须真实存在，否则**拒绝登记**；done 至少一个证据，failed/skipped
  至少一个证据或一条 --note。
- 重复登记打印 WARN 并写 `phase-duplicate` 变更记录（防静默改史）。
- 登记后 state.json 与 result.json 的阶段记录同步更新。

### 3) run —— 带超时的受控运行（每个候选一次或多次）

```bash
python3 $SKILL/scripts/supervisor.py run --work /app/work \
  --name candidate_a --timeout 300 -- python3 /input/candidate_a.py --arg v
```

- 独立日志目录 `/app/work/runs/candidate_a/`：`stdout.txt`、`stderr.txt`、
  `meta.json`（退出码、墙钟、timeout 标记、命令行、起止时间）。
- 候选失败/超时/无法启动都写入 runs 索引并记 change_records，**run 子命令自身
  仍退出 0**——失败是证据，脚本可以安全地继续跑下一个候选。
- 同名复跑会 WARN 并记 `run-rerun`（防覆盖好结果）；要保留多次尝试请换名。
- `--timeout` 是硬超时：超时进程被终止并标记 `timeout=true`。

### 4) status —— 预算台账与下一动作（随时可查，建议每阶段后查一次）

```bash
python3 $SKILL/scripts/supervisor.py status --work /app/work [--json]
```

- 打印各阶段状态、已用/剩余预算、运行摘要、下一建议动作；
- **预算过半时输出"先保存部分结果"提醒**（此时应停止新实验，先填结论保底）；
- `--json` 输出机器可读报告。

### 5) finalize —— 重算总状态 + 合约 lint（交付前最后一步，可反复跑）

```bash
python3 $SKILL/scripts/supervisor.py finalize \
  --case /input/case.json --work /app/work --output /app/output
```

- 从 state.json + runs 证据**重算** status：
  - 核心阶段（inventory/targets/run）全部未 done → `unable`
  - 六阶段全 done 且无任何失败（阶段 failed/skipped、候选失败/超时）→ `success`
  - 其余 → `partial`
- 汇总 uncertainty（失败/跳过/未完成阶段、失败/超时候选各一条诚实声明），
  追加 finalize 变更记录，写回 result.json；
- 合约 lint：case_id 一致；output_contract 全字段存在且非 null；空值
  （`""`/`[]`/`{}`）必须在 `field_notes` 中有非空说明；change_records 非空。
- **lint FAIL 打印缺失清单、退出码 1**（result.json 仍按重算状态落盘，修复后
  重跑即可）；PASS 退出码 0。

### 典型时序

```
init → phase inventory done → phase targets done → phase tolerances done
     → run candidate_a → run candidate_b（即使 a 崩了也照跑）
     → phase run done → status（查预算）
     → 填 result.json 合约字段（agent 的科学结论 + field_notes）
     → phase compare done → phase conclude done → finalize（PASS 才结束）
```

## 输入输出

**输入**：

| 路径 | 说明 |
|---|---|
| `/input/case.json` | case_id + output_contract 字段清单（init 必需） |
| `/input/task.md` | 题目描述（agent 阅读，监督器不解析） |
| `/input/*.pdf`、`/input/*.py` 等 | 论文与候选代码（按题目提供） |

**输出**：

| 路径 | 说明 |
|---|---|
| `/app/output/result.json` | 最终交付物：case_id、output_contract 全字段、诚实 status、sources（来源定位）、uncertainty、change_records、phases、runs、field_notes |
| `/app/work/state.json` | 状态机：六阶段状态/时间戳/证据、runs 索引、预算、变更记录 |
| `/app/work/runs/<name>/` | 每候选 stdout.txt / stderr.txt / meta.json |
| `/app/work/notes/`（建议） | agent 写的各阶段分析笔记，作为 phase 证据 |

result.json 中由监督器维护的记账键：`case_id, status, generated_by, sources,
uncertainty, change_records, phases, runs, field_notes`；合约字段与其平级，
由 agent 填写内容。空占位规则：字段实在无内容可填时，填空值并在
`field_notes.<字段>` 写明原因（如"作者仓库缺失，无法获取原始数据"），
否则 finalize lint 判 FAIL。

## 异常处理表

| 异常 | 监督器行为 | 退出码 |
|---|---|---|
| case.json 缺 case_id / output_contract / 为空 / 字段重复 | init 即报错，指出具体问题 | 2 |
| 重复 init | 不覆盖，提示用 --force，状态保留 | 0 |
| phase 证据文件不存在 | 拒绝登记，指明缺失路径 | 2 |
| phase 阶段名/状态非法、done 无证据 | 拒绝并提示合法值 | 2 |
| 阶段重复登记 | stderr 警告 + change_records 记 phase-duplicate，允许覆盖 | 0 |
| 候选崩溃（exit≠0） | 记 meta.json + runs 索引 + change_records，流程继续 | 0 |
| 候选超时 | 杀进程，meta.json 标 timeout=true，stderr 追加说明，流程继续 | 0 |
| 命令无法启动（OSError） | exit_code=127 记为证据 | 0 |
| 同名候选复跑 | 警告 + run-rerun 变更记录，日志覆盖 | 0 |
| 阶段漏做（pending） | finalize 重算时降级（unable/partial）并列入 uncertainty | 视 lint |
| 合约字段为 null / 空值无 field_notes / case_id 不符 / change_records 空 | finalize lint FAIL，打印缺失清单 | 1 |
| finalize 的 --output 与 init 时不一致 | 警告后继续（防止产物写错目录而不自知） | 视 lint |

## 运行契约（与平台对齐）

- 输入只读 `/input`，过程文件全部落 `/app/work`，交付物落 `/app/output`。
- `/app/output/result.json` 是**唯一交付物**，但每个结论必须能回溯到
  `/app/work` 下的证据文件（runs 日志、笔记）。
- 诚实 partial：两份候选只跑通一份、原始数据缺失、指标与论文不一致——这些
  都如实写入 status/uncertainty/data_gaps/field_notes，**partial 是合格答卷，
  伪造 success 不是**。
- 先保存再改进：init 后任何时刻 result.json 都合法；预算过半先 finalize 保底。

## 最小合成示例

`examples/` 提供完整可跑的合成演示（**synthetic，非正式案例结果**）：

```bash
bash $SKILL/examples/run_example.sh /tmp/run-supervisor-demo
```

流程：init → 三个阶段登记（证据为 notes/*.md）→ run 两个候选
（`method_ok.py` 退出 0 打印指标；`method_fail.py` 退出 1 写 stderr）
→ 中间时刻自检 result.json 合法 → status → 填写五个合约字段 →
compare/conclude 登记 → finalize。预期：**method_fail 被记录且流程继续，
finalize 判定 partial 且 lint PASS（退出码 0）**。预期产物副本见
`examples/expected/`（时间戳/路径以实际运行为准）。

## 限制与自查

**限制**：

- 监督器只管过程完整性与诚实性，**不做**科学判断：容差合理性、归因正确性、
  指标可比性由 agent 负责，写进笔记与合约字段。
- 预算台账只统计墙钟（自 init 起），不统计模型请求数；64 次请求预算需 agent
  自行节制（少闲聊、多批量）。
- 同名 run 复跑会覆盖旧日志（有警告与记录）；要多次采样请用不同候选名。
- 状态存于 work 目录单机的 state.json，不支持并发写同一 work 目录。
- 仅标准库 Python3，UTF-8 文本，无网络、无第三方依赖。

**交付前自查清单**：

1. `status --work /app/work`：六阶段无意外 pending？预算是否过半（过半则应已保底）？
2. 每个候选都有 `runs/<name>/meta.json`？失败的候选是否在 result.json 的
   uncertainty/结论文本中被如实提及？
3. 合约字段全填了？空值都有 field_notes 说明？
4. 结论文本是否避免把"合成代码在合成数据上通过"写成"论文数值复现"？
5. `finalize` 退出码为 0？（PASS 前不算完成）
6. 缺失的原始数据/作者仓库是否已显式登记（如 data_gaps）？

过程规则细节见 `references/process_control.md`（状态机图、证据标准、
失败分类映射、幂等规则、900 秒预算分配表）。
