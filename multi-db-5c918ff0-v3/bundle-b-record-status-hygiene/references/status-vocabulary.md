# 状态信号原因码表（Status Signal Vocabulary）

本文件是 `scripts/status_hygiene.py` 发出的全部机器可读原因码的**规范表**。
每条信号必须携带证据定位符（`文件相对路径::jsonpath`）。严重级别语义：

- **severe**：记录状态类判为 `severe`——默认处置 `exclude_as_retracted`，
  一律排除出候选池（模型可附理由覆盖，但须显式）。
- **flagged**：记录状态类判为 `flagged`——必须经模型裁定
  （`keep_with_notice` / `exclude_as_retracted` / `keep_clean`）后才可定夺。
- **info**：信息性（preprint 标记、import 簿记），不改变状态类。
- **warning**：数据集级问题（import 声明不一致），隔离该声明而非记录。

## 撤回 / 勘误 / 关注声明

| code | 信号来源（库·字段/关系/pubType 字符串） | severity | 要求处置 |
|---|---|---|---|
| `CROSSREF_IS_RETRACTION_OF` | Crossref `relation[]` 中 `relation-type == "is-retraction-of"`：**本记录是**撤回通告 | severe | 排除（通告本身不是研究） |
| `CROSSREF_HAS_RETRACTION` | Crossref `relation-type == "has-retraction"`：本记录已被撤回 | severe | 排除 |
| `TARGET_RETRACTED` | 派生：另一记录的 `is-retraction-of` 指向本记录 DOI | severe | 排除 |
| `CROSSREF_IS_ERRATUM_OF` | `relation-type == "is-erratum-of"` / `"is-correction-of"`：本记录是勘误通告 | flagged | 模型裁定（通常保留并附注意或不作研究计数） |
| `CROSSREF_HAS_ERRATUM` | `relation-type == "has-erratum"` / `"has-correction"` | flagged | 通常 `keep_with_notice` |
| `TARGET_CORRECTED` | 派生：另一记录的勘误通告指向本记录 | flagged | 通常 `keep_with_notice` |
| `CROSSREF_IS_EXPRESSION_OF_CONCERN_OF` | `relation-type == "is-expression-of-concern-of"` | flagged | 模型裁定 |
| `CROSSREF_HAS_EXPRESSION_OF_CONCERN` | `relation-type == "has-expression-of-concern"` | flagged | 通常 `keep_with_notice` |
| `TARGET_CONCERNED` | 派生：另一记录的 EoC 通告指向本记录 | flagged | 通常 `keep_with_notice` |
| `CROSSREF_UPDATE_TO` | Crossref `relation-type == "update-to"` 或顶层 `update-to[]`（Crossmark 更新） | flagged | 模型裁定；`update-to[].type=="retraction"` 时应按撤回对待 |
| `CROSSREF_UPDATE_BY` | `relation-type == "update-by"` | flagged | 同上 |
| `EPMC_RETRACTION_OF_PUBLICATION` | EuropePMC `pubTypeList.pubType` 含 `"Retraction of Publication"`：本记录是撤回通告 | severe | 排除 |
| `EPMC_RETRACTED_PUBLICATION` | EuropePMC pubType 含 `"Retracted Publication"`：本记录已被撤回 | severe | 排除 |
| `EPMC_ERRATUM` | EuropePMC pubType 含 `"Erratum"`（亦兼容 `"Correction"`） | flagged | 通常 `keep_with_notice` |
| `EPMC_EXPRESSION_OF_CONCERN` | EuropePMC pubType 含 `"Expression of Concern"` | flagged | 通常 `keep_with_notice` |
| `PUBLISHER_STATUS_RETRACTED` | 出版商记录显式 `status` ∈ {retracted, withdrawn, retraction, removed} | severe | 排除 |
| `PUBLISHER_STATUS_NOTICE` | 出版商 `status` ∈ {expression_of_concern, eoc, correction, corrected, erratum, concern} | flagged | 通常 `keep_with_notice` |
| `REFGRAPH_NODE_WITHDRAWN` | reference_graph 节点 `status` ∈ {retracted, withdrawn, removed} 或 `withdrawn: true` | severe | 排除 |
| `REFGRAPH_NODE_NOTICE` | 图节点 `status` ∈ {expression_of_concern, corrected, erratum} | flagged | 模型裁定 |
| `REFGRAPH_RETRACTION_EDGE` | 图边 `type` ∈ {retracts, retraction, is-retraction-of, retracted-by} 指向本记录 | severe | 排除 |
| `STATUS_SOURCE_CONFLICT` | 派生：一源称正常（published/active），另一源称撤回/撤稿 | flagged（附加在 severe 记录上） | 以更严重证据为准，冲突如实披露 |
| `IMPORT_STATE_WITHDRAWN` | import_state 条目 `status` ∈ {withdrawn, removed, retracted, deleted} 且命中本记录 | severe | 排除出候选池并注明原因 |

## preprint / 版本标记（供配对，不改变状态类）

| code | 信号来源 | severity | 用途 |
|---|---|---|---|
| `CROSSREF_POSTED_CONTENT` | Crossref `type == "posted-content"` 或 `subtype == "preprint"` | info | 标记 version_role=preprint |
| `CROSSREF_PREPRINT_RELATION` | `relation-type` ∈ {`is-preprint-of`, `has-preprint`} | info | 显式配对证据 |
| `EPMC_PREPRINT` | EuropePMC pubType 含 `"Preprint"`（不区分大小写）或 `source == "PPR"` | info | 同上 |

## import_state 簿记

| code | 来源 | severity | 处置 |
|---|---|---|---|
| `IMPORT_STATE_INCONSISTENT` | import_state 声称已导入的标识符在所有在场响应中均不存在 | warning | 隔离该**声明**（quarantine entry），在 uncertainty 中报告；不影响候选池 |
| `IMPORT_NOT_YET_IMPORTED` | 记录在响应中存在但 import_state 无对应条目 | info | 仅信息性记录 |

## 准确性声明与不确定项

- Crossref 关系类型字符串（`is-retraction-of`、`has-retraction`、`is-erratum-of`、
  `has-erratum`、`is-expression-of-concern-of`、`has-expression-of-concern`、
  `is-preprint-of`、`has-preprint`、`update-to`、`update-by`）以 Crossref REST API
  公开文档的 relation 词汇为准，匹配时**不区分大小写**。
- EuropePMC pubType 字符串 `"Retraction of Publication"` / `"Retracted Publication"`
  为 EuropePMC REST 返回中的既有取值；`"Erratum"`、`"Expression of Concern"`
  的实际大小写/复数形态**不完全确定**——脚本按小写化后匹配并兼容
  `"Correction"`，以降低漏检风险。
- Crossmark `update-to[].type` 的具体取值集合在材料中不可核验时，脚本仅原样
  记录于 `detail`，不据此升级 severe——升级须由模型裁定。
- 任何上表未覆盖的新信号，必须先在本文件登记 code 与 severity，再入脚本。
