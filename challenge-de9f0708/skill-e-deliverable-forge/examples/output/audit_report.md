# 审查报告：MOCK-E-001

> 本报告由 report_render.py 自 `result_full.json` 机械渲染生成，内容以 result.json 为准；合成示例输出，非正式测评结果。

## 一、概要

- **交付状态 status**：`complete`
- **问题总数**：6（critical 1 / major 2 / minor 2 / info 1）
- **待复核**：1 条
- **概要**：对 synthetic_paper.txt 完成 5 个审查面的审查，共 6 条发现：critical 1、major 2、minor 2、info 1，其中 1 条待复核。

### 严重度 × 类别交叉计数

| severity | abstract_table_number_mismatch | missing_ethics_statement | missing_limitations | possible_pii | unsupported_novelty_claim | unverifiable_reference | 合计 |
|---|---|---|---|---|---|---|---|
| critical | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| major | 0 | 1 | 0 | 0 | 0 | 1 | 2 |
| minor | 0 | 0 | 0 | 1 | 1 | 0 | 2 |
| info | 0 | 0 | 1 | 0 | 0 | 0 | 1 |

### 未检查面（not_reviewed）

- 无未覆盖审查面：case.json 声明的 5 个审查面（事实一致性/引用核验/伦理合规/论断证据/报告完整性）均已完成审查

## 二、逐条问题卡片

### 1. 【CRITICAL】 F01（abstract_table_number_mismatch）

- **类别 type**：`abstract_table_number_mismatch`（category: `fact_error`）
- **严重度**：严重（critical）
- **定位**：synthetic_paper.txt 第1页「摘要」
- **原文摘录**：

  > 系统分诊准确率达 97.3%

- **依据 evidence**：摘要称准确率 97.3%；第 2 页结果节表 1 汇总『总样本 400 例，其中正确分诊 375 例，错误 25 例』，据此计算为 375/400=93.75%，两处数字直接矛盾。
- **修改建议**：按表 1 混淆矩阵重新核算准确率，将摘要中的『97.3%』更正为 93.75%，或修正表 1 数据并说明两处口径差异。
- **判定状态 verdict_status**：确认

### 2. 【MAJOR】 F02（unverifiable_reference）

- **类别 type**：`unverifiable_reference`（category: `insufficient_evidence`）
- **严重度**：重要（major）
- **定位**：synthetic_paper.txt 第3页「参考文献」
- **原文摘录**：

  > Zhang, L. & Lee, H. (2021). Synthetic data augmentation for triage. Journal of Synthetic Data Studies, 12(3), 45-59.

- **依据 evidence**：该文献支撑第 1 页引言中『合成数据增强可以显著提升小样本场景下的模型性能』的关键论断，但期刊名 Journal of Synthetic Data Studies 在本地材料中无任何可核实记录，元数据存在编造嫌疑。
- **修改建议**：联网检索 Crossref/DOI 记录核验该文献是否真实存在；若无法核实，替换为真实可查的文献，或删除引言中依赖它的论断。
- **判定状态 verdict_status**：待复核：需联网检索 Crossref/DOI 确认文献真伪，本合成示例环境未执行外部核验

### 3. 【MAJOR】 F03（missing_ethics_statement）

- **类别 type**：`missing_ethics_statement`（category: `norm_issue`）
- **严重度**：重要（major）
- **定位**：synthetic_paper.txt 第2页「方法」
- **原文摘录**：

  > 我们通过问卷调查收集了 120 名受试者的健康数据

- **依据 evidence**：研究涉及人体受试者健康数据，但全文（第 1-3 页）未出现任何伦理审批或知情同意声明，不满足涉及人体研究的基本合规要求。
- **修改建议**：在方法节补充伦理审批机构名称、批件编号与知情同意获取方式；若未获审批，应如实说明并限制数据使用范围。
- **判定状态 verdict_status**：确认

### 4. 【MINOR】 F04（possible_pii）

- **类别 type**：`possible_pii`（category: `norm_issue`）
- **严重度**：次要（minor）
- **定位**：synthetic_paper.txt 第2页「方法」
- **原文摘录**：

  > 例如受试者王某（联系电话 13800001234）报告了持续两周的胸痛症状

- **依据 evidence**：正文直接出现受试者姓氏与完整手机号，属疑似个人可识别信息（PII）泄露。
- **修改建议**：删除手机号，并将『王某』匿名化为受试者编号（如 S-017）。
- **判定状态 verdict_status**：确认

### 5. 【MINOR】 F05（unsupported_novelty_claim）

- **类别 type**：`unsupported_novelty_claim`（category: `insufficient_evidence`）
- **严重度**：次要（minor）
- **定位**：synthetic_paper.txt 第1页「摘要」
- **原文摘录**：

  > 据我们所知，本研究是全球首个将量子启发算法用于县级医疗分诊的工作。

- **依据 evidence**：首创性论断未附任何文献检索范围或综述依据支撑，属于无依据论断。
- **修改建议**：补充支撑该首创性判断的文献检索范围与结果，或将表述弱化为『鲜有报道』。
- **判定状态 verdict_status**：确认

### 6. 【INFO】 F06（missing_limitations）

- **类别 type**：`missing_limitations`（category: `suggestion`）
- **严重度**：提示（info）
- **定位**：synthetic_paper.txt 第3页「讨论」
- **原文摘录**：

  > 实验结果表明本系统具有临床推广价值。

- **依据 evidence**：讨论节仅一句结论性表述，未讨论样本规模（120 名受试者）、单一机构数据来源等对结论外推的限制。
- **修改建议**：在讨论节补充局限性段落，说明样本量与单中心数据来源对结论外推的限制。
- **判定状态 verdict_status**：确认

## 三、修改优先级清单

- 【CRITICAL】 **F01**：按表 1 混淆矩阵重新核算准确率，将摘要中的『97.3%』更正为 93.75%，或修正表 1 数据并说明两处口径差异。
- 【MAJOR】 **F02**：联网检索 Crossref/DOI 记录核验该文献是否真实存在；若无法核实，替换为真实可查的文献，或删除引言中依赖它的论断。
- 【MAJOR】 **F03**：在方法节补充伦理审批机构名称、批件编号与知情同意获取方式；若未获审批，应如实说明并限制数据使用范围。
- 【MINOR】 **F04**：删除手机号，并将『王某』匿名化为受试者编号（如 S-017）。
- 【MINOR】 **F05**：补充支撑该首创性判断的文献检索范围与结果，或将表述弱化为『鲜有报道』。
- 【INFO】 **F06**：在讨论节补充局限性段落，说明样本量与单中心数据来源对结论外推的限制。

## 四、不确定项与变更记录

### uncertainty

- 参考文献[2]的真伪未能本地核实（见 F02 待复核）。
- 机械验收未通过项：sources: required field missing
- 机械验收未通过项：not_reviewed: required field missing

### change_log

- 初稿：组装 findings_final.json 的 6 条发现。
- 机械验收未过，状态自动降级为 partial；缺失/非法字段：sources、not_reviewed
- 补齐缺失字段 sources、not_reviewed，status 恢复 complete，准备重跑机械验收。

