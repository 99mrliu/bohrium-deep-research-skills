---
name: exp-schedule-forge
description: 排期与预约可行性工程。当 case.json 含 resource_contract（设备 booking：window_days/slots_per_week/slot_hours）、deadline_days 与候选方案的 est_days 时使用：把方案步骤编译成带资源约束的逐周日程，机械判定"N 天排不排得下"，定位瓶颈设备并给出可报价的排期表、甘特图与按周累计现金流；est_days 拍脑袋、设备预约吞吐不足、超期修复是本 skill 的重心。
---

# exp-schedule-forge：排期与预约可行性工程

## 1. 用途与新增价值
候选方案的 `est_days` 经常是拍脑袋。真实可行性由三件事共同决定：
1. **预约吞吐**：每台设备每周可用机时 = `slots_per_week × slot_hours`，窗口总机时 = 每周机时 × `floor(window_days/7)`；
2. **工序先后/并行**：依赖关系决定步骤能否在同一周插 slot；
3. **deadline_days**：瓶颈设备的串行工期是否超期。

本 skill 用脚本机械完成：throughput 体检（机时需求 vs 可用机时，带算式）→ schedule 排程（逐周 slot 分配 + 甘特图 + 现金流）→ repair（超期修复选项表）。est_days 是否可信、哪台设备是瓶颈、超期几天、怎么修，全部由脚本给出可复核的数字，而不是模型目测。

## 2. 适用条件与不适用情况
**适用**：case.json 含 `resource_contract.equipment[].booking`、`deadline_days`、`candidate_plans[].est_days`；或用户给出含步骤表的 plan.json。
**不适用**：
- 无 booking 信息且无法从 `equipment_domain_note` 解析出设备 → 只能做成本核算，时间维度 honest partial；
- 步骤机时完全未知且无 cost_items 可反推 → 不得编造机时，进 `confirmation_items`；
- 亚日级（小时级）精细排产：本 skill 粒度为"周 × slot"，不做日内时刻表。

## 3. 运行时契约与路径
- 输入：`/input/case.json`（必选）、`/input/task.md`（可选）；用户修订方案放 `/app/work/plan.json`。
- 工作目录：`/app/work`；交付：`/app/output`（result.json、plan.json、plan.md、throughput.json/md、schedule.json、gantt.md、cashflow.md、repair 产物）。
- 脚本：`/skills/weekly-skill/scripts/schedule_forge.py`，仅 Python 3 标准库，确定性，缺键不崩（exit 0 + partial 报告），单次运行 <5 秒。

## 4. 工作流（编号步骤，命令可直接复制）

**步骤 0：读 case。** 读 `/input/case.json`，记录 `deadline_days`、`budget_cap`、`equipment_domain_note`（内嵌设备由脚本解析合并，勿肉眼抄）。

**步骤 1：throughput 体检 3 个候选。** 机械判断每个候选 est_days 是否可信、瓶颈设备、超期天数：
```bash
python3 /skills/weekly-skill/scripts/schedule_forge.py throughput \
  --case /input/case.json --outdir /app/work
```
读 `/app/work/throughput.json`：`candidate_assessments[].est_days_verdict` / `bottleneck` / `overrun_days` / `arithmetic_problems`。

**步骤 2：写修订方案步骤表。** 综合候选优点，把方案拆成步骤表 `/app/work/plan.json`：
```json
{"version": "rev1", "steps": [
  {"id": "S1", "name": "前驱液配制", "equipment": "EQ-GB", "equip_hours": 4,
   "samples": 1, "depends_on": []},
  {"id": "S2", "name": "旋涂", "equipment": "EQ-GB", "equip_hours": 16,
   "samples": 8, "per_sample_hours": 2, "batch_capacity": 4, "parallel": false,
   "depends_on": ["S1"], "replicates": 1, "batch_group": null,
   "alt_equipment": [], "reagents": [{"id": "RE-MAI", "quantity": 10}]}
]}
```
字段语义见 `references/booking_glossary.md`；步骤表是 schedule/repair 的输入。

