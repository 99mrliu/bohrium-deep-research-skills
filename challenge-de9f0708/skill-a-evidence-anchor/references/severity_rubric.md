# finding 类型 × 严重度分级表（severity rubric）

先定类型（四选一），再定严重度（四档）。判定强度必须与证据强度匹配：
证据只支持"疑似"时，severity 至多 major 且 verdict_status=待复核。

## 1. 类型（type / category 归属）

| type | 含义 | 典型例子 |
| --- | --- | --- |
| fact_error | 与材料原文或可查事实直接矛盾 | 数字前后不一致（n=120 vs n=102）、文献元数据不可能组合、单位/公式错误 |
| insufficient_evidence | 论断本身可能成立，但材料内无支撑 | 无引用的强因果论断、无数据来源的百分比、"众所周知"式断言 |
| norm_issue | 违反学术/伦理/期刊规范 | 缺伦理审批或知情同意声明、缺数据可用性声明、疑似一稿多投表述、PII 泄露 |
| suggestion | 不伤及成立性的改进意见 | 建议补充流程图、建议报告效应量与置信区间、图表可读性 |

## 2. 严重度（severity）

| severity | 判定依据 | 处置 |
| --- | --- | --- |
| critical | 动摇结论成立性或涉及合规红线：核心数据矛盾、缺伦理审批、疑似捏造数据/文献 | 必须在报告头部列出；不修复则论文不应被采信 |
| major | 实质损害可信度但未必颠覆结论：无支撑的强因果论断、关键方法缺失、文献元数据严重可疑 | 必须修复或给出解释 |
| minor | 局部、有限影响：个别数字笔误、次要引用格式错误、单处表述歧义 | 建议修复 |
| info | 纯提示性：风格、可选改进、suggestion 类默认档 | 记录即可 |

## 3. 判定流程（每条 finding 过一遍）

1. **锚定先行**：quote 通过 quote_bind 核验（exact/normalized/cross_page）才有评级资格；
   `none` 已被自动降级为待复核，不得再标 critical/major 的"确认"。
2. **定类型**：矛盾 → fact_error；无支撑 → insufficient_evidence；违规范 → norm_issue；
   其余 → suggestion。一条 finding 只选一个主类型。
3. **定严重度**：问两个问题——(a) 它影响的是核心结论还是局部细节？(b) 它是否触及
   合规红线（伦理、数据真实性、PII）？两问皆"是"→ critical；其一"是"→ major；
   皆"否"但确需改 → minor；纯提示 → info。
4. **标 verdict_status**：
   - 确认 = quote 锚定通过 + 判定依据可引用（规则名/规范条款/外部记录）；
   - 待复核 = 锚定失败、或 absence 类未经人工全文确认、或需外部核验但未能核验；
     必须在 verdict_reasons 写明理由。

## 4. 升降级纪律
- 升级从严：升 critical 需要"原文逐字 quote + 明确规则/条款"双证据。
- 降级从宽：任何一环存疑即降一档或标待复核；宁可 minor+待复核，不可 critical+误报。
- 漏报与误报同等扣分：不要为了显得严格而拔高 severity，也不要为凑数报 info 水条。
