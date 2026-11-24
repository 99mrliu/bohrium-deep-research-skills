---
name: process-qc-runner
description: 面向「实验结果解释与异常分析」的过程质量控制 Skill。把解释工作流拆成清单化阶段（命令+输入输出哈希+超时+失败策略），幂等断点恢复、失败现场保留、预算台账（64 请求/900 秒）驱动降级决策、每阶段 checkpoint 落盘诚实 partial。当任务需要在固定预算内稳定、可恢复、可复核地完成多步分析时触发。
---

# process-qc-runner：过程质量控制与断点恢复

## 用途与重心

本 Skill 的重心是**过程质量**。平台评测在 900 秒 / 64 次模型请求内跑 3 个案例 × 3 次重复，最常见的隐性失败是过程失控：跑到一半超时什么都没留下、某步失败后 Agent 从头重跑烧光预算、同一个分析步骤因输入未变却重复执行。本 Skill 提供三件套：**阶段化运行器**（manifest + 输入输出哈希 + 幂等恢复）、**预算台账**（用量驱动降级）、**checkpoint 结果工具**（任何时刻磁盘上都有诚实 partial）。

**边界**：
- 不管分析内容，只管过程的可靠性、可恢复性、可复核性；分析脚本由任务自备（plan.json 里引用）。
- 恢复语义是保守的：输入哈希不变才跳过；输入一变，该阶段及下游全部作废重跑。
- 纯 stdlib。

## 运行时契约

- 输入：`/input/case.json`、`/input/task.md`、材料；plan.json 由 Agent 按案例生成到 `/app/work/plan.json`。
- 工作目录 `/app/work`（manifest 在 `/app/work/qc/manifest.json`）；成果 `/app/output/result.json`（case_id + 契约全字段 + 诚实 status + sources/uncertainty/change_records）。
- **checkpoint 纪律**：每个阶段结束必须 `result_kit.py checkpoint`；这是「中断也有交付」的唯一保证。
- 脚本路径以 `/skills/weekly-skill/scripts/` 书写；安装路径不同逐字替换前缀。

## 标准流程

```bash
S=/skills/weekly-skill/scripts
# 0) 开工三件套（最先执行）
python3 $S/result_kit.py scaffold --case /input/case.json --out /app/output/result.json
python3 $S/budget.py init --work /app/work --requests 64 --seconds 900
# 1) 写 plan.json（阶段=一条 shell 命令+输入输出声明+超时+on_fail）
# 2) 运行（失败即停，现场保留；修复后同一命令续跑，已完成阶段自动跳过）
python3 $S/qc_runner.py run --plan /app/work/plan.json --work /app/work
# 3) 每个关键分析请求后记账
python3 $S/budget.py tick --work /app/work
# 4) 收尾前
python3 $S/budget.py report --work /app/work
python3 $S/result_kit.py verify --case /input/case.json --out /app/output/result.json
python3 $S/qc_runner.py status --work /app/work   # 全部 OK 才可交付
```

## 降级策略（budget report 输出为准）

| 用量 | 行动 |
|-|-|
| <50% | 正常推进 |
| 50–80% | 不开新支线，优先填满契约字段 |
| >80% | 立即收尾：现状写入 result.json，status=partial，limitations 注明预算耗尽 |

## 失败处理

- 阶段失败：读 manifest 的 `stderr_tail` 定位 → 修复（改脚本/改输入理解）→ 同一 `run` 命令续跑；**不要**手工跳步后在结论里假装跑过。
- 输出被外部改动：`qc_runner.py status` 显示 STALE-OUTPUT → 该阶段重跑。
- 不可恢复失败（材料缺失）：`result_kit.py checkpoint --status partial --limitation "…"` 落盘现状，进下一案例。

## 最小示例

`examples/`（**合成示例**）：三阶段 plan，其中阶段 2 首次运行故意失败（缺输入文件），演示 FAIL→修复→续跑时阶段 1 被 SKIP 的幂等恢复，以及 budget 台账。见 `examples/README.md`。
