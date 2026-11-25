---
name: omission-risk-diagnostics
description: >-
  下游遗漏风险诊断台。当系统性文献检索的逐条纳排判定（judgments/decisions，由模型或其他流程
  在上游完成）已经存在，需要回答"会不会漏掉该纳入的文献"时触发。方法链：result.json 骨架先行
  → 读 output_contract → 消费 judgments/decisions → 险漏队列挖掘（near-miss mining，单理由排除 /
  uncertain 判据 / 弱证据锚定 / 无 not_met 依据的排除）→ 排除稳健性分析（fragility，理由码分布与
  单理由排除占比）→ 主题面覆盖核查（facet coverage，零纳入 facet 报警）→ 自动生成结构化遗漏说明
  （omission statement）与按风险分排序的人工复核工作清单（recheck worklist）→ 终检。边界：不做初筛
  判定本身（只消费既有判定）、不做 PRISMA 流程图渲染、不做计数闭合审计、不联网；仅基于有限快照，
  不声称全局召回，不预置答案，不伪造人工复核。
---

# omission-risk-diagnostics — 下游遗漏风险诊断台

## 1. 适用场景与边界（红线）

**适用场景**：上游已产出逐条纳排判定文件（`judgments.json` / `decisions.json`，含每条记录的
decision、逐判据 verdict、rationale_code、证据 quote 与锚定强度），需要对"遗漏该纳入文献的风险"
做可执行诊断，并产出可追溯的遗漏说明与人工复核队列。典型触发语："检查一下排除得稳不稳"
"哪些排除可能误伤""生成遗漏说明""给我一个复核清单"。

**红线（不可越界）**：

1. **不做初筛判定本身**：本技能只消费既有 judgments/decisions；若输入中没有判定文件，由模型
   先按其他流程产出，或将 status 诚实置为 partial 并在 uncertainty 说明，绝不由本技能代判。
2. **不做 PRISMA 流程图渲染**，**不做计数闭合审计**（属其他方向职责）。
3. **不联网**：只有限题录快照，不得声称全局召回（global recall）；facet 零纳入只是"报警"，
   不得直接定性为"检索遗漏"或"该面真空"。
4. **不预置答案、不伪造人工复核**：复核工作清单的全部条目状态为 `pending_human_recheck`，
   任何复核结论必须由真实人工产生并单独留痕。
5. 证据 quote 必须锚定到标题/摘要真实片段；selfcheck 发现未锚定即判校验失败。

## 2. 运行环境

- Python 3（仅标准库），无第三方依赖；`python3 scripts/xxx.py --help` 可见全部参数。
- 退出码约定：**0=通过**；**2=输入不足诚实降级**（能写的产物照写，result.json 记 uncertainty）；
  **3=校验失败**（输入非法、证据未锚定、合同字段缺失且无说明）。
- 路径默认值均可覆盖：`--input-dir`（默认 `/input`）、`--work`（默认 `/app/work`）、
  `--output-dir`（默认 `/app/output`）。
- 全部脚本**幂等**：中间产物与 result.json 采用"原子整文件覆盖/按 key 合并"，重复运行结果一致；
  顶层 try/except 兜底，任何意外只向 stderr 打一行信息并返回非零码，**不抛 traceback**。
- 预算感知：工作流第 1 步即落 result.json 骨架，之后每个脚本增量填充，任一环节失败都有可交付的
  诚实 partial 结果。

## 3. 工作流程（编号步骤）

1. **[脚本] 骨架先行**：`scaffold_result.py` 读 `case.json`，立即在 output-dir 落 `result.json`
   骨架——合同字段全部就位、填不了的置 null、status=partial、change_records 开始记账。
2. **[脚本] 读合同**：`output_contract.required_fields` 在骨架阶段读取；缺失则用默认字段集合并
   记 uncertainty、退出码 2 降级（运行时合同优先，不得删字段）。
3. **[模型] 确认判定输入**：检查 input 中是否存在 judgments/decisions。若不存在，模型须先按
   本技能之外的流程产出逐条判定文件；无法产出则保持 partial 并停止诊断步骤（诚实降级）。
4. **[脚本] 险漏队列挖掘**：`mine_near_misses.py` 产出 `work/near_misses.json` 与
   `work/recheck_worklist.json`（按 risk_score 降序），并填充 result.json 的
   `near_misses` / `recheck_worklist` 字段。
5. **[脚本] 排除稳健性分析**：`fragility_report.py` 产出 `work/fragility_report.json`
   （理由码分布、单理由排除占比、fragile_flag），填充 `fragility_report` 字段。
