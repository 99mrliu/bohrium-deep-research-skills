# 引用支持四态判定规则（verdict_rubric）

对矩阵的每一格（子主张 × 引文）给出一个 verdict。判定必须可复述：换一个人按本规则与同样材料应得到同一判定。

## 四态定义

| verdict | 定义 |
|-|-|
| `supported` | 子主张的全部构成要素（对象、条件、方向、量级若有）都在引文所示研究范围内，且未超出其证据类型 |
| `partially_supported` | 子主张部分要素有支持，但至少一维范围比对为 `narrower_in_source` 或 `unclear`，或证据类型弱于主张语气 |
| `not_supported` | 引文内容与子主张无关、相反，或子主张的核心要素完全不在引文研究范围内 |
| `undeterminable` | 无法取得足够信息判定（被引原文不可得且条目元信息不足以比对范围；引文歧义；条目无法定位） |

## 判定规则

- **R1 逐要素**：子主张拆到原子后再判；任一要素无支持即不得判 `supported`。
- **R2 范围比对四维**（写入 `scope_check`）：
  - `population`：人群/物种/材料体系。来源为小鼠、主张写人类 → `narrower_in_source`。
  - `condition`：剂量、温度、工况、实验范式。来源为特定条件、主张泛化为任意条件 → `narrower_in_source`。
  - `causal_strength`：来源是相关/关联，主张写因果（"导致""证明""驱动"）→ `narrower_in_source`；来源是体外/计算预测、主张写体内疗效 → 同。
  - `quantification`：主张给具体数值（倍数、百分比、p 值）而来源无此数值或数值不同 → `narrower_in_source`（数值矛盾升级为事实错误 finding）。
- **R3 映射**：四维全 `match` → 可 `supported`；任一 `narrower_in_source` → 至多 `partially_supported`；核心要素错配（对象或方向相反）→ `not_supported`；信息不足 → `undeterminable`。
- **R4 over-claim 典型模式**（见到即提高警惕）：动物→人、体外→临床、相关→因果、单中心→普遍、短期→长期、"可能/暗示"→"证实"、来源无数值→主张有数值。
- **R5 证据可得性约束**：未核读被引原文时，依据限于条目元信息（标题、期刊、年份、摘要若有）与宿主句的范围比对；`supported` 不允许给 high confidence；明显范围错配仍可判 `partially_supported`/`not_supported` 但 confidence ≤ medium，basis 写明"未核读原文，依据条目语义范围"。
- **R6 多文献标记**：一个子主张挂多个引文时逐格判定；矩阵行 verdict 取该格判定，汇总到 finding 时以最弱格为准并说明。

## 严重度映射（引用支持类 finding）

| 情形 | severity |
|-|-|
| `not_supported` 且该子主张是论文核心结论/标题级主张 | critical |
| `not_supported` 非核心，或核心结论 `partially_supported` | major |
| 非核心 `partially_supported`；多处 `undeterminable` 集中于关键论证链 | minor |
| 引用格式问题、从未被引的参考文献条目、未解析标记 | minor / advisory |
