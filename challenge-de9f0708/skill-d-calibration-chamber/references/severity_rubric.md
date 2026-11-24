# 严重度分级表（severity rubric）：四类别 × 四严重度

本表是 `scripts/severity_gate.py` 规则引擎（R1–R8）与 `scripts/adjudicate.py` 裁定纪律
（A1–A5）的人类可读依据。核心原则：**判定强度不得超过证据强度**。

## 证据强度等级（evidence_kind，由弱到强）

| 等级 | evidence_kind | 含义 | 可支撑的最高严重度 |
|---|---|---|---|
| E0 | `none` | 无任何证据，仅有怀疑 | info（且必须转待复核） |
| E1 | `model_inference` | 模型推断，未指回原文 | minor（且必须转待复核） |
| E2 | `local_rule` | 命中本地规则/启发式，有规则名 | minor（若有逐字 quote 可至 major） |
| E3 | `verbatim_quote` | 原文逐字摘录，可指回文件+页码+章节 | major |
| E4 | `external_record` | 外部数据库/规范条款记录（Crossref、期刊官网、基金委规定等实际检索到的内容） | critical |

诚信类（fabrication_suspected / integrity / plagiarism_suspected /
duplicate_publication / image_manipulation / image_reuse / data_fabrication /
authorship_misconduct）**特殊**：判 major 及以上必须 E4；无 E4 一律封顶 major 并
转待复核（对应 R3 / A3）。"疑似捏造"要求双信号：本地异常信号 + 外部记录异常。

## 类别一：fact_error（事实错误）

与可核对来源（原文自身、所引文献、外部数据库记录）相矛盾的客观错误。

| 严重度 | 定义 | 所需最低证据强度 | 示例 |
|---|---|---|---|
| critical | 动摇论文核心结论的事实错误 | E4 或 E3+可复算 | 关键数据与所引来源原文矛盾且有外部记录 |
| major | 影响局部结论或读者理解的事实错误 | E3 | 参考文献年份/卷期与外部记录不符（有逐字 quote） |
| minor | 不影响结论的孤立笔误 | E2 | 个别数字誊写错误，结论不受影响 |
| info | 疑似但无法坐实 | E0–E1 | 标待复核，不得直接报 |

## 类别二：insufficient_evidence（证据不足）

论断本身可能成立，但正文未给出支撑，或证据链断裂。

| 严重度 | 定义 | 所需最低证据强度 | 示例 |
|---|---|---|---|
| critical | 核心结论完全无数据支撑 | E3（quote 显示论断处无任何数据引用） | "本方法显著优于所有基线"但全文无对比实验 |
| major | 重要论断缺关键证据 | E3 | 声称 p<0.05 但正文/附表均无统计量 |
| minor | 局部表述证据不充分 | E2 | 某段落引用与论点相关性弱 |
| info | 建议补强的表述 | E1 | 转待复核或建议 |

## 类别三：norm_issue（规范问题）

违反明确规范条款（期刊要求、基金委规定、学术出版规范），但不涉及捏造/剽窃。

| 严重度 | 定义 | 所需最低证据强度 | 示例 |
|---|---|---|---|
| critical | 违反强制性规范且影响研究合法性 | E4（规范条款原文）+ E3 | 涉及人类受试者却无伦理批准且期刊强制要求 |
| major | 缺少强制声明/披露 | E3（全文检索确认缺失）+ 规范依据 | 缺伦理声明、缺数据可用性声明 |
| minor | 体例/格式不合规 | E2 | 参考文献体例与期刊要求不一致 |
| info | 建议性规范改进 | E1 | 建议补充 ORCID |

**注意**：缺声明是 norm_issue，**不是** misconduct（见 discrimination_rules.md FP-05）。

## 类别四：suggestion（建议性意见）

改进建议，不构成问题。一律 info，不得携带任何违规严重度（对应 R5 / A4 / FP-08）。

| 严重度 | 定义 | 所需最低证据强度 |
|---|---|---|
| info | 唯一允许的严重度 | E0 即可，但建议给出来源 |

## 规则引擎映射（severity_gate.py）

| 规则 | 触发条件 | 动作 |
|---|---|---|
| R1 | evidence_kind ∈ {model_inference, none} | 严重度封顶 minor |
| R2 | evidence_kind ∈ {model_inference, none} | verdict_status → 待复核 |
| R3 | 诚信类 type 且无 external_record 信号 | 封顶 major + 待复核 |
| R4 | evidence_kind=verbatim_quote 但 quote 为空 | 按 model_inference 重算（R1/R2） |
| R5 | category=suggestion | 封顶 info |
| R6 | evidence_kind=local_rule 且无 quote | 封顶 minor |
| R7 | evidence_kind=verbatim_quote 且 quote 非空 | 严重度下限 minor（只抬到 minor） |
| R8 | 以上均未触发 | 保持原严重度（记录 keep） |

## 裁定纪律映射（adjudicate.py）

| 规则 | 触发条件 | 裁定 |
|---|---|---|
| A1 | 已待复核或 E0/E1 | 待复核 |
| A2 | critical 但非 E4 | 降级 major |
| A3 | 诚信类但非 E4 | 封顶 major + 待复核 |
| A4 | suggestion | 维持 info |
| A5 | 其余 | 维持 |
