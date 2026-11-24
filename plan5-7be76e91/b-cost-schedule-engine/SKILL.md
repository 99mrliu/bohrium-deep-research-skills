---
name: cost-schedule-engine
description: >-
  全口径成本与时间核算引擎：把实验方案比较中的「钱与工时」做成可复算的确定性台账。
  当任务需要比较多个候选实验方案的总成本（机时费/耗材/人力/外送，区分一次性投入与按次消耗）、
  全周期时间（样品准备/设备排期/执行/表征排队/分析/返工期望），并做预算/截止门判定与
  成本-时间 Pareto 选择时触发。模型只负责从真实材料抽取条目并挂来源，全部算术、校验、
  门判定由 stdlib Python 脚本完成。不适用于：无需量化成本/排期的纯文献综述、无候选方案
  比较的单方案设计、以及材料中完全没有价格/工期依据且不允许标注假设的场景。
---

# cost-schedule-engine — 全口径成本与时间核算引擎

## 解决什么问题

题目点名的典型失败，本 Skill 逐条做机检：

1. **时间只算实验执行**：漏掉样品准备、设备排期、表征排队和返工。
2. **成本只写耗材单价**：漏掉机时费与人力工日。
3. **不区分一次性投入与按次消耗**：重复次数 runs 的放大效应丢失。
4. **拍脑袋工时/单价**：缺数量或单价时静默当 0，无法复核。
5. **转录与浮点误差**：手抄数字、float 尾差（如 0.1×7=0.7000000000000001）。

## 分工（不可逾越）

- **模型**：读真实文件 → 抽取条目（cost_items / time_items）→ 每条挂
  `source`/`locator` → 裁决异常 → 撰写 result.json 文字。模型**不做算术**。
- **脚本（scripts/，纯 stdlib，确定性）**：全部加乘算术（decimal.Decimal）、
  单位换算、返工期望、预算/截止门、Pareto 前沿与支配关系、双跑一致性。
  脚本不知道物理含义，只做口径校验与算术。

## 工作流（严格按序）

### 步骤 0：读契约，尽早落盘

1. 读 `/input/case.json` 与 `/input/task.md`：提取 `case_id`、
   `output_contract` 的**全部原始字段名**（逐键，不漏不造）、`budget`、
   `deadline_days`、`workday_hours`、rubric 权重、硬阈值。
2. 列出 `/input/` 真实材料清单（论文 PDF、前瞻性价格/预订契约、候选方案文档），
   **逐个打开读内容**，不得凭文件名臆测。契约是组织方构造的前瞻情景，数字
   不得说成实测。
3. **尽早**把骨架 result.json 写到 `/app/output/`：填入 case_id、
   output_contract 全键（值先为 null）、`status: "partial"`、`sources: []`、
   `uncertainty`、变更记录。之后每完成一步增量更新。

### 步骤 1：模型为每方案填 plan_record.json

按 `references/plan_record_schema.json`（口径定义见 `references/cost_model.md`
与 `references/time_model.md`）为每个候选方案填一份 plan_record：

- `cost_items[]`：`name / category / basis / quantity / unit / unit_price /
  runs / source / locator`。category ∈ {equipment_time, consumable, labor,
  outsourcing, other}；basis ∈ {one_time, per_run}。
- `time_items[]`：`phase / duration / unit / [rework_probability,
  rework_cost] / source / locator`。phase ∈ {sample_prep, booking_wait,
  execution, characterization_queue, analysis, rework_buffer}。
- `workday_hours`：plan 顶层或 case.json 必须有一处显式给定（1 day = ? 小时）。
  材料没写就把「工时换算」记入确认项，并按契约给定值继续；**脚本缺省会 exit 2
  而不是替你编一个数**。
- 材料里查不到的 quantity/unit_price：**留缺**，让脚本 exit 3 进缺陷清单，
  再决定是标注假设（写入 assumptions 与 uncertainty）还是列为确认项——
  绝不自己编一个价格填进去。

### 步骤 2：脚本核算（模型零算术）

```bash
python3 scripts/cost_ledger.py --plan plan_record_P1.json --out-dir work/ledger
python3 scripts/time_model.py --plan plan_record_P1.json --case /input/case.json \
    --ledger work/ledger/ledger_P1.json --out-dir work/ledger
```

产出每方案 `ledger_<P>.json/md`（五口径小计、一次性 vs 按次分列、按 runs
折算总计、缺陷清单）与 `time_<P>.json/md`（逐阶段台账、labor_hours 与
elapsed_days 分列、gates 明细、gate_status）。

### 步骤 3：Pareto 与预算/截止门

```bash
python3 scripts/pareto.py --case /input/case.json --out-dir work/pareto \
    --plan P1:work/ledger/ledger_P1.json:work/ledger/time_P1.json \
    --plan P2:work/ledger/ledger_P2.json:work/ledger/time_P2.json \
    --plan P3:work/ledger/ledger_P3.json:work/ledger/time_P3.json
```

推荐规则为字典序，且 `rule_source` 必声明：先 gate pass → 再 Pareto 前沿 →
再按 case rubric 权重（`rule_source=case_rubric`）或默认成本优先
（`rule_source=default_cost_first`）决胜。脚本直接读 ledger/time 产物，
不手抄数字。

