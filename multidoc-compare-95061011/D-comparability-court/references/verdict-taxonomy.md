# Verdict 分类法与守门语义（verdict-taxonomy）

本文件是 comparability-court 的"法典"：五种 verdict 的定义、任务级合成规则、permit 语义、叙述绑定规范。所有 verdict 由 `scripts/decide.py` 依据 `references/comparability-rules.json` 确定性产出，**agent 不得改写 verdict，只能补充证据（quote / paragraph_id）**。

## 1. 五种 verdict

| verdict | 定义 | 对定量合成的含义 | 对定性对照的含义 |
|---|---|---|---|
| `comparable` | 规范化取值一致（含别名归一），同一口径 | 允许 | 允许 |
| `convertible` | 取值不同但存在确定性换算（如 min^-1 ↔ h^-1） | 允许，permit 必须附归一化说明 | 允许 |
| `subset_only` | 维度性质允许定性对照但不允许数值合并（不同 metric、不同材料体系、不同投加量、不可换算单位） | **禁止** | 允许，报告中必须注明口径差异 |
| `undecidable` | 至少一方未报告该维度，无法裁定 | 禁止 | 禁止（缺失本身即不确定性；补齐档案后可重裁） |
| `blocked` | 维度冲突不可调和（不同污染物、不同任务） | 禁止 | 禁止（连定性对照也属于"比了不该比的"） |

## 2. 任务级总裁定（overall verdict）

- 严重度序（最严在前）：`blocked > undecidable > subset_only > convertible > comparable`。
- 一对论文的六维度（含扩展键）裁定中，**任务级总裁定 = 最严重者的 verdict**，并记录 `strictest_dimensions`（取得最严 verdict 的维度清单）与 `blocking_dimensions`（所有严格于 convertible 的维度，即阻断定量合成的维度）。
- 总裁定仅用于总览与报告；守门判断永远回到逐维度 decision。

## 3. permit 语义（pool.py）

合成请求（synthesis_request.json）字段：`request_id`、`docs`（≥2 篇，否则拒绝——单篇摘要不构成多文档比较）、`field`、`claim_type`（`quantitative` | `qualitative`）、`required_dimensions`（缺省 = 六核心维度）、`claim_text`。

- 对 `docs` 的**每一个无序对** × 每一个 `required_dimensions` 维度，必须存在 decision 记录；缺失 decision → block（理由：缺少裁定）。
- `quantitative` 请求：所有相关 decision 的 verdict ∈ {comparable, convertible} 才发 permit；permit 附 `normalization_notes`（每个 convertible 维度的换算说明）。
- `qualitative` 请求：verdict ∈ {comparable, convertible, subset_only} 可发 permit；permit 附 `caveats`（每个 subset_only 维度的口径差异警告，报告必须复述）。
- 任一维度为 `blocked` 或 `undecidable` → block，输出 `blocking` 清单：decision_id、维度、verdict、双方取值、双方 paragraph_id + quote 定位。
- permit_id 形如 `PERMIT-<request_id>`。**无 permit 的定量断言不得出现在报告中**；被 block 的请求只能以"被阻断 + 阻断理由"的形式出现在报告的"被阻断的合成"一节。

## 4. 叙述绑定规范

1. 报告（verdict-report.md）中**每一个跨论文比较句**必须引用 `[DEC-…]`（裁定）或 `[PERMIT-…]`（许可）；不允许手写新的比较结论。
2. 引用 id 必须真实存在于 decisions.jsonl 或 pool 输出中（render_court.py 的 lint 强制检查）。
3. 启发式 lint：一句中同时出现 ≥2 个 doc_id 与数字/比较词（均值、高于、优于、排名、更快、更强等）且**没有任何** `[DEC-…]`/`[PERMIT-…]` 引用 → 告警"疑似未许可的定量比较句"。已绑定 decision/permit 的句子视为有出处；纯手写、无引用的跨论文数值句才是打击对象。
4. 定性对照句引用 permit 时，若 permit 含 caveats，句子必须体现口径差异（如"仅定性对照，材料体系不同"）。

## 5. 扩展键

profiles.jsonl 允许六核心维度之外的自由扩展键（如 `light_source`、`reaction_time`）。扩展键须在 rules 的 `extension_dimensions` 登记规则；未登记的维度异值时默认 `undecidable`，防止"无规则默认可比"。
