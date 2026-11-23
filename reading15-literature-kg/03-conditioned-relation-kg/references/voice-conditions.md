# 作者声音（author voice）与条件作用域规则

## 1. author voice 四类（必填）

| voice | 定义 | 典型位置 | 使用约束 |
|-|-|-|-|
| `primary-results` | 作者本文的一手结果/测量 | Results、Methods 中的自测数据 | 可作一手证据 |
| `cited-background` | 转述他人工作的背景引用 | Introduction、Related Work | **永远不得当作一手证据**；查询时必须显式标注 |
| `interpretation` | 作者对结果的解释性解读 | Discussion | 不等同于测量事实 |
| `hypothesis` | 作者的推测/待验证猜想 | Discussion、Future Work | 不得升级为结论边 |

判别提示：
- “was reported to / 已被报道 / [引用编号]” → `cited-background`；
- “we achieve / 我们测得 / Table N shows our …” → `primary-results`；
- “this suggests / 可能因为” → `interpretation`；
- “we hypothesize / 有待进一步验证” → `hypothesis`。

## 2. 条件作用域（condition scoping）

极性（polarity）与比较结论只在声明的作用域内成立。作用域键：

- `sample`：样本/数据子集（如 10k 句对训练划分）；
- `model_config`：模型配置/参数规模；
- `dataset`：数据集节点；
- `metric`：指标节点（或自由文本 `basis`）；
- `condition`：实验条件节点（如低资源预算）；
- `task`：任务节点。

规则：

1. **无全局赢家**：`outperforms` 缺 metric/basis 或 comparator →
   linter 降级为 `uncertain`，绝不补造“总体更好”。
2. **数值三件套**：value + unit + 至少一个作用域键，缺一不可；
   缺则数值降级、边记 `partial`。
3. **条件缺失不补造**：条件未知 → `partial/uncertain` 并写入
   uncertainty，不从领域常识推断条件。
4. **跨篇不并条件**：两篇论文的条件、样本与数值不得合并成一个结论；
   相同通用方法/材料术语不代表相同物理样本、模型实例、数据集或实验条件。

## 3. 冲突处理

- 同 (subject, relation, object, 条件签名) 下数值不同 → K1 冲突；
- supports 与 contradicts 并存、或反向 outperforms 并存 → K2 冲突；
- 冲突**全部保留**，边标记 `in_conflict=true`，conflicts.json 记录
  双方 source_id 与引文，**绝不静默仲裁、不取平均、不选赢家**。

## 4. 共现与转述的边界

- 跨篇（或同篇）共现只是共现：`cooccurrence_notes` 记录但不建边；
- 综述转述（cited-background）只能回答“谁报道过什么”，不能回答
  “本文证明了什么”；
- 同一篇论文的多种文件格式只算一个来源，不构成跨篇证据。
