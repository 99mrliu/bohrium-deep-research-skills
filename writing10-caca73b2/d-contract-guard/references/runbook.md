# 五阶段 Runbook

本 runbook 以 64 次模型请求 / 900 秒墙钟为基准预算。各阶段给出准入条件、动作、准出条件。原则: **保底产物先行, 增强随时可弃。**

## 阶段 0 — 契约与盘点 (目标: 0 次内容请求)

- 准入: 进入工作目录, 已知 /input 与 /app/output 路径。
- 动作:
  1. `python3 scripts/contract.py init --case /input/case.json --out /app/output/result.json`
  2. `python3 scripts/material_check.py --dir /input/materials --case /input/case.json --out-dir /app/work` (退出码 1 = 有问题, 把打印的 limits 行收下)
  3. `python3 scripts/budget.py plan --stages s0_contract,s1_minimum,s2_enhance,s3_discuss,s4_polish --ledger /app/work/budget_ledger.json`
- 准出: result.json 骨架存在且可解析; material_inventory.json 已生成; 缺失材料已全部进入 limits; 台账已建。
- 预算参考: 0–2 次请求, ≤30 秒 (脚本本身不耗模型请求)。

## 阶段 1 — 最小可用产物 (保底)

- 准入: 阶段 0 准出完成; 材料盘点非"零材料" (零材料走失败分支, 见 honest-partial.md)。
- 动作: 只依据盘点确认可读的材料, 写出保底版"结果与讨论"骨架到 /app/output/deliverable.md: 每段只含可溯源事实, 允许简短、允许标注"图件未提供, 按文字材料转述"。随后:
  - `python3 scripts/contract.py checkpoint --result /app/output/result.json --stage s1_minimum --note "..." --set deliverable='"deliverable.md"' --set preserved_facts='[...]' ...`
  - `python3 scripts/budget.py log --ledger /app/work/budget_ledger.json --stage s1_minimum --requests N --seconds S`
- 准出: /app/output 内已有 deliverable + 可解析 result.json, 且 preserved_facts/evidence_map 已填实。**从此刻起, 任何中断都有诚实产物。**
- 预算参考: ≤10 次请求, ≤150 秒。

## 保底产物的构成

1. `deliverable.md`: 结果段 (逐图/表陈述已核实事实) + 讨论段 (机制解释 + 数据缺口声明) + 事实来源清单。
2. `result.json`: case_id 原样; 契约五键非空或有解释; status 据实; sources 列出实际读取的文件。
3. `material_inventory.json/md` 与 `budget_ledger.json`: 过程证据。

## 阶段 2 — 结果增强 (可选-增强)

- 准入: 阶段 1 准出; `budget.py advise` 未建议砍增强。
- 动作: 逐图逐表补全结果节; 每个新增数值必须能在材料中定位; 读数不清的图表按异常处理表处置。结束: checkpoint + budget log。
- 准出: 结果节覆盖材料中全部图/表; change_log 记录本阶段增量。

## 阶段 3 — 讨论增强 (可选-增强)

- 准入/动作/准出同阶段 2 模式: 补机制解释、与数据缺口的对应关系、局限性。每论断挂来源或标注推断。

## 阶段 4 — 润色 (可选-润色, 最先被砍)

- 仅做语言与结构整理, **不得新增事实**。预算越过 70% 时此阶段应已被 advise 建议跳过。

## 阶段 5 — 定稿

- `python3 scripts/contract.py final_check --case /input/case.json --result /app/output/result.json --output-dir /app/output | tee /app/output/final_check.txt`
- 退出码 0 → 交付; 非 0 → 按 FAIL 项修复或在 change_log/limits 书面解释后重跑。

## 检查点纪律

- 每阶段结束**先 checkpoint 再记账**, 顺序不可颠倒 (先保住产物状态, 再消耗注意力)。
- checkpoint 只追加 stage_log/change_log; 写盘为 tmp + rename 原子替换。
- 中断恢复: 读取 result.json 的 stage_log 找到最后完成阶段, 从下一阶段继续, 不重做。

## 900 秒工作线 (示例排布)

| 时间 | 阶段 | 动作 | 累计请求 |
|---|---|---|---|
| 0:00–0:30 | s0 | init + material_check + plan | 0 |
| 0:30–3:00 | s1 | 写保底骨架 + checkpoint + log | ≤12 |
| 3:00–7:00 | s2 | 结果增强 + checkpoint + log | ≤26 |
| 7:00–11:00 | s3 | 讨论增强 + checkpoint + log; 越 70% 则 advise | ≤40 |
| 11:00–13:00 | s4 | 润色 (advise 建议砍则跳过) | ≤50 |
| 13:00–15:00 | s5 | final_check + 修复/解释 + 定稿 | ≤54 |
| 储备 | — | 10 次请求 / 120 秒, 仅用于 final_check 失败后的补救 | ≤64 |
