# 聚合规则全集（Aggregation Rules）

子判断逐条核验完毕后，须按**显式确定性规则**聚合回整论断判定，禁止凭
感觉"综合考虑"。`scripts/aggregate.py` 是这些规则的可执行实现
（`--explain` 可输出逐步推导），两者语义以本文件为准。

## 记号

- 子判定 verdict ∈ {supported, partially_supported, contradicted,
  insufficient_evidence}。
- 核心性 core：显式 `core` 字段优先；缺省时 `type=modifier`（纯修饰子
  判断，如独立拆出的显著性/程度限定）为 core=false，其余类型（fact /
  comparison / causal / scope）一律 core=true。
- weight：可选，仅用于报告各子判断占比，**不改变判定**。

## 规则（按求值顺序）

| 规则 | 条件 | 整论断判定 |
|---|---|---|
| R2 | 任一 core=true 子判断为 contradicted | **contradicted** |
| R1 | 全部子判断 supported | **supported** |
| R3 | contradicted 仅出现在 core=false 子判断 | **partially_supported** |
| R4 | 无 contradicted，且全部 insufficient_evidence | **insufficient_evidence** |
| R5 | 无 contradicted，无任何 supported / partially_supported | **insufficient_evidence** |
| R6 | 其余混合情形 | **partially_supported** |

求值顺序即 R2 → R1 → R3 → R4 → R5 → R6，首条命中即得结论。

## 逐条说明

- **R1（全真则真）**：所有原子子判断均获直接证据支持，整论断
  supported。前置条件是拆解通过覆盖机检（无 omission），否则"全真"
  只是"拆漏后的全真"。
- **R2（核心反驳一票否决）**：核心谓词（比较方向、因果机制、普适
  范围、主事实）任一被证据直接推翻，整论断 contradicted。理由：复合
  论断是合取，任一连言支为假则合取为假。典型例：性能数字全对，但
  "适用于所有铝合金"被原文"仅 6xxx 系"直接反驳 → 整论断 contradicted。
- **R3（修饰反驳降级）**：被反驳的只是修饰性限定（如"显著提升"中的
  显著性限定不成立但效应存在），核心谓词仍成立 → partially_supported，
  并在理由中注明"核心成立、修饰被反驳"。
- **R4（全缺证）**：没有任何子判断获得可核验证据 →
  insufficient_evidence。未报告≠反驳，不得改判 contradicted。
- **R5（无支持亦无反驳）**：子判定全部由 partially_supported 与
  insufficient_evidence 组成（无任何 supported）→ 整论断
  insufficient_evidence：连一个完全成立的连言支都没有，谈不上"部分
  支持"。
- **R6（混合降级）**：至少一个 supported 且存在
  insufficient_evidence 或 partially_supported → partially_supported。

## 边界情形

1. **单子判断论断**：退化为该子判断自身的 verdict（R1/R2/R4 自然覆盖）。
2. **主题相关≠支持**：证据只与论断主题相关但未断言同一命题时，该子
   判断记 insufficient_evidence，不得记 supported。
3. **冲突证据并列**：同一子判断既有支持又有冲突证据时，子判断本身记
   contradicted 或 partially_supported 并**并列双方原话**，再参与聚合；
   不得在聚合层"抹平"冲突。
4. **core 标注争议**：拿不准某子判断是否核心时按 core=true 处理
   （更严格的口径），并在 uncertainty 中注明该选择对结论的影响
   （如"若 a4 被视为修饰，则结论由 contradicted 降为
   partially_supported"）。
5. **循环论证**：若某子判断的证据实质上依赖另一子判断的结论（而非
   独立文献证据），先做去重/合并再聚合；coverage_matrix 的 overlap
   警告是此类问题的信号。
6. **范围子判断的特殊性**：普适量词（所有/全部/all）使 scope 子判断
   极易成为"最脆弱的连言支"，核验时优先查原文的适用范围声明。
7. **聚合不引入新证据**：聚合层只做逻辑合成；任何新事实都必须回到
   子判断核验层补充。
