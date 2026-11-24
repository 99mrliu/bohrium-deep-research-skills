# 匹配规则与原因码（matching-rules.md）

本文件枚举 `identity_arbiter.py` 的全部分层匹配规则与 `dedup_decisions.jsonl` 中可能出现的
`reason_code`。每一对候选记录（records 的两两组合，按记录 id 排序后遍历）都会产出恰好一条
JSONL 决策行，保证判定可解释、可回放。

## 标识符与字段规范化

- **DOI**：转小写；剥除 `https://doi.org/`、`http://doi.org/`、`https://dx.doi.org/`、
  `http://dx.doi.org/`、`doi:` 前缀；去除首尾空白与尾部标点 `. , ; :`。
- **PMID / PMCID**：精确字符串（仅去首尾空白），不做任何推断式映射。
- **标题**：NFC 归一化 → HTML 实体反转义 → 去 HTML 标签 → 小写 → 标点替换为空格 → 折叠空白。
- **第一作者姓氏**：Crossref 取 `author[].family`；EuropePMC 取 `authorString` 逗号分块的
  首 token；publisher 兼容 dict（`family`/`surname`）与字符串（含逗号取逗号前，否则取末 token）。
- **字段状态三分**：`missing`（键不存在）/ `unknown`（键存在但为 null 或空）/
  `not_provided`（值为 `not_provided`、`n/a` 等显式哨兵）。三者在合并时区别对待，
  不得把 missing 当作"值为空"参与冲突判定。

## 分层匹配

| 层级 | 名称 | 条件 | 处置 |
|---|---|---|---|
| T1 | identifier-exact | 共享规范化 DOI；或共享 PMID/PMCID；或命中 reference_graph / import_state 中**显式声明**的别名对 | 自动合并 |
| T2 | bibliographic-exact | 规范化标题完全相同 **且** 年份相同（两侧均非空）**且** 第一作者姓氏相同 | 自动合并 |
| T3 | fuzzy candidate | 标题 token 集合 Jaccard ≥ 0.6 **且** 作者姓氏重叠度 ≥ 0.5 **且** \|年份差\| ≤ 1（两侧年份均非空） | **只进 arbitration_queue.json，绝不自动合并** |
| NONE | — | 以上均不满足 | 保持独立 |

- 层级按 T1 → T2 → T3 顺序判定，命中即停，决策行记录命中层级。
- **跨标识符链接（pmid↔doi 等）只允许来自 reference_graph / import_state 的显式别名对
  （`aliases` / `known_aliases` 数组），严禁发明映射。**
- 姓氏重叠度定义：|交集| / min(|A|, |B|)；任一侧无姓氏时为 0.0（不会误中 T3）。
- T3 对可通过 `--adjudications FILE` 应用人工/模型裁决
  （`[{"pair":[idA,idB],"decision":"merge|separate","rationale":"..."}]`）；
  无裁决文件时 T3 对保持独立，`status=partial` 并在 `uncertainty` 中显式列出。

## reason_code 枚举

| reason_code | 含义 | decision |
|---|---|---|
| `T1_SHARED_DOI` | 共享规范化 DOI | merge |
| `T1_SHARED_PMID` | 共享 PMID 或 PMCID | merge |
| `T1_ALIAS_LINK` | 命中显式别名对（跨标识符） | merge |
| `T2_BIBLIOGRAPHIC_EXACT` | 标题+年份+第一作者姓氏全同 | merge |
| `T3_FUZZY_CANDIDATE` | 模糊候选，待仲裁 | pending_arbitration |
| `T3_ADJUDICATED_MERGE` | T3 经裁决文件判为合并（附 rationale） | merge |
| `T3_ADJUDICATED_SEPARATE` | T3 经裁决文件判为独立（附 rationale） | separate |
| `NO_MATCH` | 未命中任何层级 | separate |

每条决策行的 `evidence` 固定包含：`shared_identifiers`（共享标识符列表）、
`title_sim`（Jaccard，4 位小数）、`surname_overlap`（4 位小数）、`year_diff`
（整数或 null）；裁决行另附 `adjudication_rationale`。
