# 分级阈值与聚合规则（明文，与 scripts/aggregate_grade.py 常量一一对应）

等级四态：`high / moderate / low / ungradable`。孤立等级标签禁止：
每个等级必须附推导链（derivation），列出被触发的规则编号、实际计数值与触发条目 ID。

## 记数定义

- `n`：该文献已提交并经门控校验的条目判断总数。
- `na_ratio` = `not_assessable` 条目数 / `n`。
- `partial_ratio` = `partial` 条目数 / `n`。
- `core_not_met`：核心条目（条目库中 `核心: 是`）判 `not_met` 的条目 ID 列表。
- `core_na`：核心条目判 `not_assessable` 的条目 ID 列表。

## 规则（按优先级顺序判定）

| 规则 | 条件 | 等级 |
|---|---|---|
| R0 | 文献解析失败（tier=failed），无任何可依据文本 | ungradable |
| R0b | 无任何条目判断（模型未提交或全部解析失败） | ungradable |
| R1 | `na_ratio > 0.60`（可评价条目占比不足 40%） | ungradable |
| R5 | tier=abstract_only（仅摘要）：**等级上限 moderate，不允许 high**；先执行 R5b/R5c，否则 R5a | 见下 |
| R5a | 仅摘要且无 core_not_met、core_na 数 < 3 | moderate |
| R5b | 仅摘要且 `len(core_na) ≥ 3`（核心证据缺口过大） | low |
| R5c | 仅摘要且存在 core_not_met | low |
| R3 | 全文且 `core_not_met=0`、`core_na=0`、`na_ratio ≤ 0.15`、`partial_ratio ≤ 0.30` | high |
| R4 | 全文且 `len(core_not_met) ≤ 1` 且 `na_ratio ≤ 0.35`（不满足 R3） | moderate |
| R6 | 其余全文情形（`len(core_not_met) ≥ 2` 或 `na_ratio > 0.35`） | low |

## 说明

- 门控校验失败者已被 verify_quotes.py 就地降级为 `not_assessable`，聚合时按降级后计。
- 仅摘要文献之所以封顶 moderate：方法学条目（随机化、混杂控制、统计细节）
  在摘要中天然不可得，高分级需要全文证据支撑。
- 修正阈值时须同步修改本表与 `aggregate_grade.py` 顶部常量，保持单一事实源。
