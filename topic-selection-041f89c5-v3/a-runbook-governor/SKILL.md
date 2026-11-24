---
name: runbook-governor
description: 运行可靠性工程取向的科研选题评估技能。当任务是在 /input 给定 case.json（含 case_id 与 output_contract）、task.md 与科研材料，要求完成文献综述、选题或创新性评估，并在 /app/output 交付结构化 result.json，且运行受模型请求数与秒级时间双预算约束时使用。核心立场：交付的第一风险是"跑到一半被掐断，什么都没留下"——本技能用 scripts/runbook.py 把执行变成受治理的状态机：init 立即锁定 case_id 并写出契约合法的 result.json 骨架，阶段进出留痕，预算按 L0/L1/L2 三级降级，危急时 triage 强制产出合法 partial，finalize 机检后才算交付。不适用：无输出契约、无预算约束的离线自由写作。
---

# runbook-governor：先保住"任何时刻都有合法结果"，再追求内容深度

## 核心主张

定时定预算的评测运行里，最常见的零分模式不是内容平庸，而是**中断时 /app/output 为空或契约非法**：Agent 把 result.json 留到最后一步写，预算一耗尽就前功尽弃。本技能倒置优先级：**第 1 分钟就写出契约合法的 result.json 骨架，此后每个阶段只回填、不重构**；预算台账驱动三级降级，宁可主动交一份诚实的 partial，也不被动留下一堆半成品草稿。内容质量决定分数上限，运行治理决定分数下限。

## 运行时契约（必须先读）

1. 输入在 `/input`：`task.md`、`case.json`（含 `case_id`、`output_contract`）、材料文件（PDF/TXT/JSON/CSV）。**逐文件读真实内容**，不依据文件名或标签猜测；PDF 用运行环境实际可用的解析工具从原始 PDF 提取，不假设有预提取文本层。
2. 若存在 `/input/environment/resources.yaml`，先读它确认可用工具与预算。
3. 中间产物写入 `/app/work`，最终交付写入 `/app/output`。
4. `/app/output/result.json` 必须含 `case_id`（与 case.json 逐字一致）与 `output_contract` 声明的**全部原始字段**，字段名逐字照抄，不增删改名。
5. 预算：约 64 次模型请求、900 秒、单次响应 16384 token。
6. 诚实状态：`status` 只能是 `success` / `partial` / `failed`；材料缺失、无法判定、运行失败分别说明；partial 写明缺什么、为什么。
7. 禁止伪造：检索不到写检索不到并给出检索范围；不依据错误的领域标签补造数据。

## 六阶段工作流（每个边界都过 runbook）

所有命令中 `$S=/app/work/run_state.json`，脚本路径 `/skills/weekly-skill/scripts/runbook.py`。

### 阶段 intake（最先做，最先保住下限）

```
python3 /skills/weekly-skill/scripts/runbook.py --state $S init \
    --case /input/case.json --output /app/output --requests 64 --seconds 900
python3 /skills/weekly-skill/scripts/runbook.py --state $S enter --phase intake
```

1. `ls -laR /input`，登记全部材料到 `/app/work/inventory.md`（名称、字节、格式、可解析性）。
2. 逐句读 `task.md`，把交付要求摘成清单 `/app/work/deliverables.md`。
3. result.json 骨架已由 init 写出——**此刻即使中断，交付也是合法的**。

`exit --phase intake --note "..."` 后 `tick --n <本阶段模型请求数>`。

### 阶段 question：研究问题结构化

拆出研究对象、关键变量、比较基线、预期结论方向、可证伪条件，写 `/app/work/question_frame.md`；task.md 未给的要素标 `未指定`，不脑补。退出时 `checkpoint` 一次。

### 阶段 retrieve：检索与筛选留痕

- 证据第一来源 = `/input` 文献集；若环境确有联网检索且任务允许，登记完整检索式与时间窗。
- 每条候选记录判 纳入/排除/待定，排除写明理由，记 `/app/work/screening_log.md`。
- **覆盖边界声明**写入 `/app/work/coverage_boundary.md`：综述结论只在这个边界内成立；"未见相关研究"永远说成"在上述边界内未见"。

### 阶段 extract：证据提取

每篇纳入文献提取可比较字段（任务、方法、数据、指标、结论、局限）入 `/app/work/evidence_table.md`；每条证据带定位（文件名+页/段）。提取到一半预算告警时，优先保核心文献，其余标"未提取"并在不确定性中说明。

### 阶段 synthesize：四项交付

在 `/app/work/synthesis.md` 完成：已有工作比较（含不可比对象及原因）、创新点识别（逐条判 已被覆盖/部分覆盖/未见覆盖/无法判定，"未见覆盖"同句写检索边界）、可行性判断（每条前提标 `[来源]` 或 `[假设]`）、研究空白与不确定性（冲突证据双方均列出）。**每次模型调用后 `tick`**；每完成一项交付 `checkpoint` 一次。

### 阶段 closeout：回填与终检

1. 结论逐字段回填 `/app/output/result.json`；证据表、筛选日志、边界声明复制到 `/app/output` 作可复核附件。
2. `checkpoint` 终检通过后：

```
python3 /skills/weekly-skill/scripts/runbook.py --state $S finalize --status success
# 或：finalize --status partial --reason "缺什么、为什么"
```

3. 把 `run_state.json` 复制到 `/app/output/run_state.json`——它是本次运行的完整审计轨迹（阶段耗时、预算消耗、快照清单）。

## 预算治理（本技能核心）

每完成一个模型调用回合就 `tick`，每个阶段边界都 `status`：

- **L0（用量比 <0.6）**：正常运行。
- **L1（0.6–0.8）**：停止新增检索与新方向探索；用已收集证据直接综合；砍掉所有"锦上添花"步骤。
- **L2（≥0.8 或剩余 <120 秒）**：立即停止分析，执行 `triage`（强制合法 partial），然后 `finalize --status partial --reason ...`。

降级判定细节与阶段定义见 `references/runbook_protocol.md`；状态文件结构见 `references/state_format.md`。

## 异常处理

| 情形 | 处置 |
|-|-|
| checkpoint 报缺字段 | 立即回填该字段（哪怕先置 null + 不确定性说明），不带着非法 result.json 继续跑 |
| case_id 不一致 | 停止一切回填，以 case.json 为准逐字修正 |
| 材料不可解析 | 换工具重试一次；仍失败登记 `unreadable`，相关结论降级 partial 并说明 |
| 文献集为空 | `triage` 后 `finalize --status partial --reason "输入文献集为空"`；问题结构化与协议照常交付 |
| 预算到 L2 | 见上；不允许"再试一次说不定来得及" |
| finalize 校验失败 | 按错误清单逐条修复后重跑 finalize；禁止绕过校验直接交付 |

## 红线

- 不许在未 `init` 写骨架前做任何分析；不许"最后再统一写 result.json"；不许隐藏预算消耗（tick 必须诚实自报）；不许在 L2 级别继续开新分析线程；不许把 partial 包装成 success。

## 最小示例

`examples/` 内有**合成示例**：虚构案例 `SYNTH-RUNBOOK-001`（5 字段契约）的一次完整受治理运行，含一次故意触发的预算危急（L2 → triage → partial）。命令序列与预期输出见 `examples/minimal_example.md`，实跑产物在 `examples/output/`。
