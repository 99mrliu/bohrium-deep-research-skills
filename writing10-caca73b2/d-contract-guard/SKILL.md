---
name: contract-guard-runner
description: 面向预算受限评测环境的执行纪律技能：在任何内容工作之前先建立契约有效的 result.json 骨架, 以检查点增量推进, 以预算台账感知调度, 在材料缺失或预算耗尽时仍能交付诚实、可解析、字段完整的产物。Use when running a writing task under a hard model-call/time budget where a valid result.json must survive any failure point.
---

# Contract Guard Runner — 契约优先的执行守护

## 解决的问题

在固定预算 (如 64 次模型请求 / 900 秒) 的评测运行中, 基础执行方式常见四类失败:

1. **预算耗尽导致无产物**: 内容工作做到一半被截断, 输出目录没有交付物。
2. **result.json 缺字段或不可解析**: 最后才匆忙拼装, 漏掉 output_contract 声明的键, 或写入中断产生半个 JSON。
3. **status 不诚实**: 实际只完成了骨架却记 complete, 或材料缺失却编造内容充数。
4. **材料缺失静默跳过**: 引用找不到、图表读不出时不留痕迹, 下游无法判断结果可信度。

本技能的处置原则是: 先立契约, 再谈内容; 每一阶段结束立即检查点; 预算有台账、有降级阶梯; 缺口一律书面化。

## 何时使用 / 不适用

**使用**: 评测或批处理环境, 输入为 /input/case.json + /input/task.md + 材料, 要求在 /app/output 交付产物与 result.json, 且存在硬预算 (请求数 / 墙钟时间 / 单次响应 token)。

**不适用**: 无契约要求的自由写作; 交互式、可无限重试的人工协作场景; 预算充裕到降级阶梯永不可能触发的任务 (此时本技能退化为轻微的形式开销)。

## 运行契约

1. 读取 `/input/case.json` 与 `/input/task.md` 的**实际文件内容**, 不凭记忆或假设作答; 材料目录以盘点结果为准。
2. 中间产物写入 `/app/work`, 最终产物写入 `/app/output`。
3. `result.json` 必须包含:
   - `case_id`: 与 case.json 中值**原样一致**, 不改写、不补全;
   - case.json `output_contract` 声明的**全部键** (标准键为 `deliverable`、`preserved_facts`、`evidence_map`、`change_log`);
   - `status`, 取值 ∈ {`partial`, `complete`, `failed`};
   - `sources`、`uncertainty`, 以及本技能要求的 `limits`、`stage_log`。
4. **任何时刻** result.json 必须是可解析 JSON: 内容工作开始之前即由 `contract.py init` 写出骨架, 此后只经 `contract.py checkpoint` 原子更新 (tmp + rename), 不做原地半截写。
5. `status=partial` 时, `limits` 或 `uncertainty` 必须具体写明缺什么、为什么; 空缺的契约键必须在 `change_log` 或 `limits` 中有书面解释。

## 依赖

Python ≥ 3.9, 仅标准库 (argparse / json / os / hashlib / tempfile / datetime)。三个脚本均在 `scripts/` 下, 以 `python3 scripts/<name>.py --help` 查看用法。

## 工作流 (按序执行)

- **阶段 0 — 契约与盘点** (内容工作前必须完成):
  1. `python3 scripts/contract.py init --case /input/case.json --out /app/output/result.json`
  2. `python3 scripts/material_check.py --dir /input/materials --case /input/case.json --out-dir /app/work`
  3. `python3 scripts/budget.py plan --stages s0_contract,s1_minimum,s2_enhance,s3_discuss,s4_polish --ledger /app/work/budget_ledger.json`
  盘点发现的缺失材料, 按脚本打印的原文粘贴进 result.json 的 `limits`。
- **阶段 1 — 最小可用产物**: 先写"保底版"结果段与讨论段骨架 (只含已核实事实, 允许短) 进 /app/output, 随即 `checkpoint --set deliverable=...`。此后无论何处中断, 输出目录已有诚实可用的交付物。
- **阶段 2–4 — 逐图逐节增强**: 结果节按图/表补全, 讨论节补机制解释与数据缺口, 最后润色。**每阶段结束必做两件事**: `contract.py checkpoint` + `budget.py log` 记账; 越过 70% 先 `budget.py advise` 再决定是否继续。
- **阶段 5 — 定稿**: `python3 scripts/contract.py final_check --case /input/case.json --result /app/output/result.json --output-dir /app/output`, 退出码 0 方可交付; 非 0 则按打印的 FAIL 项逐条修复或书面解释后重跑。

## 降级阶梯

预算或时间越过阈值时, 按 `budget.py advise` 的建议砍**可选阶段**, 顺序固定:

- L1 先砍润色 (polish);
- L2 再砍讨论增强 / 结果增强 (enhance / discuss);
- L3 冻结: 立即停止内容工作, 以当前保底骨架执行 final_check 定稿。

保底骨架 (阶段 0/1) **永远在保留之列**, 任何降级不得触碰。

## 异常处理表

| 异常 | 处置 |
|---|---|
| case.json 缺 `output_contract` | 按五标准键 (deliverable/preserved_facts/evidence_map/change_log + status) 建骨架, 并在 `uncertainty` 记一条说明 (init 自动完成) |
| 材料目录为空 / 被引用材料缺失 | 将 material_check 打印的行原样写入 `limits`; 零材料时 status 记 `failed`, **不得编造内容**; 可写"失败说明件"作为 deliverable |
| 图表读数不清 / 缺统计量 / 单位不明 | 不猜测数值; 在正文按材料原文转述, 在 `uncertainty` 记明哪一项读数不清及影响 |
| 引用找不到 | 在 `limits` 记"引用缺失: <路径>", 正文相应论断标注来源待核 |
| 写盘失败 | 更换路径重试一次 (如 /app/output 失败则先写 /app/work 再复制); 仍失败则在可写位置保留 result.json 并将情况记入 `limits` |
| result.json 意外损坏 | checkpoint 会拒绝解析并报错; 以最近一份 checkpoint 或重新 init 恢复, 损失限于最近一次阶段增量 |

## 红线

1. **不伪造运行状态**: 未完成不得记 complete; 材料缺失不得编造事实、数值或图件。
2. **status 由 final_check 规则裁决, 不得手工粉饰**: complete 仅当无未解决 limits; failed 必须附失败原因; 手工改 status 后必须重跑 final_check 验证。
3. **checkpoint 不覆盖历史**: `stage_log` 与 `change_log` 只追加; 任何阶段不得删除或改写既往检查点记录。

## 自查方法

交付前依次确认: (1) `final_check` 退出码为 0 且各项 PASS; (2) `python3 -c "import json;json.load(open('/app/output/result.json'))"` 不报错; (3) result.json 的 `stage_log` 覆盖阶段 0 至定稿; (4) `budget.py advise` 无 OVERRUN 遗留; (5) limits/uncertainty 中每条缺口都能指出对应的材料或预算原因。

## 限制

本技能管执行纪律, 不管写作质量上限: 保底骨架保证"有且诚实", 不保证"好"。`budget.py` 的用量来自调用方如实记账, 无法自动拦截平台侧的真实请求消耗; 阶段 tier 依阶段名启发式判定 (polish/润色 → 可选, enhance/discuss/增强 → 可选), 自定义阶段名可能全部落入保底 tier, 此时降级建议退化为"全量或冻结"。`material_check.py` 只交叉核对 case.json 常见字段 (materials/figures/files/inputs 等) 中显式声明的路径, 正文里隐含的引用不在核对范围。
