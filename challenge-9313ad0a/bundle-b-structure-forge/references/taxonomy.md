# 分类体系（kind 词汇表）与分类轴规则

本文件定义思维导图节点的 `kind` 词汇表、各用途（purpose）的核心 kind 集合，以
及“一个兄弟组只用一个分类轴”的规则。配套工具：`scripts/tree_lint.py`（检查）
与 `scripts/tree_rebalance.py`（修复）。

## 1. kind 词汇表（12 种）

| kind | 定义 | 典型例 |
| --- | --- | --- |
| `question` | 有待回答的研究问题、子问题 | “如何提高比表面积？” |
| `method` | 方法、路线、步骤、测量手段 | “水热合成法”“XRD 表征” |
| `evidence` | 支持或反驳某论断的证据、观测、数据 | “吸附等温线为 IV 型” |
| `result` | 由方法直接得到的实验或计算结果 | “比表面积 850 m²/g” |
| `conclusion` | 由结果归纳出的结论性判断 | “模板剂浓度是主控因素” |
| `limitation` | 方法、数据或结论的局限 | “未做中试放大验证” |
| `task` | 待执行的行动项 | “重复第三批合成” |
| `risk` | 潜在风险、失败模式 | “晶化温度漂移导致杂相” |
| `decision` | 已作出的决定 | “采用 1:0.35 模板剂配比” |
| `milestone` | 阶段性里程碑 | “完成小试工艺窗口” |
| `concept` | 概念、定义、背景知识 | “介孔材料” |
| `other` | 无法归入上述类别者（应尽量少用） | 待分类的临时节点 |

## 2. 分类轴规则：一个兄弟组只用一个轴

同一父节点下的全部子节点应当沿**同一分类轴**展开，即兄弟节点的 `kind` 应当一
致（或至多在两种密切相关的 kind 之间）。`tree_lint.py` 的 `kind_mixing` 检查
对 distinct kind 超过 2 的兄弟组发出 WARN。

示例：

- 合理：父节点“实验结果汇总”下全部为 `result`（按“结果”轴展开）。
- 不合理：同一兄弟组内混杂 `result`、`evidence`、`task`、`other` 四种
  kind——结果、证据、行动项属于不同轴，应分层或分组。

`tree_rebalance.py` 的 `split_overloaded` 在拆分过载兄弟组时按 kind 插入
“<kind>类”中间分组节点，其效果是把隐含的多轴拆分显式化；分组后父节点的直
接子节点为各分组节点，它们 kind 各不相同，`kind_mixing` 警告可能仍然出现，
此时警告的含义是“此处存在多个分组轴，请人工复核”，属于预期行为。

## 3. 各 purpose 的核心 kind 集合

`tree_lint.py` 的 `missing_core_kind` 检查：全图缺少下列任一核心 kind 时发出
WARN（提示内容骨架不完整，需人工补写）。

| purpose | 核心 kind（缺一不可） |
| --- | --- |
| `paper` | `question`, `method`, `result`, `conclusion` |
| `experiment` | `method`, `risk` |
| `project` | `milestone`, `task`, `risk` |
| `meeting` | `decision`, `task` |
| `knowledge` | 无强制集合 |

说明：核心集合是“最低完备性”要求而非充分条件；例如论文类导图通常还包含
`limitation` 与 `evidence`，但缺失这两类不触发警告。
