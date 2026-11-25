---
name: rq-coverage-compass
description: 科研问题驱动检索的"覆盖罗盘"——以证据充分性与停止判据为中心的检索节奏控制技能。把研究问题分解为 2–5 个子问题（Agent 按模板写 decomposition.json，缺省时脚本自动派生并如实标注），对有限快照做逐子问题检索计数，产出 SQ×证据覆盖矩阵、sufficient/thin/starved 充分性分级、第 2 轮放宽年份窗的边际收益估计，以及带可复核理由的停止决定（evidence_sufficient / marginal_gain_low / handoff_to_human），最后按 output_contract 装配 result.json。适用于有限快照下判断"每个子问题证据够不够、什么时候可以停、什么时候必须交人工"。不适用：全网实时检索、单篇精读、替冲突证据做学术裁决。
---

# rq-coverage-compass — 证据充分性与停止判据

**核心立场：继续找还是停，不由疲劳感决定，而由一张可复算的 SQ×证据覆盖矩阵和
三条写死的停止判据决定。**

本技能的重心在**证据充分性测量**：检索计数保持轻量确定，重器放在覆盖矩阵、
充分性分级、边际收益估计与停止决定。两条命令完成一个案例；模型判断集中在唯一
一处——按 references/subquestion-template.md 把研究问题分解成子问题清单
（不分解也能跑，脚本自动派生并降级标注）。

## 运行契约（平台环境）

- 输入：`/input/case.json`（含 `case_id`、`research_question`、`output_contract`）、
  `/input/task.md`、快照导出文件（JSON/JSONL/CSV/TSV/RIS，以实际内容为准）。
- 中间产物：`/app/work`；最终交付：`/app/output`（含 `result.json`）。
- `result.json` 必含 `case_id` 与 `output_contract` 列出的**每一个**字段
  （finalize.py 动态读契约，禁止硬编码字段名），外加 `status`
  （complete/partial/blocked）、`sources`、`uncertainty`；填不了的字段留空容器，
  并在 `field_notes`/`uncertainty` 写明原因。
- 本技能目录记为 `SKILL_DIR`（通常 `/skills/weekly-skill`）；非平台环境换成实际路径。
- 仅 Python 3 标准库（≥3.8），零网络。**预算纪律**：两条命令约 1 分钟跑完；
  测量一旦完成，停止决定与矩阵即可交付——即使后续中断，coverage_report.json
  已是诚实的中间结论。

## 标准流程（两步 + 一次分解）

```bash
# 0) 子问题分解（唯一需要模型判断的环节）：按 SKILL_DIR/references/subquestion-template.md
#    把 RQ 拆成 2–5 个子问题，写 /app/work/decomposition.json。
#    跳过此步也可以——measure.py 会从 RQ 自动派生并在产物中标注 auto_derived。

# 1) 覆盖测量：解析快照 → 逐 SQ 检索计数 → SQ×证据覆盖矩阵
#    → sufficient/thin/starved 分级 → 边际收益估计 → 停止决定 + 缺口分类
python3 SKILL_DIR/scripts/measure.py \
    --case /input/case.json --input-dir /input --work /app/work

# 2) 契约装配：覆盖矩阵/停止决定/候选证据集 → result.json（空字段自动写说明）
python3 SKILL_DIR/scripts/finalize.py \
    --case /input/case.json --work /app/work --out /app/output
```

读停止决定再行动：`evidence_sufficient` → 直接交付；`marginal_gain_low` → 交付，
thin 子问题已在 uncertainty 声明；`handoff_to_human` → 不要硬凑，把 reason 与
缺口分类原样交人工（reason 本身可复核：矩阵里每个数字都能重算）。

## 产物清单

| 路径 | 内容 |
|-|-|
| `/app/output/result.json` | 按契约装配的最终结果（status/sources/uncertainty/field_notes） |
| `/app/output/coverage_matrix.json` | SQ×证据覆盖矩阵：可用/争议/出窗/缺元数据命中数、分级、缺口、边际收益、证据 rid 与命中词 |
| `/app/output/stop_decision.json` | 停止决定 + 一句可复核理由 + 逐 SQ 建议（accept/accept_with_caveat/needs_human） |
| `/app/work/coverage_report.json` | 测量全量报告（含 input_files、thresholds、problems） |
| `/app/work/decomposition.used.json` | 实际使用的子问题清单与来源（agent_file/auto_derived） |

