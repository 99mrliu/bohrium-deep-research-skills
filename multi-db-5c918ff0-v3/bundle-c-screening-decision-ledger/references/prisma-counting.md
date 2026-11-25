# 流量阶段定义与守恒不变量（prisma-counting.md）

本文件定义 `prisma_flow.json` 的阶段口径与守恒校验。口径是 **PRISMA 2020
流程图（Page et al., 2021, 系统综述报告规范）针对"离线多源候选集"场景的
改编**：原始 PRISMA 面向联网检索+全文评估的全流程，本技能只有题录级筛选，
因此只保留"识别→去重→初筛→排除（分原因）→纳入"主干，并将"全文获取/
全文排除"阶段替换为"边界待决/未判定"这一诚实口径。这是**改编用法**，
不与任何正式 PRISMA 计数口径对齐声明，也不引用任何虚构的计数规范。

## 阶段定义

| 阶段 | 字段 | 口径（全部由脚本实际计数） |
|---|---|---|
| 识别 identified | `records_identified` | 各来源材料解析出的**原始**记录数（per_source + total），来自 parse 的实际解析行数 |
| 去重移除 duplicates_removed | `duplicates_removed` | 最小去重吸收的原始记录数 = 原始总数 − 规范记录数；去重组明细在 dedup_summary.json |
| 初筛 screened | `records_screened` | `decision_ledger.jsonl` 的行数（每条规范记录至多一行最终判定） |
| 未判定 unjudged | `records_unjudged` | 规范记录数 − screened（无任何判定的记录；诚实暴露而非静默归零） |
| 排除 excluded | `records_excluded` | 账本中 decision=exclude 的行数；`per_criterion` 按标准 id 计数（一条 exclude 至少引用一个标准，引用多个时每个标准各计一次，故分标准合计可 ≥ total）；`per_stage` 按 prescreen_script / screen_model / borderline_resolution 分层 |
| 边界待决 borderline_pending | `borderline_pending` | 账本中 decision=borderline（未裁定）的行数 |
| 纳入 included | `records_included` | 账本中 decision=include 的行数 |

## 守恒不变量（flow 与 selfcheck 均断言）

1. `identified_total − duplicates_removed == canonical_records`
   （去重只吸收，不创造）。
2. `records_screened + records_unjudged == canonical_records`
   （每条规范记录要么有判定行，要么被显式计为未判定）。
3. `excluded + included + borderline_pending == records_screened`
   （每条账本行恰落三态之一）。

任一不变量不成立 → `conserved=false`，flow 退出 3，finalize 标 status=error。

## 为什么必须"重算而非断言"

挑战任务要求"排序/筛选依据"与"遗漏说明"。断言式计数（在报告里手写数字）
无法被检验，且在模型步骤出错（漏判、重复判定）时会与账本悄悄背离。本技能
的每个计数都是对账本行/去重组的 `len()` 结果；`records_unjudged` 与
`borderline_pending` 专门承接"遗漏说明"——它们非零时 finalize 必然
partial，绝不允许以 ok 掩盖未闭合的判定。
