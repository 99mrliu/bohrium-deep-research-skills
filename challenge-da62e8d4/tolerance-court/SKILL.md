---
name: tolerance-court
description: 事前容差与统计裁决。当需要把复现/候选数值方法的输出与论文报告指标按容差比较、并用多种子观测区分“数值随机波动”与“方法性系统差异”时触发：先注册容差（防事后篡改），再实际运行，最后用判定代数给出 within_tolerance / stochastic_fluctuation / systematic_deviation / insufficient_runs / not_comparable / missing 的机器判定与归因建议。适用于“论文复现与方法验证”中参数/代码/指标验算与差异归因的子场景。
---

# tolerance-court：事前容差与统计裁决

## 用途与适用条件

本 Skill 只做一件事、并把它做硬：**“对得上 / 对不上”不是看一眼差多少，而是一个必须先注册判定规则、再用多种子观测做统计分解的裁决过程。**

适用条件：
- 有论文报告值（或其缺失需显式登记）与容差需求；
- 有一份或多份候选数值方法代码的**多种子/多次运行输出**；
- 需要判定差异是随机波动（numerical noise）还是方法性系统偏差（systematic deviation）。

不适用（不是本 Skill 重心，请配合其他工具或人工完成）：环境取证、PDF 引文门核验、报告渲染、论文原文数值的权威性裁决。

## 核心思想

1. **先注册，后运行。** 容差文件（tolerances.json）必须先于任何候选方法的运行写入磁盘，带 UTC 时间戳与 targets 的 SHA-256。看到结果之后再写或改容差 = 事后篡改，本 Skill 用 mtime 校验把它抓出来（preregistration_violation）。
2. **看到结果后不放宽容差。** 确需重建容差文件必须 `--force` 并留下旧文件哈希与原因（change_records），且裁决时该记录会随报告一并呈现。
3. **偏差 = 随机分量 + 系统分量。** 单个数字不能裁决。n 次观测 → n / median / mean / spread(max−min) / MAD → 按判定代数分类（见 references/tolerance.md 真值表）。机器只给判定与 attribution_hint（numerical_noise / systematic / none），**最终归因由 agent 结合证据决定**。

## 铁律

1. **容差先写后跑。** 任何候选代码运行之前必须已生成 tolerances.json；违反时裁决自动标 `preregistration_violation=true`，全部结论可信度降级并如实写入 result.json。
2. **论文值未报告 → `not_comparable`，不得编造。** 论文只给图不给数，或材料根本没有该指标：登记 not_comparable，可注明“从图估读”并标低置信，绝不允许把估读值写成论文报告值。
3. **n=1 的随机（stochastic）指标只能 `insufficient_runs`。** 单点观测无法谈波动；n=2 可以判但附加 insufficient_runs 告警。不得用单种子结果宣称“复现成功/失败”。
4. **result.json 全字段诚实。** status ∈ success / partial / unable / refused；原始数据或作者仓库缺失是**预期情况**，必须显式登记而非掩盖；每一项结论带来源定位与不确定性。
5. **预算纪律。** 总预算约 64 次模型请求 / 900 秒：容差注册与裁决是廉价脚本，把预算留给“实际运行候选代码”和“差异归因”，不要在反复润色报告上烧请求。
6. **组织方合成代码 ≠ 作者原代码。** 合成数据上判得 within_tolerance，只能写“候选实现与合成目标在容差内一致”，**不能写成论文数值复现**。

## 逐条命令流程（$SKILL 指代技能目录，评测时为 /skills/weekly-skill）

```bash
# 0. 读 /input/case.json 与 /input/task.md，提取指标清单与案例给定容差（若有）
# 1. 编写 targets.json（见“输入输出”），放进 /app/work
# 2. 事前注册容差——必须在任何候选代码运行之前
python3 $SKILL/scripts/preregister.py \
    --targets /app/work/targets.json \
    --out /app/work/tolerances.json
#    随机性指标确需放大容差时：--k 2 --rationale "写下理由"（没有理由不许放大）

# 3. 实际运行两份候选方法（多种子），日志统一放 /app/work/runs/
#    每次运行把观测值与日志路径记入 observations.json

# 4. 裁决（--runs 用于 mtime 防篡改校验）
python3 $SKILL/scripts/adjudicate.py \
    --tolerances /app/work/tolerances.json \
    --observations /app/work/observations.json \
    --out /app/work/adjudication \
    --runs /app/work/runs
echo "exit=$?"   # 0 全通过/不可比；1 有系统偏差/超差/missing/违规；2 结构错误

# 5. 读 /app/work/adjudication/comparison.json 与 comparison.md，
#    把判定、preregistration_violation、change_records、不确定性
#    如实汇总进 /app/output/result.json（含 case_id 与 output_contract 全部字段）
```

## 输入输出

### targets.json（手写，preregister.py 的输入）
JSON 数组，每项字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | 字符串 | 指标名，全局唯一 |
| `paper_value` | 字符串或 null | 论文报告值**原文**（如 `"0.152"`、`"72.1"`、`"1.2e3"`、`"1200"`）；未报告用 null |
| `unit` | 字符串 | 单位，可空 |
| `case_tolerance` | 数值或 null | 案例给定容差；非 null 时**逐字优先** |
| `aggregation` | `mean`/`median`/`single` | 论文口径的聚合方式（判定以 median 为主，此字段随档记录） |
| `kind` | `deterministic`/`stochastic` | 有无随机性（采样、随机初始化、shuffle 等） |

