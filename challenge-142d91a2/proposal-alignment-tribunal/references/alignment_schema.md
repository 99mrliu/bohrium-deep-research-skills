# 七要素对齐矩阵 Schema（alignment_matrix.json）

对齐矩阵是开题报告的**单一事实源**：先填矩阵、过裁定，再按矩阵展开成稿。
矩阵为 JSON 对象，六个实体表：`research_questions` / `objectives` / `steps` /
`validations` / `outcomes` / `risks`。所有 `id` 全局唯一，引用一律用 id，不用名称。

## 1. RQ（研究问题，1–3 个）

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 形如 `RQ1` |
| `statement` | 是 | 问句形式，变量与总体明确 |
| `decision_criterion` | 是 | **判断标准**：什么结果支持、什么结果拒绝该问题的候选答案。缺此字段 RQ 不可证伪，裁定 fail |

RQ 超过 3 个说明问题未收敛；0 个说明没有科学问题只有工作清单。两种都 fail。

## 2. OBJ（研究目标）

每个 OBJ 通过 `rq_id` 挂到**唯一** RQ。四个必填考核字段缺任一个即 fail：

| 字段 | 说明 |
|---|---|
| `metric` | 考核指标：可量测的变量名（不是「提升性能」这类方向词） |
| `threshold` | 判定阈值：达到/超过多少算达成 |
| `threshold_basis` | **阈值依据**：前期数据、文献值或工程约束的具体出处；「经验估计」不算依据 |
| `time_point` | 考核时间点：第几个月/哪个里程碑判定 |

另含 `sample_or_control`（样本量与对照设置）。目标句里出现「显著提高」「明显改善」而无阈值与依据，是开题稿最常见的空话形态，本表从结构上禁止。

## 3. STEP（技术路线步骤）

| 字段 | 说明 |
|---|---|
| `serves` | **本步骤服务的 OBJ id 列表，至少 1 个**。空列表 = 孤儿步骤（做了不服务任何目标的工作），fail |
| `input` / `output` | 步骤的输入物与产出物（数据、样品、模型、报告） |
| `depends_on` | 前置 STEP id 列表，用于暴露时序矛盾 |

## 4. VAL（验证方式）

每条 VAL 挂一个 OBJ（`obj_id`）。必填 `control`（与什么对照）与
`statistical_criterion`（统计判据：检验、显著性水平、效应量或模型比较准则）。
**每个 OBJ 至少 1 条 VAL**——没有验证方式的目标无法判定达成与否。

## 5. OUT（预期成果）

每个 OUT 挂一个 OBJ（`obj_id`），必填 `acceptance_criterion`（验收判据：数据完整性、
精度、覆盖范围的可检查条件）。**每个 OBJ 至少 1 个 OUT**——没有成果的目标是无产出承诺。

## 6. RSK（风险）

| 字段 | 说明 |
|---|---|
| `affects` | 受影响的 STEP/OBJ id 列表 |
| `trigger_signal` | **触发信号**：可观察的启动条件（如「连续两周无法进场」），不是「如果发生风险」 |
| `fallback` | 备选方案：信号触发后切换到什么做法 |
| `decision_point` | 决策时点：最晚在何时按信号做切换决定 |

三字段缺任一个即 fail——缺触发信号的风险是祈祷，缺备选的是抱怨，缺时点的是马后炮。

## 7. 合取式纳入条件（裁定规则一览）

| 规则 | 条件（全部满足才 pass） |
|---|---|
| `RQ-NUM` | 1 ≤ RQ 数 ≤ 3 |
| `RQ-CRIT` | 每个 RQ 的 `decision_criterion` 非空 |
| `RQ-COVER` | 每个 RQ 被 ≥1 个 OBJ 引用 |
| `OBJ-FIELDS` | 每个 OBJ 的 metric/threshold/threshold_basis/time_point 均非空 |
| `STEP-SERVE` | 每个 STEP 的 `serves` ≥1 个 OBJ |
| `VAL-FIELDS` | 每条 VAL 的 control 与 statistical_criterion 非空 |
| `OUT-FIELDS` | 每个 OUT 的 acceptance_criterion 非空 |
| `OBJ-COVER` | 每个 OBJ ≥1 条 VAL 且 ≥1 个 OUT |
| `RSK-FIELDS` | 每个 RSK 的 trigger_signal/fallback/decision_point 均非空 |
| `REF-INT` | 所有 id 引用（rq_id、serves、depends_on、obj_id、affects）指向存在的实体；无重复 id |

机器裁定见 `scripts/alignment_check.py`；任何一条 fail 即 `gate_pass: false`，退出码 1。
规则语义与修复口径见 `references/fail_playbook.md`。
