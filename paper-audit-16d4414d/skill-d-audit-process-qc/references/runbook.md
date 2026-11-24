# 过程质控运行手册（900 秒 / 64 请求）

## 时间盒

| 时间 | 动作 | 检查点 |
|-|-|-|
| 0:00–0:30 | init + 读 case.json/task.md + 材料体检 | init |
| 0:30–2:00 | 登记覆盖台账（全 pending）→ 材料体检后定 skipped/unchecked | coverage |
| 2:00–10:00 | 逐检查项审查；每项完成即 coverage examined + checkpoint | 每项一个 |
| 10:00–12:00 | 写 status / summary / 未检查项 | final |
| 12:00–13:00 | finalize 门禁 + 整改 | finalize |

预算安全网独立于时间盒：以请求数为准。40 次 warn 后不再开新检查线；56 次 critical 立即收尾。

## 检查点节奏原则

- **宁可多不可少**：检查点是 append-only 的一次性写入，代价极低；
- 每个检查点做一件事（field 级更新），便于中断后定位续跑点；
- journal.jsonl 是审计链：评审能看到"什么时候确认了什么"，这是"过程可复核"的直接证据。

## 覆盖台账纪律

- task.md 有的检查项，台账必须有对应条目；一个都不能漏登记；
- examined 表示"检查过且有结论（通过或发现问题）"；
- skipped/unchecked 必须写理由，理由要可被评审接受（材料缺失、工具不可用、预算耗尽）；
- pending 是"计划做还没做"，finalize 时 pending 视同未完成，status 不得 success。

## DRIFT 处置

复跑 diff 的三类成因与写法：

1. **材料/输入差异**（平台重复运行理论上同输入，出现差异要记录但通常为零）；
2. **判断漂移**：同一证据两次定级不同——说明定级依据没写实。回到该 finding 补三维依据（主结论影响/可修正性/可复现性），两次取较保守的一级；
3. **发现增删**：新增 finding 要有明确触发原因（本轮多查了某节）；消失的 finding 要说明为何撤回。解释不了的一律 needs_review。

## 诚实门禁逻辑（finalize）

拒收条件（exit=5）：
- case_id 与 case.json 不一致；
- output_contract 字段缺失（null 允许存在——诚实占位比编造好，但要配合 status=partial）；
- 台账有 pending/skipped/unchecked 而 status 标 success/通过/complete；
- status 仍是 in_progress；
- journal 检查点 <2（过程不可复核）。

通过条件不代表"审完了"，只代表"交付物自身一致且诚实"。partial 是合法且常见的最终状态。
