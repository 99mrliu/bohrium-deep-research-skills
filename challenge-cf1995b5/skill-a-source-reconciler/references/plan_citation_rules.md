# 方案数字引用规则（plan_citation_rules）

修订方案（plan.json / plan.md / result.json 内的一切数字）必须满足：**每个数字要么引用
fact id，要么标注为假设**。这条规则由"自检"步骤机械执行。

## 1. 引用格式

- 行内引用：`退火温度取 105/110/115 °C [F041][F057]`，其中 F041 是参数域事实，F057 是
  文献 key_claim 事实。
- 成本行：`| 手套箱 | 80 CNY/h [F012] | 24 h | 1920 CNY |`，数量 24 若是设计决策，
  标注 `(设计值)`；单价必须引 fact id。
- 推导数字：给出算式并引用各操作数的 fact id，如
  `total = 1920+360+500+360+120 = 3260 CNY [F020,F022,F024,F026,F028]`。

## 2. 假设标注

- 无法在 facts.json 中定位的数字一律写为 `ASSUME-n`（n 从 1 顺序编号），例如
  `反溶剂滴加时机 12 s (ASSUME-1)`。
- 每个 ASSUME-n 必须**同时**出现在 result.json 的 `confirmation_items` 中，
  说明需要什么输入才能把它变成事实。
- 禁止把 ASSUME 包装成事实语气（"根据经验取 12 s"可以，"12 s 为最优值"不可以）。

## 3. 前瞻合同措辞

- resource_contract 的价格/预约是**计划性约定**（disclaimer [F007]）：写
  "按组织方前瞻合同单价 80 CNY/h [F012] 估算"，禁止写"供应商报价 80 CNY/h"或
  "已预约 24 小时"。
- budget_cap / deadline_days 是硬约束：方案 total_cost 与 est_days 必须附
  "≤ 预算 20000 CNY [F008] / ≤ 周期 30 天 [F009]"的校核句。

## 4. 文献数字

- 有 pdf_excerpts.md 时：文献数字引用格式 `[F005, pdf p.3]`（fact id + 真实页码）。
  页码只能来自 pdfscan 输出，**不得凭记忆或推测填写**。
- 无 PDF 或 pdftotext 不可用：只能引用 `source.key_claim` 事实，并注明"原文未核对"。

## 5. 对账修正痕迹

- 修订候选方案中的错误数字时，写 `原 v1 total_cost 5760 → 修正 5660（reconcile A-total，
  差额算式见 reconcile_report.json）`，并进 change_log。
- 越域参数改写时，写 `5000 rpm → 4000 rpm（reconcile B-param，enum 域 [F031] 内最近可行点）`。

## 6. 自检清单（写完后执行）

1. 提取 plan.md / plan.json 中全部数字 token；
2. 每个数字后面 3 行内必须有 `[Fxxx]`、`(ASSUME-n)` 或 `(设计值)` 之一；
3. 每个 `[Fxxx]` 在 facts.json 中存在且 value 与文中数字一致（单位一致）；
4. ASSUME-n 与 confirmation_items 一一对应；
5. 全文无"已确认报价/已预约/已排期"等越界措辞。
