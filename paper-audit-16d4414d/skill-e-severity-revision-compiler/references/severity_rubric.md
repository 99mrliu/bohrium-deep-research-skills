# 严重度定级细则（severity rubric）

## 决策树（逐条过，写到 rationale 里）

```
这条 finding 若成立，主结论是否不再成立？
├─ 是 → critical
└─ 否 → 是否影响次要结论，或需要补实验/补引用/重算才能成立？
    ├─ 是 → major
    └─ 否 → 是否会误导读者（数值、措辞、方向）但不动结论？
        ├─ 是 → minor
        └─ 否 → suggestion
```

## 三维依据（confirmed 必填）

| 轴 | 取值/写法 | 说明 |
|-|-|-|
| main_conclusion_impact | 一句话 | 对主结论的影响路径，写清"通过哪条证据链" |
| fixability | easy_single_edit / moderate_rewrite / needs_new_analysis / needs_new_data | 决定修复优先级排序 |
| reproducibility_impact | 一句话 | 他人按此文复现时能否到达同一结论 |

## 锚例（校准用，避免一律标"中"）

| 情形 | 定级 | 锚定理由 |
|-|-|-|
| p=0.31 声称 significant，且该结果是主结论唯一支撑 | critical | 主结论的统计依据不存在；但 fixability 可能是 easy_single_edit（改表述或重算）——定级看影响不看修改成本 |
| 摘要数值与结果不一致（14.1 vs 15.1），主结论方向不变 | major | 误导读者、损害可信性，不改无法交代 |
| 背景句引用一篇文献支撑领域共识 | minor | 不动结论，但证据链不规范 |
| Discussion 用因果动词描述相关设计，主结论本身已带 hedge | major | 强度超设计上限，读者会误取因果信息 |
| 引而未列 [3] | major | 证据不可追溯，影响可复核性 |
| 列而未引 | minor | 冗余，不误导 |
| future work 写得空泛 | suggestion | 可改可不改 |

## 反失真规则

- ≥4 条全部同级 → lint 全局告警。真实分布几乎总跨级；先怀疑定级惯性，再确认；
- needs_review 不定级——待复核条目强行定级是另一种失真；
- 定级由"影响"决定，不由"修改难度"决定；改起来容易的严重问题仍是严重问题。
