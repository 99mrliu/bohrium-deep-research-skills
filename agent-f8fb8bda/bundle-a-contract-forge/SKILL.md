---
name: dr-contract-forge
description: 面向深度研究与文献综述（deep research, literature review）任务的交付契约工程 Skill，以确定性脚本锻造契约完备的 result.json，保证六要点齐备、状态诚实一致、中断可恢复。
---

# dr-contract-forge —— 深度研究交付契约工程

## 定位与重心

深度研究 Agent 的评测看最终交付。本 Skill 的重心是**下游交付契约工程**：无论检索与综合过程如何波折，最终写入 `/app/output/result.json` 的必须是契约完备、六要点齐备、诚实一致的产物，且任何中断都可从快照恢复。

机械可判定的检查全部下沉到三个确定性脚本（仅 Python3 标准库、无网络依赖），模型只做判断类工作。脚本以退出码门控：`0` 通过、`1` 门控违例（stdout 打印逐项失败清单）、`2` 用法/IO 错误。

## 安装布局

```
/skills/weekly-skill/
├── SKILL.md                      本手册
├── scripts/
│   ├── contract_init.py          阶段一：契约初始化
│   ├── contract_check.py         阶段五：交付总门（F1-F6）
│   └── checkpoint.py             阶段快照：save / list / recover
├── references/
│   ├── output_contract.md        契约字段语义、填写规范、诚实状态规则、change records
│   └── budget_protocol.md        64 请求 / 900 秒的五阶段分配与降级顺序
└── examples/                     合成示例（可一键跑通，含埋雷变例）
```

下文统一记 `SKILL_DIR=/skills/weekly-skill`，先执行：

```bash
SKILL_DIR=/skills/weekly-skill
```

## 五阶段流程协议（覆盖六要点）

六要点与 `result.json` 区块的映射（固定区块名，缺一不可）：

| 六要点 | result.json 区块 | 内容形态 |
|---|---|---|
| 问题拆解 | `problem_decomposition` | 子问题数组，每条含可检索的问句 |
| 检索覆盖 | `search_coverage` | 各来源/查询/命中/采用记录数组 |
| 证据回链 | `evidence_linkage` | 证据条目数组，每条含 `id`（E-编号）、`source_id`、`claim`、`locator` |
| 冲突证据 | `conflict_evidence` | 冲突主题数组，列出对立证据 id 与处置 |
| 综合结论 | `synthesis` | 结论文本，凡引用证据必须以 `[E-编号]` 回链 |
| 研究空白 | `research_gaps` | 未解问题与后续方向数组 |

另有 `sources`（每条含 `id`/`title`/`locator`）、`status`、`uncertainty`、`limitations`（`blocked` 时加 `blocked_reason`）。契约字段（由 case.json 的 `output_contract` 动态决定，禁止硬编码字段名）与上述固定区块并列于 `result.json` 顶层。

### 阶段一：契约初始化（脚本驱动，必先执行）

```bash
python3 "$SKILL_DIR/scripts/contract_init.py" --case /input/case.json --out /app/output
```

产出 `contract.json`（字段点路径清单 + 材料 SHA-256）、`result.json` 骨架（全部契约字段 `PENDING` 占位、六要点区块置空、`status="partial"`）、`budget_ledger.json`（64 请求 / 900 秒与五阶段配额）。case.json 缺失或损坏时脚本写出 `status=blocked` 的 result.json 并以 exit 2 退出——此时停止后续阶段，按 blocked_reason 报告。随后立即存第一份快照：

```bash
python3 "$SKILL_DIR/scripts/checkpoint.py" --out /app/output --work /app/work save s1-init
```

模型在本阶段只读 `contract.json`，记住契约字段清单与材料哈希，不手写任何字段名。

### 阶段二：问题拆解（模型判断，一次响应完成）

依据 task.md 与材料，把综述问题拆为可检索子问题，回填 `problem_decomposition`（数组，每条一句问句，标注对应契约字段）。通用做法：子问题之间正交、合取覆盖原问题；拆完即写盘，不占用额外响应。

### 阶段三：检索执行（模型判断，多轮）

按子问题检索材料与外部来源。通用做法：每轮检索后**立即**把查询、来源、命中数、采用数追加进 `search_coverage`，把采用文献追加进 `sources`（`id`/`title`/`locator` 三键齐全）；宁可少检索一轮，也要留足回填时间。检索覆盖要对应 `problem_decomposition` 的每个子问题。

