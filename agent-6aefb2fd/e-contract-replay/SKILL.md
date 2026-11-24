---
name: contract-replay-delivery
description: 交付契约与第三方复算取向的多步骤数据分析规程。contract_seal.py 以 partial-first 契约镜像管理 result.json：begin 立即占位、fill 拒绝悬空路径、raise 按五类异常分类法登记、seal 在 case_id/字段/路径/exceptions 不全时拒绝 success；replay_check.py 站在不信任任何自报的第三方立场，从 /input 原始数据独立重算描述统计池，验证行数口径与报告中每个数字的可复算性，复核不过不许 seal。适用于评分强调"结果可核验、异常不静默、诚实 partial"的科研表格分析案例。
---

# Contract-Replay —— 先保契约，再经复算，最后封口

核心主张：**交付质量的下限由契约决定，上限由复算决定。**
本 Skill 的重心在交付端：result.json 是逐字段管理的契约而非事后补写的附件；
交付前必须过一次"第三方复算"——复核器从原始数据独立重算，报告中的每个数字
都要么有自报证据、要么能被复算复现。分析本体（导入/清洗/统计/绘图）按通用
要求完成，但只有复算通过的成果才允许 seal 为 success。

## 运行契约（评测环境）

- 输入 `/input/case.json`（`case_id`、`output_contract.fields`）、`/input/task.md`。
- 工作于 `/app/work`，交付入 `/app/output`；`result.json` 含原样 `case_id` + 全部
  契约字段 + `status`/`sources`/`uncertainty`。
- 预算约 8–12 次请求；**begin 必须在第一次分析前执行**（任何中途崩溃都留下
  可评分的 partial）。

## 流程

**0. 契约占位。**

```
python3 /skills/weekly-skill/scripts/contract_seal.py begin \
    --case /input/case.json --out /app/output/result.json
```

同时生成 `/app/work/contract_checklist.md` 待填清单。读 task.md，记下任务专项。

**1. 分析本体（通用要求）。**

- 导入：pandas 读 CSV/SQLite；双源案例核对一致性并声明主源（不一致写 uncertainty）。
- 清洗：完全重复删（保留首条）记数；缺失 ≤5% 中位数/众数填补、>5% 保留声明；
  异常 1.5×IQR 只标记；行数变化写 `/app/output/cleaning_evidence.json`
  （含 initial_rows/final_rows）；cleaned 表存 `/app/output/cleaned_data.csv`。
- 统计：前提先行（Shapiro+Levene→参数/非参），结果存 `/app/output/statistics.json`
  （含方法、p、效应量、样本量）；区分度排序/回归按任务要求。
- 绘图：matplotlib Agg 150dpi → `/app/output/figures/*.png` + manifest。
- 报告：`/app/output/report.md`，数字只引用统计 JSON 或可复算的描述统计。
- 每完成一件产物立即 `fill`（路径不存在会被拒绝——这是特性）：

```
python3 /skills/weekly-skill/scripts/contract_seal.py fill --out /app/output/result.json \
    --set cleaned_data=/app/output/cleaned_data.csv --set statistics=/app/output/statistics.json
```

- 每遇异常立即 `raise`（分类法见 `references/replay_method.md` §2）：

```
python3 /skills/weekly-skill/scripts/contract_seal.py raise --out /app/output/result.json \
    --kind capability_limit --detail "scipy 不可用，推断检验未执行"
```

**2. 第三方复算（本重心）。**

```
python3 /skills/weekly-skill/scripts/replay_check.py --input /input --output /app/output
```

- 复核项与容差见 `references/replay_method.md` §1：R1 契约完整、R2 行数口径、
  R3 报告数字复算池溯源。
- 退出码 7 = 复核不过：**先修复再 seal**；R3 报无源数字时，要么改回可复算的值，
  要么把产生它的证据 JSON 落到 /app/output（复核器会读入）。
- `replay_report.json` 自动写入 /app/output，是 quality_evidence 的核心件。

**3. 封口。**

```
python3 /skills/weekly-skill/scripts/contract_seal.py fill --out /app/output/result.json \
    --set figures='["/app/output/figures/fig_x.png"]' --set report=/app/output/report.md \
    --set quality_evidence='["/app/output/replay_report.json","/app/output/cleaning_evidence.json"]' \
    --set exceptions="无未解释异常"
python3 /skills/weekly-skill/scripts/contract_seal.py seal \
    --case /input/case.json --out /app/output/result.json --status success
```

seal 拒绝时：按提示修复；无法修复 → 对应 `raise` + `--status partial` 诚实交付。

## 异常处置表

| 情形 | 处置 |
|-|-|
| fill 拒绝悬空路径 | 先把产物真实落盘；不伪造路径 |
| raise 的 kind 不在分类法 | 五类必居其一；选最接近的并在 detail 说明 |
| replay R2 报行数变多 | 几乎必为拼接事故；检查 cleaned 生成代码 |
| replay R3 报无源数字 | 改回可复算值或补充证据 JSON，重跑到过 |
| seal 拒绝 success | 修复 / raise / partial，三选一，禁止绕过 |
| 时间不足 | 已 begin 的 partial + 已 fill 的产物 + raise 说明，即合法交付 |

## 资源

- `scripts/contract_seal.py` — 契约封口器（begin/fill/raise/seal，本重心）。
- `scripts/replay_check.py` — 第三方复算复核器（本重心）。
- `references/replay_method.md` — 复核方法论、容差、异常分类法、交付顺序纪律。
- `examples/make_example.py` + `examples/README.md` — 合成示例（含复算抓获
  无源数字的演示）。

## 边界与不适用

- 复算池为描述统计级；推断量的方法学复核（检验选择是否恰当）不在 R3 范围。
- cleaned 表列裁剪/重命名剧烈时 R2 降级为提示性通过（detail 记录）。
- 本 Skill 不提供统计与绘图引擎；需要前提检验决策树时按通用规则自行实现并
  在 statistics.json 中记录依据。
