# 受控关系词表（与 scripts/atomize_lint.py 同步）

任务自带关系词表或 schema 枚举时，以任务为准；把本词表关系映射过去并在 result.json
记录映射。以下 24 个关系按 6 族组织。

## 比较与性能

| relation | 含义 | 例 |
|-|-|-|
| outperforms | 在指定指标与设定下优于 | A outperforms B（指标、数据集进 qualifiers） |
| underperforms | 在指定指标与设定下劣于 | A underperforms B |
| comparable_to | 差异无统计学或实际显著性 | A comparable_to B（≠ 等价） |
| equivalent_to | 功能/结果可互换的等价 | SIMD 实现 X equivalent_to 原实现（输出一致） |

区分：`comparable_to` 只陈述无显著差异，不蕴含等价；`outperforms` 必须带指标与范围。

## 参数与属性

| relation | 含义 |
|-|-|
| has_parameter | 具有某参数及取值（object 可为参数表） |
| has_property | 具有某性质（如 linear-time、deterministic） |
| has_value | 某度量取某值（object 含数值与单位，须逐字对得上） |
| has_complexity | 时间/空间复杂度 |

## 结构与组成

| relation | 含义 |
|-|-|
| part_of | 组件属于整体 |
| consists_of | 整体由部分组成 |
| uses | 使用某算法/数据结构/资源 |
| extends | 在前作/基线上扩展 |
| derived_from | 数据来源或方法派生 |

## 因果与机制

| relation | 含义 |
|-|-|
| causes | 直接导致（须有原文因果表述或实验证据） |
| enables | 使某能力成为可能 |
| inhibits | 抑制/降低 |
| requires | 前置依赖 |
| limits | 构成限制（局限章节常见） |

`correlates_with/associated_with` 不得升级为 `causes`。

## 关联与证据

| relation | 含义 |
|-|-|
| correlates_with | 统计相关 |
| associated_with | 一般关联（未定量） |
| reports | 文献报告某结论（用于归属既往工作） |
| evaluated_on | 在某数据集/基准上评测 |
| trained_on | 在某数据上训练 |
| applies_to | 适用于某对象/范围 |

## 功能与用途

| relation | 含义 |
|-|-|
| supports | 支持某输入/模式/功能 |
| generates | 产生某输出 |
| takes_input | 接受某输入形态 |
| produces_output | 产出某输出形态 |

## 使用约定

- 一断言一关系；同句第二关系必须另起断言。
- 负向事实：肯定关系 + `polarity=negative`，不新增否定关系词。
- 找不到贴切关系时，选语义最近者并在 qualifiers 记录原文措辞；不得生造词表外关系。
