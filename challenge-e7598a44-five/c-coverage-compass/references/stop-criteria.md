# 停止判据的精确语义（measure.py 的判定依据）

停止决定是对"还要不要继续找证据"的可复核回答，不是感觉。全部判据都能从
coverage_report.json 的数字复算。

## 先定义：单条证据怎么算"可用"

对子问题 SQ 与记录 R：

1. **term_hit**：SQ 的全部 must_terms 且（any_terms 非空时）至少一个 any_term
   命中 R 的 标题+摘要+期刊（小写子串匹配）。
2. **usable**：term_hit 且 R 在 SQ 的 year_window 内（无窗则恒真；R 缺年份按在窗
   处理但计入 metadata_missing）且 R 未带 conflict_opinion 夹具标记。
3. **conflicted**：term_hit 且在窗但带 conflict_opinion —— 登记为争议证据，
   计入矩阵但不计入可用数，不做学术裁决。
4. **out_of_window**：term_hit 但年份出窗 —— 是"放宽窗口可得"的潜在证据，
   也是边际收益估计的来源。

## 充分性分级（逐 SQ）

| 分级 | 条件 | 含义 |
|-|-|-|
| sufficient | usable ≥ 3 | 该子问题证据足够，接受 |
| thin | usable ∈ {1, 2} | 有证据但单薄，交付时必须声明 |
| starved | usable = 0 | 零可用证据，不能靠流程自愈 |

阈值 3 写在 measure.py 顶部 `SUFFICIENT_MIN`，是声明式单一事实来源，可按赛制调整。

## 缺口分类（非 sufficient 的 SQ，诊断为什么不够）

按优先级判定，取第一个命中的类别：

| 类别 | 条件 | 处置提示 |
|-|-|-|
| no_records | raw_term_hits = 0 | 快照里根本没有相关记录 → 只能人工扩展检索源 |
| out_of_window | 可用=0 且 conflicted=0 且出窗>0 | 证据都在窗外 → 检查窗口是否过严 |
| only_conflicted | 可用=0 且 conflicted>0 | 证据全是争议意见 → 必须人工，脚本不裁决 |
| metadata_missing | 可用>0 且全部缺年份/DOI | 有证据但无法核验归属 → 归属降级 |
| null | 以上皆非（thin 但有正常可用证据） | 单纯数量不足 |

## 三条停止判据（全局决定）

判定时按以下顺序，取第一个命中的决定：

1. **handoff_to_human**
   - 快照零记录：没有任何证据可测量，臆造覆盖结论比不交更糟；或
   - 存在 starved 子问题：有限快照内流程无法补足，需人工扩展检索源或书面确认
     接受缺口（reason 中列出 SQ 与缺口类别）；或
   - 存在 thin 子问题且第 2 轮模拟新增 > thin 子问题数（每子问题超过 1 条）：
     继续检索可能改变分级，值得再来一轮，但快照有限脚本不能自取，交人工决定。
2. **evidence_sufficient**：无 starved、无 thin —— 全部子问题 usable ≥ 3，可以停。
3. **marginal_gain_low**：无 starved、有 thin，且第 2 轮模拟（去掉年份窗）新增
   ≤ thin 子问题数 —— 继续检索的期望收益低于每子问题 1–2 条，不改变任何分级，
   可以停并以 partial 如实交付 thin 子问题。

## 边际收益估计的方法与局限

模拟的第 2 轮只做一件事：**放宽年份窗**（取全部 term_hit 而不问年份），新增数 =
out_of_window 记录数。这是故意的保守下界：真实世界里还可以扩术语、扩库，但那些
超出有限快照，估计了就是臆造。reason 中写明"放宽第 2 轮预计仅新增 N 条"，
复核者可直接用矩阵里的 out_of_window_hits 列复算。

## 与 result.json 状态的对应

| 停止决定 | status |
|-|-|
| evidence_sufficient 且无其他保留 | complete |
| marginal_gain_low | partial（thin 已声明） |
| handoff_to_human | partial（快照有记录时）/ blocked（零记录时） |