### tolerances.json（preregister.py 的输出）
含 `created_at`（UTC ISO）、`targets_sha256`、`k`、`change_records`，以及每项的 `tolerance_abs` / `tolerance_rel` / `derivation`（`case_given` / `half_ulp` / `none`）/ `reason` / `k_applied` / `rationale`。

### observations.json（手写汇总，adjudicate.py 的输入）
```json
{"方法名": {"指标名": {"values": [0.149, 0.151, 0.150], "logs": ["runs/a_seed1.log"]}}}
```
`values` 为该指标各次运行的观测值；空数组判 `missing`。`logs` 为对应运行日志路径（参与 mtime 校验）。

### comparison.json / comparison.md（adjudicate.py 的输出）
每项：方法 / 指标 / 论文值 / n / median / mean / spread / MAD / deviation(abs,rel) / 容差 / **judgment** / alerts / attribution_hint；全局含 `preregistration_violation`、容差文件时间戳与 change_records、汇总计数。判定代数与真值表见 references/tolerance.md。

## 异常处理表

| 情形 | 处理 |
|---|---|
| 论文只给图不给数 | 判 `not_comparable`；如必须量化，注明“从图估读、低置信”，且不得写成论文报告值 |
| 材料/原文完全没有该指标 | `paper_value=null` → `not_comparable`，并在 result.json 登记缺失 |
| 原始数据 / 作者仓库缺失 | **预期情况**：在 result.json 显式登记缺失项，用组织方合成代码/数据运行，结论措辞限定为“候选实现与合成目标的一致性” |
| preregistration_violation（容差不早于日志） | 退出码 1；全部结论可信度降级；如实记录于 comparison 与 result.json，不得回滚文件掩盖 |
| 需要修改已注册容差 | `preregister.py --force --force-reason "原因"`；旧文件 sha256 进入 change_records，随报告公开 |
| 单种子（stochastic n=1） | 判 `insufficient_runs`；补跑种子，不得用单点下结论 |
| 某方法观测全失败 | 该指标 `values=[]` → `missing`；result.json 相应 status 至多为 partial |
| 观测里出现未注册指标 | 判 `not_comparable` + `unregistered_metric` 告警；不得现编容差 |
| 两份候选方法结论冲突 | 各自独立裁决；在 result.json 并列呈现，不归并为单一结论 |

## 运行契约（评测环境）

- 输入：`/input/case.json`（含 `case_id` 与 `output_contract` 字段清单）、`/input/task.md`，材料按题目提供（真实 PDF 论文；两份候选数值方法代码；原始数据/作者仓库缺失为预期）。
- 工作目录：`/app/work`（targets/tolerances/observations/runs/ 均放这里）。
- 最终产物：`/app/output`，**必须含 `result.json`**——含 `case_id` 与 `output_contract` 全部字段、诚实 `status`（success/partial/unable/refused）、每项结论的来源定位（文件/表/页/运行日志路径）、不确定性说明、变更记录（含本 Skill 的 change_records 与 violation 标记）。
- 中途失败也要产出 result.json：`status` 如实写 partial/unable，已完成部分与卡点写清楚，**禁止编造数据**。
- 预算：约 64 次模型请求 / 900 秒，3 个固定案例，官方 DeepSeek Harness 自动运行。

## 最小合成示例

以下端到端示例是**合成示例（synthetic），非正式案例结果**，仅验证工具链：

```bash
$SKILL/examples/run_example.sh /tmp/tc-demo
# 依次执行：preregister → adjudicate → 打印 comparison.md
```

`examples/input/targets.json` 覆盖 4 类指标（case_given 容差、half_ulp 小数、科学计数、stochastic），`examples/input/observations.json` 的两个候选方法覆盖 within_tolerance / stochastic_fluctuation / systematic_deviation / not_comparable / missing / insufficient_runs 六种判定；预期输出见 `examples/expected/`（时间戳字段以实际运行为准）。

## 限制与自查

**限制**
- half_ulp 只按书写有效数字推导：整数 `"1200"` 取 ±0.5（个位），若论文实际只保留 2 位有效数字，应改用 `case_tolerance` 显式登记。
- 判定代数是机械规则：小样本下 stochastic_fluctuation 与 systematic_deviation 的边界（3×spread）是启发式；attribution_hint 不是最终归因。
- mtime 校验只能发现“容差晚于日志”这一类篡改，不能证明容差内容本身合理。
- 判定以 median 为主；论文若用 mean 口径，agent 应结合 aggregation 字段自行评估口径差。

**交付前自查清单**
1. tolerances.json 的 created_at 早于所有 runs/ 日志 mtime？（adjudicate 已校验，violation=false？）
2. 每个指标的容差理由（reason 字段）能逐字读出来、且优先使用 case_given？
3. stochastic 指标 n≥3？n=1 是否老老实实判了 insufficient_runs？
4. 论文未报告项是否全部 not_comparable、没有任何编造值？
5. result.json 是否含 case_id、output_contract 全字段、来源定位、不确定性、change_records / preregistration_violation？
6. 措辞是否把“合成目标在容差内一致”与“论文数值复现”严格区分？
