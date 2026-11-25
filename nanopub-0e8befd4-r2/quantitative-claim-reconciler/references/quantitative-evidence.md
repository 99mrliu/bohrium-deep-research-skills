# 量值证据规范

## 1. 最小证据单元

每条量值证据必须有唯一 `evidence_id`、存在的 `source_id`、可复核 `locator`、`value`、`unit`、`quantity_kind`、`statistical_unit` 和 `population_scope`。数值使用十进制字符串。`null`、空白或省略均表示未知，不得变为零。

表格 locator 必须含实际 `row_id` 与 `column_id`；证据值必须等于对应 cell。表格必须有行标题，每列必须有完整 `label` 和非空 `unit`，每行必须有完整 `label` 和全部 cell。图注 locator 必须含实际 `panel_id` 或 `field: caption`；panel 证据值须与 panel 声明单位一致。脚本检查结构与明确值，不 OCR、不猜图。

## 2. 行列标题与统计单位

- 不只用 A/B/C 或“值”作标题。标题须表达对象、指标、时间和单位（若适用）。
- `unit` 是计量单位，如 `mentions`、`identifiers`、`people`、`s`、`ms`、`count`；`quantity_kind` 是语义类型，如 `mentions`、`unique_identifiers`、`people`、`cpu_time`。
- `statistical_unit` 说明一次计数落在哪个对象上；`population_scope` 说明总计覆盖谁。二者不可被数值相等替代。
- s 与 ms、mentions 与 people、raw mentions 与 deduplicated identifiers 不自动换算或混合。转换需要来源明确的转换因子和单独计算定义；本计算器不静默转换。

## 3. mentions、unique identifiers、people

三种量可不同方向变化：一次 mention 不保证一个新 identifier，一个 identifier 不保证一个真实 person。相同数值也不能证明对象相同。比例计算要求 `operand_kinds.numerator == operand_kinds.denominator`，并要求 scope 显式兼容。people 分母不能服务 unique-identifier 分子，反之亦然。

## 4. 分母、百分比与百分点

share 是 `numerator / denominator × 100%`，分母范围必须写清。ratio/CPU time change 是新旧值相对基线的变化，带正负号。百分点是两个百分比之差，单位 `percentage_points`，不是 `%`；当前计算器不将百分点运算伪装成 `ratio_percent_change`。

“增长 25%”不等于“增长 25 个百分点”；25% 的占比也不等于 25 个独立对象。直接报告的百分比只能在 evidence 明确存在时记录，不能反推未给操作数。

## 5. 图 panel 与 head graph

每个 panel 有独立单位、对象、尺度和范围。panel a 的秒不能直接与 panel b 的毫秒对账。`head_graph` 或顶端节点中的残差、总值若由图注直接给出，标 `direct`；只有给出所有源操作数时才另标 `calculated`。直接 head graph 值与复算残差可并列，但不得用其中一个捏造另一个。

## 6. 质性结论

质性断言也引用 evidence IDs，但 `value` 和计算结果应为空。例如“标题完整”“不可跨 panel 比较”“来源不支持因果结论”。质性结论不能补足缺失数值。

## 7. 合成示例

仓库内所有 fixture 都是 **SYNTHETIC 合成非正式结果**，仅验证语义与代码，不是真实论文、产品或实验结论。
