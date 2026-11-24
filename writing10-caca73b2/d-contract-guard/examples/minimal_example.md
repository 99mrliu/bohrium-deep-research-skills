# 最小可运行示例

> 本示例为合成示例: `examples/input/` 下的 case.json / task.md / materials/notes.md
> 均为虚构的事实表 (case_id `SYNTH-EXAMPLE-001`), 仅用于演示命令与产物形态。
> 以下命令与输出均为在本仓库 `skill/` 目录下真实运行的结果 (时间戳为真实运行时间);
> 对应的完整产物见 `examples/output/`, 失败分支产物见 `examples/failcase/output/`。

## 1. 阶段 0: 契约骨架 (内容工作之前)

```
$ python3 scripts/contract.py init --case examples/input/case.json --out examples/output/result.json
INIT OK: examples/output/result.json
  case_id      : SYNTH-EXAMPLE-001
  contract keys: deliverable, preserved_facts, evidence_map, change_log, figures
  status       : partial
(exit=0)
```

## 2. 阶段 0: 材料盘点

```
$ python3 scripts/material_check.py --dir examples/input/materials --case examples/input/case.json --out-dir examples/output
INVENTORY: examples/output/material_inventory.json (1 文件)
SUMMARY  : examples/output/material_inventory.md
PROBLEMS: 无
(exit=0)
```

## 3. 阶段 0: 预算规划

```
$ python3 scripts/budget.py plan --stages s0_contract,s1_minimum,s2_enhance,s3_discuss,s4_polish --ledger examples/output/budget_ledger.json
BUDGET PLAN — 总预算 64 请求 / 900s; 储备 10 请求 / 120s; 可分配 54 请求 / 780s
  s0_contract      11 请求 / 156s   [保底]
  s1_minimum       11 请求 / 156s   [保底]
  s2_enhance       11 请求 / 156s   [可选-增强]
  s3_discuss       11 请求 / 156s   [可选-增强]
  s4_polish        10 请求 / 156s   [可选-润色]
  储备            10 请求 / 120s   [永不主动使用]
LEDGER: examples/output/budget_ledger.json
(exit=0)
```

## 4. 阶段 1: 保底骨架 + 检查点

先写保底版 `examples/output/deliverable.md` (结果/讨论骨架, 仅含可溯源事实), 然后:

```
$ python3 scripts/contract.py checkpoint --result examples/output/result.json --stage s1_minimum \
    --note "保底骨架 deliverable.md 已写入输出目录。" \
    --set deliverable='"deliverable.md"' \
    --set 'preserved_facts=["8 h 硬度 98 HV (materials/notes.md)","24 h 峰值硬度 132 HV (materials/notes.md)", ...]' \
    --set 'evidence_map=[{"claim":"硬度随时效时间先升后降, 24 h 达峰","source":"materials/notes.md"}, ...]' \
    --set 'figures=["图1: 24 h 样品 TEM 照片 — 图片文件未随材料包提供, 仅在正文按事实表转述。"]' \
    --set 'limits=["缺失材料: 图1 TEM 图片文件未随包提供, ...", "数据缺口: 缺少 16 h 硬度点与 48 h TEM, 已在讨论第 2 节声明。"]' \
    --set 'uncertainty=["48 h 硬度下降归因为过时效属机制推断, 缺 48 h TEM 直接证据。"]'
CHECKPOINT OK: stage=s1_minimum -> examples/output/result.json
(exit=0)
```

(为排版紧凑, 上列 --set 参数以 `...` 略写; 完整实值见 examples/output/result.json。)

## 5. 阶段 2–3: 增强 + 记账 (模拟预算压力)

```
$ python3 scripts/budget.py log --ledger examples/output/budget_ledger.json --stage s2_enhance --requests 14 --seconds 200
LOG: stage=s2_enhance +14 请求 / +200s
  已用 32/64 请求 (50%), 380/900s (42%); 剩余 32 请求 / 520s
  OK: 预算健康。
(exit=0)

$ python3 scripts/budget.py log --ledger examples/output/budget_ledger.json --stage s3_discuss --requests 16 --seconds 260
LOG: stage=s3_discuss +16 请求 / +260s
  已用 48/64 请求 (75%), 640/900s (71%); 剩余 16 请求 / 260s
  WARN: 已越过 70% 预算线, 运行 advise 获取降级建议。
(exit=0)
```

## 6. 降级建议: advise 判定砍润色

```
$ python3 scripts/budget.py advise --ledger examples/output/budget_ledger.json
ADVISE — 剩余可调度 6 请求 / 140s; 未完成阶段 ['s4_polish'] 计划需 10 请求 / 156s
  L1 砍润色: 跳过 ['s4_polish']; 其余阶段照常。
  原则: 保底骨架 (tier=保底) 永远在保留之列; 降级只砍可选阶段。
(exit=0)
```

据此记录跳过决定 (检查点不覆盖历史, 只追加):

