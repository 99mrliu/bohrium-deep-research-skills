---
name: stagegate-qc-runner
description: 当需要在严格时间与请求预算（900 秒 / 64 次模型请求）内完成学术写作、报告生成或材料整合类任务时使用本 skill。它是写作过程的门禁系统而非内容校对器：通过五阶段门禁（intake→outline→draft→audit→finalize）强制执行预算纪律，init 即落一版骨架 result.json 实现"先交付后优化、绝不空交"，check/selfcheck/deliver 分别提供阶段产物校验、量规自评与出口清单，任何时刻被中断都有诚实 partial，部分完成如实降级并全程留痕。
---

# stagegate-qc-runner：写作过程的阶段门禁与质量控制

## 定位

本 skill **不验证事实、不管文体、不做渲染**。它是写作过程的门禁系统（process
stage-gate QC）：管理"流程是否被诚实执行"，而非"内容是否正确"。核心承诺：

1. **先交付后优化**：`init` 完成的瞬间，输出目录就存在一版全字段的骨架
   `result.json`（所有契约字段 + `PENDING`）与 deliverable 占位——任何时刻被杀，
   都有一个诚实可解释的 partial。
2. **预算纪律**：900 秒被切成 5 个阶段 deadline，每次 `check` 报告已用秒数与
   偏差，超前给 `GO`，逾期给 `WARN-BUT-PROCEED`（不阻塞，但提示立即交付当前
   最好版本）。
3. **绝不空交、绝不静默**：`deliver` 的出口清单任一项失败都如实写入
   `delivery_manifest.json` 与 `worklog.jsonl`，仍允许交付，不静默通过。

## 运行契约（评测平台运行时）

- skill 安装于 `/skills/weekly-skill`；本 bundle 的脚本以
  `python3 /skills/weekly-skill/scripts/gate.py ...` 调用。
- 输入：`/input/case.json`、`/input/task.md` 及材料文件。
- 工作目录：`/app/work`（workplan、worklog、notes、初稿都放这里）。
- 最终输出：`/app/output`。其中 `result.json` 必须**原样包含** `case.json` 中
  `output_contract` 的全部字段（典型键：`case_id`、`deliverable`、
  `preserved_facts`、`evidence_map`、`change_log`），`case_id` 与输入逐字节一致，
  并含诚实的 `status` / `sources` / `uncertainty` / change records。
  部分完成必须如实说明（`status: "partial"` + `uncertainty` + `change_log`）。
- 预算：**64 次模型请求 / 900 秒**。
- 三个目录可用环境变量 `STAGEGATE_INPUT_DIR` / `STAGEGATE_WORK_DIR` /
  `STAGEGATE_OUTPUT_DIR` 覆盖（用于本地演练与 `examples/` 复现）。
- 依赖：仅 Python3 标准库，无网络、无第三方包。

## 可复制命令序列

```bash
# 0) 定义路径（平台运行时省略，使用默认 /input /app/work /app/output）
export STAGEGATE_INPUT_DIR=/input
export STAGEGATE_WORK_DIR=/app/work
export STAGEGATE_OUTPUT_DIR=/app/output
GATE="python3 /skills/weekly-skill/scripts/gate.py"

# 1) 初始化：生成 workplan.json + 骨架 result.json + deliverable 占位
$GATE init

# 2) 阶段门禁：每个阶段产出 required_artifacts 后立即 check
#    intake   → /app/work/notes/material_inventory.md
#    outline  → /app/work/notes/outline.md + notes/evidence_assignment.md
#    draft    → /app/work/deliverable.md（允许【待确认】，禁止 TODO/XXX）
#    audit    → /app/work/notes/audit_report.md
$GATE check intake
$GATE check outline
$GATE check draft
$GATE check audit

# 3) 量规自评：机器可判项自动评分，输出 selfcheck_report.md + 需模型自答清单
$GATE selfcheck

# 4) 交付：装配终版 result.json + 出口清单 + delivery_manifest.json
$GATE deliver
```

退出码约定：`check` 产物缺失/占位 → 1；`deliver` 出口清单未全过 → 2
（仍完成交付并诚实记录）；其余成功路径 → 0。`WARN-BUT-PROCEED` 不改变退出码。

## 900 秒时间表

| 阶段 | 截止（秒，相对 init） | 必备产物（相对 /app/work） | 门禁命令 | 到点未完成怎么办 |
|---|---|---|---|---|
| intake | 120 | `notes/material_inventory.md` | `check intake` | 用已有清单直接进入 outline，缺失材料记入 uncertainty |
| outline | 300 | `notes/outline.md`、`notes/evidence_assignment.md` | `check outline` | 按最简骨架（3 段式）开写 draft，不回头补完美大纲 |
| draft | 600 | `deliverable.md` | `check draft` | 未写完的段落用【待确认】标注收尾，立即转 audit |
| audit | 780 | `notes/audit_report.md` | `check audit` | 用 `selfcheck` 代替手写 audit，报告即产物 |
| finalize | 860 | （由 `deliver` 生成） | `deliver` | 860 秒是硬线：无论完成度如何都必须跑 `deliver` |
| 缓冲 | 900 | — | — | 留 40 秒应对装配/写盘/意外重试 |

配套模型请求预算（64 次）建议：init/清点 ≤6，outline ≤10，draft ≤30，
audit/selfcheck ≤10，finalize/修复 ≤8。

## 异常处理

- **某阶段产物无法完成**：不要停滞。在 `deliverable.md` 用【待确认】标注缺口，
  在 `/app/work` 写 `preserved_facts.json` / `evidence_map.json` 记录已完成部分，
  直接跳到后续阶段。`deliver` 会把残留 `PENDING` 如实写入 `change_log`，
  `status` 自动置为 `"partial"`。降级交付 > 空交。
- **check 失败（退出码 1）**：补齐缺失产物后重跑同一 `check`；若时间不足，
  跳过该阶段继续推进——worklog 已记录 FAIL，finalize 时会汇入 `change_log`，
  评审可见完整过程。
- **check 逾期（WARN-BUT-PROCEED）**：不阻塞。压缩后续阶段时间，优先保证
  draft 完整与 deliver 必达。
- **deliver 出口清单 FAIL（退出码 2）**：按 FAIL 清单逐项修复后重跑 `deliver`；
  无法修复的项保留在 `delivery_manifest.json.exit_check_failures` 中，诚实交付。
- **重复运行的幂等性**：`init` 可安全重跑——保留原 init 时间戳（预算时钟不
  重置）、不覆盖已有 `result.json`；`check`/`selfcheck` 任意次重跑只追加
  worklog；`deliver` 每次重跑全量重建 `result.json` 与 manifest，结果确定。

## 机器判定边界

`selfcheck` 只对机器可判项评分（result.json 字段齐全、deliverable 字数与占位符、
evidence_map / change_log 非空、【待确认】计数）；事实正确性、任务覆盖度等列为
"需模型自答"清单，必须逐条诚实回答，禁止默认全勾。量规全文见
`references/rubric.md`，阶段语义与失败处置矩阵见 `references/stage-protocol.md`。

## 最小示例

`examples/` 提供合成示例全套（case_id=`EXAMPLE-NOT-A-TEST-CASE`，**合成示例，
非正式案例结果**）：输入、真实运行命令与全部产物（骨架版与终版 result.json、
workplan、worklog、selfcheck 报告、delivery manifest）。按
`examples/README.md` 的命令序列可在两分钟内复现完整门禁流程（含一次人为 FAIL
与修复）。