## 充分性分级与停止判据（详见 references/stop-criteria.md）

- 分级：可用证据 ≥3 条 sufficient；1–2 条 thin；0 条 starved
  （阈值在 measure.py 顶部 `SUFFICIENT_MIN`，单一事实来源）。
- 缺口分类（非 sufficient 时诊断原因）：no_records / out_of_window /
  only_conflicted / metadata_missing。
- 停止判据（按序取第一个命中）：
  1. **handoff_to_human** — 快照零记录，或存在 starved 子问题，或 thin 子问题的
     第 2 轮模拟新增超过每子问题 1 条（值得再来一轮但快照有限，交人工）；
  2. **evidence_sufficient** — 全部子问题 sufficient；
  3. **marginal_gain_low** — 无 starved、有 thin，且放宽年份窗的第 2 轮模拟新增
     ≤ thin 子问题数（继续检索不改变分级，可以停）。

## 异常处理（诚实降级）

- case.json 缺失/损坏：measure 写出带 problems 的报告并 exit=2；finalize 交付
  `status=blocked` 骨架并 exit=2，指明缺什么。
- 无 decomposition.json：自动派生 2–5 个子问题，产物标注 `auto_derived`，
  problems/uncertainty 写明"口径粗于人工分解"——**降级必留痕**。
- 快照零记录：`status=blocked`，决定 handoff_to_human，理由"无任何证据可测量，
  不能臆造覆盖结论"。
- 未跑 measure 直接 finalize：交付 blocked 骨架，uncertainty 指明先运行 measure.py。
- 冲突意见夹具（conflict_opinion）：计入矩阵 conflicted 列并登记到 uncertainty，
  不计入可用证据，**不做学术裁决**。
- 缺年份/DOI 的证据：计入可用但单记 metadata_missing 列，并在 uncertainty 声明
  归属核验受限。

## 最小调用示例（合成示例，非正式案例结果）

`examples/minimal/` 内含合成 case.json（10 契约字段）、9 条合成快照记录
（`10.0000/synth.cc.*` 虚构 DOI）与一份按模板手写的 decomposition.json（3 个子问题）。
设计：SQ-1 晶界钝化效率（3 条可用 → sufficient）、SQ-2 湿热稳定性（2 条可用 +
1 条出窗 + 1 条冲突夹具 + 1 条缺年份 → thin）、SQ-3 铅泄漏生物毒性
（零命中 → starved，触发 handoff）。实测输出：

```
measure.py  → {"ok": true, "records": 9, "subquestions": 3,
               "decomposition_source": "agent_file",
               "sufficiency": {"SQ-1": "sufficient", "SQ-2": "thin", "SQ-3": "starved"},
               "stop_decision": "handoff_to_human", "problems": []}        (exit 0)
finalize.py → {"ok": true, "status": "partial", "contract_fields": 10,
               "candidates": 5, "stop_decision": "handoff_to_human",
               "uncertainty_items": 5}                                    (exit 0)
```

partial 的原因（均写入 uncertainty）：SQ-2 thin、SQ-2 的冲突意见夹具已登记待人工、
SQ-2 有 1 条证据缺年份/DOI、SQ-3 零可用证据触发 handoff。完整产物见
`examples/minimal/expected/`（由上述命令真实生成）。

异常路径实测：删去 decomposition.json 重跑，自动派生 5 个子问题（3 sufficient /
2 thin），停止决定变为 `marginal_gain_low`，产物标注 `auto_derived`；空快照重跑，
measure exit=2，result.json `status=blocked`——两条路径均诚实降级，无臆造。

## 复用与维护

- 换领域：measure.py 顶部 `CROSS_LINGUAL` 小词表与 `SUFFICIENT_MIN` 阈值是
  声明式配置；子问题术语永远以 Agent 手写的 decomposition.json 为准。
- 换契约：无需改代码——契约字段全部从 case.json 动态读取。
- 换停止判据：判据语义集中在 references/stop-criteria.md 与 measure.py 的
  `stop_decision()`，改判据必须同步改文档，保持"文档即判据"。
- 版本：v1.0（2026-11，Python ≥3.8，stdlib only）。