```
$ python3 scripts/contract.py checkpoint --result examples/output/result.json --stage s4_polish \
    --note "按 advise L1 建议跳过润色阶段 (figures 已在 limits 说明缺失原因); 保底骨架定稿, status 维持 partial (图1 缺失, 数据缺口未闭合)。"
CHECKPOINT OK: stage=s4_polish -> examples/output/result.json
(exit=0)
```

## 7. 阶段 5: final_check → PASS

```
$ python3 scripts/contract.py final_check --case examples/input/case.json --result examples/output/result.json --output-dir examples/output | tee examples/output/final_check.txt
FINAL CHECK — examples/output/result.json
  PASS: case_id 原样保留 (case='SYNTH-EXAMPLE-001', result='SYNTH-EXAMPLE-001')
  PASS: 契约键全部存在 (5 键)
  PASS: 契约键非空或有书面解释
  PASS: status ∈ {partial, complete, failed} (当前: 'partial')
  PASS: status=partial 且 limits/uncertainty 说明了缺口
  PASS: deliverable 文件存在: examples/output/deliverable.md
VERDICT: PASS
(exit=0)
```

注意此处 status 诚实保持 **partial** 且判定 PASS: 图 1 图片文件未随包提供、数据缺口未闭合, 都在 limits/uncertainty 中书面化了。最终 result.json (含完整 stage_log) 见 `examples/output/result.json`。

## 8. 失败分支: 材料目录为空 → 诚实 failed

`examples/failcase/input/materials/` 为空目录, 而其 case.json 引用 notes.md 与 fig1.png:

```
$ python3 scripts/material_check.py --dir examples/failcase/input/materials --case examples/failcase/input/case.json --out-dir examples/failcase/output
INVENTORY: examples/failcase/output/material_inventory.json (0 文件)
SUMMARY  : examples/failcase/output/material_inventory.md
PROBLEMS (3):
  - 材料目录为空: examples/failcase/input/materials
  - case.json 引用缺失: [materials] notes.md
  - case.json 引用缺失: [materials] fig1.png

请将以下行粘贴进 result.json 的 limits (JSON 数组元素):
  "材料目录为空或不存在: 无任何可用输入材料, 内容工作无法进行。"
  "缺失材料: notes.md (case.json 字段 materials 引用, 但材料目录中不存在)。"
  "缺失材料: fig1.png (case.json 字段 materials 引用, 但材料目录中不存在)。"
(exit=1)
```

零材料 → 拒绝编造, 骨架 init 后把脚本打印的 limits 行原样写入, status 记 failed, 并写"失败说明件"作为 deliverable 占位:

```
$ python3 scripts/contract.py init --case examples/failcase/input/case.json --out examples/failcase/output/result.json
INIT OK: examples/failcase/output/result.json ... status       : partial
(exit=0)

$ python3 scripts/contract.py checkpoint --result examples/failcase/output/result.json --stage s0_contract \
    --note "材料盘点: 目录为空且 case.json 引用的 notes.md/fig1.png 均缺失; 无任何事实来源, 拒绝编造内容, status=failed。" \
    --set status='"failed"' --set 'limits=[...]' --set 'uncertainty=[...]' --set 'figures=["无: fig1.png 缺失, 未编造任何图件。"]'
CHECKPOINT OK: stage=s0_contract -> examples/failcase/output/result.json
(exit=0)

$ python3 scripts/contract.py checkpoint --result examples/failcase/output/result.json --stage s1_minimum \
    --note "写入失败说明件 deliverable_failed.md; preserved_facts 与 evidence_map 保持为空属有意为之: 零材料, 无事实可保全, 无证据可映射。" \
    --set deliverable='"deliverable_failed.md"'
CHECKPOINT OK: stage=s1_minimum -> examples/failcase/output/result.json
(exit=0)

$ python3 scripts/contract.py final_check --case examples/failcase/input/case.json --result examples/failcase/output/result.json --output-dir examples/failcase/output
FINAL CHECK — examples/failcase/output/result.json
  PASS: case_id 原样保留 (case='SYNTH-FAILCASE-001', result='SYNTH-FAILCASE-001')
  PASS: 契约键全部存在 (5 键)
  PASS: 契约键非空或有书面解释
  PASS: status ∈ {partial, complete, failed} (当前: 'failed')
  PASS: status=failed 且说明了失败原因
  PASS: deliverable 文件存在: examples/failcase/output/deliverable_failed.md
VERDICT: PASS
(exit=0)
```

要点: 即使是 failed, result.json 仍然契约完整、可解析、每条空缺有书面解释 — 这正是"诚实 partial/failed 优于虚假 complete"的落点。中间一次 final_check 曾 FAIL (preserved_facts/evidence_map 空且无解释、deliverable 缺失), 通过补写解释与失败说明件后转为 PASS, 说明 FAIL 输出可以直接指导修复。