6. **[脚本] 主题面覆盖核查**：`facet_coverage.py` 将 case.json 的 facets 与纳入集比对，
   产出 `work/facet_coverage.json`，零纳入 facet 置 `zero_inclusion_alarm`，填充
   `facet_coverage` 字段。
7. **[脚本] 生成遗漏说明**：`omission_statement.py` 汇总三个诊断产物，生成
   `output/omission_statement.md`（人读）并填充 `omission_statement` 字段（机读摘要）。
8. **[模型] 审读与转交**：模型通读 `omission_statement.md` 与复核工作清单，向用户/评审呈现
   风险点；**不得**代为填写复核结论（红线 4）。
9. **[脚本] 终检**：`selfcheck.py` 校验合同字段完整性、证据锚定真实性，终置 status
   （全部通过且无降级 → completed；否则 partial 并写明原因），产出 `work/selfcheck.json`。

## 4. 输出合同映射表

| output_contract 字段 | 生产者 | 落盘位置 | 内容 |
|---|---|---|---|
| `case_id` | scaffold_result.py | result.json | 透传 case.json |
| `status` | selfcheck.py 终置 | result.json | completed / partial / failed |
| `near_misses` | mine_near_misses.py | work/near_misses.json → result.json | 险漏队列、触发器、风险分 |
| `fragility_report` | fragility_report.py | work/fragility_report.json → result.json | 理由码分布、单理由占比、fragile_flag |
| `facet_coverage` | facet_coverage.py | work/facet_coverage.json → result.json | 逐 facet 命中与零纳入报警 |
| `omission_statement` | omission_statement.py | output/omission_statement.md + result.json 摘要 | 结构化遗漏说明 |
| `recheck_worklist` | mine_near_misses.py | work/recheck_worklist.json → result.json | 按风险分排序的人工复核队列 |
| `sources` | 各诊断脚本增量 | result.json | 输入文件路径 + sha256 + 角色 |
| `uncertainty` | 各脚本增量 | result.json | 降级与限制说明（null 字段必须在此有交代） |
| `change_records` | 各脚本追加 | result.json | 变更日志（ts / action / files） |

若评测合同的字段名与上表不同，以运行时 `output_contract.required_fields` 为准：骨架保证字段
齐备，填不了的填 null 并在 uncertainty 说明。

## 5. 异常处理表

| 异常情形 | 行为 | 退出码 |
|---|---|---|
| case.json 缺失 | 写最小 result.json（status=failed），stderr 说明 | 2 |
| case.json JSON 非法 | 不产物，stderr 一行说明 | 3 |
| output_contract.required_fields 缺失 | 默认字段集合落骨架 + uncertainty 说明 | 2 |
| judgments/decisions 缺失 | 该诊断写降级、result.json 记 uncertainty；等待模型先产出判定或保持 partial | 2 |
| judgments 结构不识别 | stderr 说明，不产物 | 3 |
| records 缺失（facet_coverage / selfcheck 需要） | 对应环节写 skipped + uncertainty | 2 |
| facets 未在 case.json 定义 | facet_coverage 写 skipped 段并说明需人工补 facet | 2 |
| work/ 上游诊断产物缺失（omission_statement） | 不生成说明，stderr 提示先跑诊断脚本 | 2 |
| 证据 quote 未锚定到题录原文 / 合同 null 字段无说明 | selfcheck 判失败，status 保持 partial | 3 |
| 任何未预期异常 | 顶层兜底，stderr 一行，不 traceback | 3 |

## 6. 最小调用示例

```bash
# 按序执行（路径参数均可省略，默认 /input、/app/work、/app/output）
python3 scripts/scaffold_result.py     --input-dir /input --work /app/work --output-dir /app/output
python3 scripts/mine_near_misses.py    --input-dir /input --work /app/work --output-dir /app/output
python3 scripts/fragility_report.py    --input-dir /input --work /app/work --output-dir /app/output
python3 scripts/facet_coverage.py      --input-dir /input --work /app/work --output-dir /app/output
python3 scripts/omission_statement.py  --input-dir /input --work /app/work --output-dir /app/output
python3 scripts/selfcheck.py           --input-dir /input --work /app/work --output-dir /app/output
echo "exit=$?"   # 0 通过 / 2 诚实降级 / 3 校验失败
```

可复现的合成示例（非真实评测案例）见 `examples/`：`bash examples/run_example.sh` 一键跑通，
逐步命令与真实 exit code 记录在 `examples/selftest_log.md`。

## 7. 参考文档

- `references/omission_risk_method.md`：诊断方法学、触发器定义、风险权重、理由码字典。
- `references/facet_model.md`：研究问题 facet 分解方法与零纳入报警的解释边界。

## 8. 维护信息

- 版本：v1.0.0
- 日期：2026-11-25
- 作者：bohrium-deep-research-skills 项目组
