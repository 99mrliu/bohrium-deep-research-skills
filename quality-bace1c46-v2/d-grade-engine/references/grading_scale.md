# 文献研究质量分级量表（人类可读版）

- 量表版本：**1.0.0**（与 `references/thresholds.json` 的 `scale_version` 严格一致；二者如有出入，以 JSON 为准并视为缺陷需修正）
- 适用范围：对单篇文献研究（doc）在 5 个方法学维度上给出判定，再由脚本按显式阈值聚合为域级与总评等级。
- 铁律：**模型只产出维度级判定 + 证据引用；所有聚合由 `scripts/derive.py` 按本量表完成。任何人不得口头或凭经验给出"总体大概是中等"这类孤立等级。**

## 1. 五个维度

| 维度 id | 中文名 | 关注问题 | 所属域 |
|---|---|---|---|
| `design_adequacy` | 研究设计充分性 | 研究问题与设计是否匹配（随机化、对照、前瞻/回顾、混杂控制策略） | 内部效度（核心） |
| `sample_sampling` | 样本与抽样 | 抽样框架、样本量与把握度、纳入排除标准、选择偏倚 | 内部效度（核心） |
| `measurement_outcomes` | 测量与结局 | 暴露/结局定义、测量工具的效度信度、盲法评估、结局时点 | 测量与推断效度（核心） |
| `statistical_analysis` | 统计分析 | 分析方法与设计匹配、缺失数据处理、多重性、敏感性分析 | 测量与推断效度（核心） |
| `reporting_completeness` | 报告完整性 | 关键方法学信息是否完整可核查（流程图、方案注册、效应量与精度报告） | 透明性（非核心） |

## 2. 四个判定等级及进入条件

| 等级 id | 中文 | 进入条件（满足其一即可判定） |
|---|---|---|
| `low_concern` | 低担忧 | 该维度关键方法学要素均有描述且处理恰当；未发现可能实质影响结论的缺陷。 |
| `some_concern` | 部分担忧 | 存在方法学疑点（如未报告分配隐藏、样本量估算缺失但有补救迹象）；或关键信息部分缺失，无法排除偏倚但也无直接缺陷证据。 |
| `high_concern` | 高担忧 | 存在明确缺陷且可能实质改变结论（如明显混杂未调整、结局测量系统性失真、分析单位错误、严重选择偏倚）。 |
| `insufficient_evidence` | 证据不足（弃权） | 文中信息缺失到无法区分以上任何等级；或材料不可获得。**判定此等级时必须在 note 中写明缺什么。** |

> `insufficient_evidence` 不是"中等风险"，而是**弃权**。它沿聚合链向上传播（见 §5），绝不参与平均。

## 3. 维度 → 域 映射矩阵

| 维度 | internal_validity | inference_validity | transparency |
|---|:---:|:---:|:---:|
| design_adequacy | ● | | |
| sample_sampling | ● | | |
| measurement_outcomes | | ● | |
| statistical_analysis | | ● | |
| reporting_completeness | | | ● |

域属性：`internal_validity`、`inference_validity` 为**核心域**；`transparency` 为**非核心域**。

## 4. 域级规则（按序求值，首个命中生效）

| 规则 id | 条件 | 域级结果 |
|---|---|---|
| R-DOM-01 | 域内任一维度 = high_concern | high_concern |
| R-DOM-02 | 域内任一维度 = insufficient_evidence | insufficient_evidence（弃权传播） |
| R-DOM-03 | 域内任一维度 = some_concern | some_concern |
| R-DOM-04 | 域内全部维度 = low_concern | low_concern |
| R-DOM-FB | 以上均不命中（兜底） | insufficient_evidence |

## 5. 总评阶梯与规则（按序求值，首个命中生效）

总评阶梯四档：`low`（低）< `moderate`（中）< `high`（高），外加 `insufficient_evidence`（证据不足，独立于阶梯）。

| 规则 id | 条件 | 总评 |
|---|---|---|
| R-OV-01 | 5 个维度中 ≥3 个为 insufficient_evidence | **insufficient_evidence** |
| R-OV-02 | 两个核心域均为 insufficient_evidence | **insufficient_evidence** |
| R-OV-03 | 任一核心域 = high_concern | high |
| R-OV-04 | 仅非核心域（透明性）= high_concern | moderate |
| R-OV-05 | 任一域 = some_concern | moderate |
| R-OV-06 | 存在 insufficient_evidence 的域但未达 R-OV-01/02 阈值 | moderate（弃权信号保留，须在不确定性中标注） |
| R-OV-07 | 全部域 = low_concern | low |
| R-OV-FB | 以上均不命中（兜底） | insufficient_evidence |

## 6. 弃权传播的理由（abstain-propagation rationale）

证据不足意味着"不知道"，而不是"没问题"。若把弃权当作中性分参与平均，缺失信息越多的研究总评反而越好看——这是反向激励。因此：

1. 维度弃权 → 所在域弃权（R-DOM-02）；
2. 弃权维度 ≥3/5 或两个核心域均弃权 → 总评弃权（R-OV-01、R-OV-02）；
3. 未达阈值时降级为 moderate 并在不确定性中显式保留弃权信号（R-OV-06）；
4. 弃权永远不能被其他维度的 low_concern 抵消。

## 7. 完整演算示例（与 examples/ 中合成数据一致）

文献 DOC-S2 的维度判定：

| 维度 | 判定 |
|---|---|
| design_adequacy | insufficient_evidence |
| sample_sampling | insufficient_evidence |
| measurement_outcomes | insufficient_evidence |
| statistical_analysis | high_concern |
| reporting_completeness | some_concern |

推导链：

1. 域 `internal_validity`：R-DOM-02 命中（2 个成员弃权）→ **insufficient_evidence**；
2. 域 `inference_validity`：R-DOM-01 命中（statistical_analysis 高担忧）→ **high_concern**；
3. 域 `transparency`：R-DOM-03 命中 → **some_concern**；
4. 总评：先查 R-OV-01——弃权维度计数 = 3 ≥ 3，命中 → **总评 = insufficient_evidence**（推导链记录 `rule_id=R-OV-01, inputs={insufficient_dimensions: 3, threshold: 3}`）。注意：尽管存在一个高担忧核心域，弃权规则按顺序优先，总评弃权而非 high。
