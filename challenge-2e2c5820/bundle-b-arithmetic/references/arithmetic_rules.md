# 实算规则（所有脚本共同遵守）

## 1. 数值表示

- 全部算术使用 Python `decimal.Decimal`；读 JSON 时 `parse_float=Decimal`，杜绝二进制浮点误差。
- 金额显示：ROUND_HALF_UP 量化到 0.01（2dp）。中间运算不量化，只对最终显示值量化。
- 时间：小时为单位的 Decimal，显示最多 2dp。

## 2. 预算复算

- 每行：`computed = unit_price × quantity`，公式串原样打印，如 `离心管 2.50 × 200 = 500.00 CNY`。
- 申报小计核对：若有 `stated_subtotal`，漂移 = `|stated − computed| / |computed|`；
  **漂移 > 0.5%（默认，可调 `--drift-tol`）即标记 unverified**——申报值不采信，合计一律用复算值。
- 合计 = Σ computed。上限（cap）匹配优先级：`--cap` 显式参数 > case.json 中键名匹配
  `cap|上限|budget|预算` 的正数值（直接含 cap/上限 的路径优先）。
- delta = 合计 − 上限；`delta > 0 → 超支`，否则 `结余`。找不到上限 → `unverified_cap_not_found`，不编造上限。
- 多币种混排 → `unverified_mixed_currency`，不硬加。

## 3. 进度实算

- 由 `depends_on` 建 DAG；Kahn 拓扑排序，**发现环即 exit 2** 并列出成环节点。
- ES = max(前置 EF, 0)，EF = ES + duration；总工期 = max(EF)。
- 关键路径：从 EF 最大节点回溯，每步取 EF 最大的前置（并列取 id 较小者，保证可复现），
  以 `S1(0→24) → S2(24→72) → …` 显式链式打印。
- 时限匹配：`--deadline-hours` > case.json 中键名匹配 `deadline|截止|window|窗口` 的正数值。
  `总工期 > 时限 → 超出（gating fail）`；找不到时限 → `unverified_no_deadline`。

## 4. 参数域判定

- 域来源：`--domains` 显式文件 > case.json 中键名匹配 `domain|参数域|parameter` 的 dict 列表。
- 名称模糊匹配（按序）：规范化（去空白/下划线/连字符/括号，小写）后精确相等 → 一方包含另一方 →
  否则 `no_domain_found`（如实报告，绝不静默放过）。
- 单位归一化：仅在同维度且 `convertible=true` 时按 references/units.json 的 factor 换算
  （如 mL↔µL、min↔h）。`convertible=false`（rpm↔g 依赖转子半径）或跨维度 →
  `unit_unconvertible`，请专家复核，绝不猜换算。
- 枚举域：换算后值 ∈ values；区间域：min ≤ 值 ≤ max（含端点）。
  越界 → `out_of_domain`（gating fail）。

## 5. 结论分级

| 级别 | 含义 | 处理 |
|---|---|---|
| gating fail | 超支 / 超期(超出) / 越域(out_of_domain) | 该方案判不可行 |
| unverified | 申报漂移、no_domain_found、unit_unconvertible、cap/deadline 未找到、产物缺失 | 如实列出，不计 gating fail，但写入 uncertainty |
| pass | 三项实算均无 gating fail | 可作为 chosen_plan 候选 |

## 6. 诚实铁律

**任何脚本无法从抽取的操作数复算出来的数字，一律标记 `unverified`，不得采信、不得写进结论。**
模型声称的数字（如"总价约 9000"）若未经脚本实算，只能作为待验证线索，不能进入 result.json 的数值字段。