### 阶段四：证据与综合（模型判断，集中回填）

为每条关键主张建立证据条目回填 `evidence_linkage`（`id` 取 `E-01`、`E-02`…，配 `source_id` 与 `locator` 精确到页/段）；对立结论回填 `conflict_evidence`（不得只取支持面）；`synthesis` 文本中凡引用证据一律写 `[E-编号]`，且编号必须存在于 `evidence_linkage`；未解问题回填 `research_gaps`。随后回填契约字段，按真实完成度设定 `status`（判定规则见 references/output_contract.md）并快照：

```bash
python3 "$SKILL_DIR/scripts/checkpoint.py" --out /app/output --work /app/work save s4-synthesis
```

### 阶段五：交付门（脚本驱动）

```bash
python3 "$SKILL_DIR/scripts/contract_check.py" --case /input/case.json --out /app/output
```

- exit 0：打印 `GATE: PASS`，交付。
- exit 1：stdout 逐项列出 `F 编号 + 具体问题`，逐条修复后重跑本命令；修复前先 `checkpoint save`，改坏可 `recover`。
- exit 2：用法/IO 错误，检查路径与 JSON 合法性。

中断恢复：任何时刻可用下列命令盘点与回滚，配合"先存 partial 再迭代"：

```bash
python3 "$SKILL_DIR/scripts/checkpoint.py" --work /app/work list
python3 "$SKILL_DIR/scripts/checkpoint.py" --out /app/output --work /app/work recover s4-synthesis
```

## 门控规则 F1-F6（contract_check.py）

- **F1** `case_id` 与 case.json 完全一致。
- **F2** `output_contract` 全部顶层字段存在且非 `"PENDING"`；空值仅 `partial` 下允许，且 `limitations` 中必须有提及该字段名的条目逐项声明原因；`completed` 下空字段判负。
- **F3** 六要点区块齐备；`completed` 时全部非空。
- **F4** 诚实一致性：`completed ⇒ sources 非空`；`partial ⇒ limitations 非空`；`blocked ⇒ blocked_reason 非空`；`status` 取值必须合法。
- **F5** `sources` 每条含 `id`/`title`/`locator` 三个非空字符串键。
- **F6** `synthesis` 中出现的全部 `E-数字` 编号（含 `evidence_ids` 列表项）必须存在于 `evidence_linkage` 的 `id` 集合。

`status=blocked` 时 F2/F3/F6 豁免，F1/F4/F5 仍检查。

## 退出码约定（全部脚本一致）

| 退出码 | 含义 | 处置 |
|---|---|---|
| 0 | 通过 / 成功 | 进入下一步 |
| 1 | 门控违例 / 操作失败 | 读 stdout 逐项清单，修复后重跑 |
| 2 | 用法 / IO 错误 | 检查参数、路径、JSON 合法性 |

## 诚实状态三条铁律（细则见 references/output_contract.md）

1. `completed`：六要点区块与 sources 全部非空，契约字段无空值。
2. `partial`：允许契约字段留空数组/空串，但 `limitations` 必须**逐字段**写明原因；`uncertainty` 不得为空。
3. `blocked`：必须有 `blocked_reason` 说明缺什么、停在哪。

任何情况下不得为通过门控而填充无依据内容；宁可 `partial` 也不伪造 `completed`。

## 预算纪律（细则见 references/budget_protocol.md）

先跑脚本骨架再思考；一次响应多做事（拆解+回填一次完成）；每阶段结束立即 `checkpoint save`；超支前按 budget_protocol.md 的降级顺序收缩，最终以诚实的 `partial` 交付兜底。

## 确定性说明

`contract_init.py` 与 `contract_check.py` 的产物/判定不含随机数与时间戳，同一输入重复运行结果一致。`checkpoint.py` 的 `manifest.json` 含 `saved_at_epoch` / `saved_at_local` 时间戳字段，仅为人读、不参与任何门控判定（见脚本 docstring）。

## 自检

bundle 自带合成示例（合成示例 / synthetic），一键跑通全流程并验证门控开火：

```bash
bash "$SKILL_DIR/examples/run_example.sh"
```

预期：`good_result` 过门 exit 0；`bad_result` 过门 exit 1 且输出含 F2、F4、F6；checkpoint 的 save/list/recover 全部 exit 0；末尾打印 EXPECTED vs ACTUAL 汇总，全部一致时脚本整体 exit 0。