### 步骤 4：模型写 result.json

更新 `/app/output/result.json`（增量改，不推翻重来）：

- `case_id` + `output_contract` 全部原始字段逐键填值。
- **七类字段**（评分完整性）：假设 / 变量 / 对照 / 步骤 / 参数 / 资源 /
  判读标准。资源类直接引用台账数字（ledger/time/pareto 文件路径 + 关键值）；
  判读标准写清 gate 判定与 Pareto 规则来源。
- **依据与风险**：每个关键数字挂 source/locator；风险单列（排期波动、返工
  概率不确定性、前瞻性契约非真实报价等）。
- **确认项**：safety / ethics / equipment_availability / expert 四类，
  状态用 pending/confirmed 标注；**pending 的不得写成可执行事实**
  （如"设备可用"未经确认只能写"待设备管理员确认"）。
- 诚实 `status`（complete/partial/blocked）、`sources`、`uncertainty`、
  变更记录（每次增量更新追加一条）。
- 成本时间台账引用：列出 ledger/time/pareto 产物路径。

## 脚本用法与退出码

| 脚本 | 用途 | 关键参数 |
|---|---|---|
| `scripts/cost_ledger.py` | 成本台账 | `--plan --out-dir` |
| `scripts/time_model.py` | 时间模型+门 | `--plan [--case --ledger] --out-dir` |
| `scripts/pareto.py` | Pareto+推荐 | `--plan ID:LEDGER:TIME（≥2） [--case] --out-dir` |
| `scripts/selfcheck.py` | 端到端自查 | `[--keep-dir]` |

退出码统一：**0**=成功；**2**=输入/用法错误（文件不存在、JSON 非法、
缺 workday_hours、有 budget 却无 --ledger 等）；**3**=质量门/校验拦截
（缺陷清单或门明细写 stdout，能写的产物仍写出）。`--help` 均可用。

## 输入输出说明

- 输入：`plan_record.json`（模型抽取）、`case.json`（契约）、ledger 产物
  （供 time_model 判预算门、供 pareto 取数）。
- 输出：`ledger_<P>.json/md`、`time_<P>.json/md`、`pareto.json/md`。
  JSON 为机器可读权威版（金额/时长为十进制字符串），md 为人读台账。
  确定性保证：无时间戳、无绝对路径、无随机数，同输入双跑逐字节一致。

## 异常分类处置

| 异常 | 检测者 | 退出码 | 处置 |
|---|---|---|---|
| 缺 quantity / unit_price | cost_ledger | 3 | 缺陷清单；模型回查材料或记假设/确认项，绝不静默当 0 |
| 负值/非数字/非法 category/basis/phase/unit | cost_ledger / time_model | 3 | 修正抽取 |
| rework_probability 越界 [0,1] 或与 rework_cost 不成对 | time_model | 3 | 修正抽取 |
| 缺 workday_hours | time_model | 2 | 回 case/plan 补显式换算，不臆造 |
| 有 budget 无 --ledger | time_model | 2 | 先跑 cost_ledger |
| 耗材/总成本超预算 | time_model 预算门 | 3 (over_budget) | 诚实上报，给出压缩项建议但标 pending |
| 设备排期冲突/超截止 | time_model 截止门 | 3 (past_deadline) | 上报并给换设备/加急等备选（标 pending） |
| 全部方案超预算/超截止 | pareto | 3 (all_infeasible) | **不推荐任何方案**，如实写 status 与限制，请组织方裁决 |
| 材料缺失/无法判断 | 模型 | — | result.json 记 partial + uncertainty，不编造 |
| 脚本运行失败 | 脚本 | 2/3 | 读 stdout 缺陷清单修复后重跑，不绕过 |

## 自查方法

```bash
python3 scripts/selfcheck.py    # exit 0 才允许交付
```

覆盖：好例 exit 0、三份 booby-trap 各 exit 3 且缺陷精确命中（缺单价 /
over_budget / 概率越界）、P3 被 P1 支配命中、推荐与 rule_source 非空、
Decimal 精确断言（0.1×7="0.7"）、双跑字节一致。也可用
`python3 scripts/selfcheck.py --keep-dir <dir>` 保留产物人工目检。

## 适用边界

- 只做成本/时间的核算与选择支持；科学可行性、安全性判断不在本引擎内，
  由模型依据论文材料完成并记入确认项。
- 契约数字是前瞻情景值，结果中必须注明"非实测、非真实报价"。
- 多币种、税率、通胀、设备折旧不在口径内；出现时先由模型统一口径并注明
  依据，否则列确认项。
- 脚本不做优化求解，只做给定方案的核算、门判定与 Pareto 比较。

## 合成示例说明

`examples/` 全部为**合成示例 / SYNTHETIC EXAMPLE**：虚构契约文本 +
P1（便宜但慢）/ P2（贵但快）/ P3（被 P1 支配）三份 plan_record + 三份
booby-trap 负例（缺单价 / 超预算 / 概率 1.4），`examples/outputs/` 是
`examples/README.md` 中命令序列真实跑出的产物。示例不代表真实案例结果。