**步骤 3：schedule 排程。** 先存 partial 再排：
```bash
python3 /skills/weekly-skill/scripts/schedule_forge.py schedule \
  --case /input/case.json --steps /app/work/plan.json \
  --start 2026-01-05 --outdir /app/work
```
检查 `schedule.json.detections`：依赖冲突、slot/window 溢出、`deadline_overrun_days`、设备双订。`gantt.md` 与 `cashflow.md` 直接进交付。

**步骤 4：超期则 repair 迭代 ≤3 轮。**
```bash
python3 /skills/weekly-skill/scripts/schedule_forge.py repair \
  --case /input/case.json --steps /app/work/plan.json --outdir /app/work
```
从 `repair.md` 选项表按"节省天数/代价比"选策略（优先作用于瓶颈设备的选项），改 plan.json 后回步骤 3 重排验证。**每轮必须重跑 schedule**（repair 的节省天是设备级折算，只有重排才算数）。3 轮仍超期 → honest partial：在 result.json 写明最小可达工期与缺口。

**步骤 5：以可行日程为骨架完成六要素完整方案。** 排期是本 skill 的重心，但交付必须覆盖六要素（详见 `references/scheduling_model.md` 末节清单）：
- 假设与变量：每步 equip_hours 的来源（case 路径或标注假设）；
- 对照组：正负对照步骤也要占 slot，写进步骤表；
- 设备材料：只用合同设备表（含 note 解析合并）内的设备与试剂；
- 时间成本：甘特图 + 现金流即本项；
- 参数范围：步骤参数必须落在 `parameter_domains` 内；
- 风险和异常：repair 各选项的代价列 + 失败模式表。
产出 `/app/output/plan.json`（含 steps 与 schedule 引用）与 `/app/output/plan.md`。

**步骤 6：result.json。** 按 `output_contract.required_fields` 填写；`candidate_assessment` 直接引用 throughput 结论；`validation` 引用 schedule detections；未确认项（批量夹具、替代设备口径、前瞻合同价格）进 `confirmation_items`。

## 5. 输出契约
- `result.json`：`case_id`、`revised_plan`、`candidate_assessment`、`validation`、`status`（complete/partial/blocked）、`uncertainty`、`sources`、`change_log`、`confirmation_items`（以 case 的 required_fields 为准）。
- `plan.json`：`{version, est_days(= schedule total_days), steps[], schedule_ref, cashflow_summary}`。
- `plan.md`：六要素章节 + 甘特图内嵌 + 瓶颈/修复论证（引用 throughput/repair 算式）。
- 脚本产物：throughput.json/md、schedule.json、gantt.md、cashflow.md、repair.json/md。

## 6. 失败模式与止损表
| 失败模式 | 信号 | 止损 |
|---|---|---|
| est_days 不可信 | throughput `est_days_verdict` 报警 | 以瓶颈算式替代，写进 candidate_assessment |
| 瓶颈设备超期 | `overrun_days > 0` | repair ≤3 轮；仍超期 → partial，给出最小工期 |
| 设备不在合同表 | `unknown_equipment` / "设备不在…无法核算" | 删除该步骤或进 confirmation_items，不得假设可约 |
| 依赖环/未知依赖 | `dependency_conflicts` 非空 | 修步骤表后重排；不得手工忽略 |
| window_days 溢出 | `slot_overflow` 非空 | 压缩该设备机时或确认窗口可续约（confirmation_items） |
| 脚本异常 | error_report.json | 读 error 字段修输入；脚本始终 exit 0，不得视为成功 |
| 现金流超预算 | cashflow.md `over_budget` | 减机时/换设备/降重复，并同步重排 |

## 7. 输入缺失/约束冲突的降级（honest partial）
- 缺 booking 字段：该设备标 `无法核算`，其余设备照常出报告，status=partial；
- 候选无 cost_items 也无步骤表：只出设备吞吐表，不判定 est_days；
- deadline 与 window 冲突（deadline > window_days）：两数并列报告，按 min 判定并在 uncertainty 说明；
- 任何情况下先把已算出的部分写入 `/app/output` 再迭代，不许空交付。

## 8. 预算意识
64 次模型请求内：脚本调用不占模型预算，尽量"一次吞吐体检 + ≤3 轮 schedule/repair"。每轮迭代前先把当前最优 plan.json/plan.md/result.json（status=partial）落盘 `/app/output`，再决定是否继续；最后 10 次请求内禁止开启新一轮 repair，只做文档收尾。
