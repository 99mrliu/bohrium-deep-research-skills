# matching_rules.md — 分层身份匹配规则、理由码表与仲裁政策

本文件是 `scripts/dedup.py` 的规范文档：规则改动必须先改本文件再改脚本，
二者不一致以本文件为准并视为缺陷。目标：**每一次归并/拒并/送裁都可解释、
可复算、可重放**（同输入同输出）。

## 1. 输入归一前提（normalize_records.py 已完成）

| 要素 | 归一规则 |
|---|---|
| DOI | 去 `https://doi.org/`、`doi:` 前缀，小写，去全部空白 |
| PMID | 仅保留数字 |
| PMCID | 大写 `PMC`+数字 |
| 题名 | 去 HTML 标签 → 小写 → 非标点字母数字折为空格 → 去停用词 → 折叠空白 |
| 年份 | 4 位数字（1500–2099），issued/published/date/year 多字段回退 |
| 首作者姓 | `authors_norm[0].family` 小写、去非字母字符；兼容 `Family, Given` 与 `Surname I.` 两种串格式 |

## 2. 分层规则（严格按 Tier 顺序，先到先得）

### Tier 1 — 标识符精确匹配（自动归并）

- 归一 DOI 相等 → 归并，理由码 `T1_DOI_EXACT`。
- 归一 PMID 相等 → `T1_PMID_EXACT`；归一 PMCID 相等 → `T1_PMCID_EXACT`。
- **跨标识符互链**：一条记录只有 PMID、另一条只有 DOI 时，仅当引用图 /
  组织方 id 映射表中**显式**给出二者对应关系（aliases / same_work /
  id_map 等结构）才归并，理由码 `T1_ID_CROSSREF`，evidence 必须记录
  别名内容与来源文件。**禁止臆造 pmid↔doi 映射**：无显式对应时降级到
  Tier 2/Tier 3 按书目证据判断，绝不凭"看起来同一篇"补映射。
- 引用图中的**引用边（citations）不是同作品证据**，不得触发归并。

### Tier 2 — 归一题名 + 年份 + 首作者姓（自动归并 / 自动拒并）

三者全等（且均非空）→ 归并，理由码 `T2_TITLE_YEAR_FIRSTAUTHOR`。
题名与首作者全等但年份均存在且不同 → 判**非重复**，理由码
`NON_DUP_YEAR_MISMATCH`（典型：年度综述、会议/期刊双版本不同年）。
年份任一缺失 → `NON_DUP_YEAR_UNKNOWN`，不自动归并（可转入 Tier 3 视野外，
保持分簇，必要时由模型在仲裁环节处理）。

### Tier 3 — 模糊匹配（只送仲裁，绝不自动合并）

对未被 Tier 1/2 决定的记录对，同时满足：
1. 归一词集合 Jaccard ≥ 0.6（`--thresholds jaccard` 可调）；
2. 作者姓集合 Jaccard 重合 ≥ 0.5（`author_overlap`）；
3. 年份差 ≤ 1（`year_window`）；

→ 判 `arbitrate`，理由码 `T3_FUZZY_ARBITRATE`，进入仲裁队列。
触发相似（Jaccard 达标）但年份超窗 → `NON_DUP_YEAR_MISMATCH`；
作者重合不达标 → `NON_DUP_AUTHOR_MISMATCH`。低相似对（Jaccard < 阈值）
不写入日志以降噪。

## 3. 理由码表（dedup_decisions.jsonl）

| reason_code | tier | match | 含义 |
|---|---|---|---|
| `T1_DOI_EXACT` | 1 | true | 归一 DOI 精确相等 |
| `T1_PMID_EXACT` | 1 | true | 归一 PMID 精确相等 |
| `T1_PMCID_EXACT` | 1 | true | 归一 PMCID 精确相等 |
| `T1_ID_CROSSREF` | 1 | true | 引用图显式别名的跨标识符互链 |
| `T2_TITLE_YEAR_FIRSTAUTHOR` | 2 | true | 归一题名+年份+首作者姓全等 |
| `T3_FUZZY_ARBITRATE` | 3 | arbitrate | 模糊相似达标，送仲裁 |
| `NON_DUP_YEAR_MISMATCH` | 2/3 | false | 其余达标但年份冲突/超窗 |
| `NON_DUP_YEAR_UNKNOWN` | 2 | false | 年份缺失，Tier2 不予自动归并 |
| `NON_DUP_AUTHOR_MISMATCH` | 3 | false | 题名相似但作者姓重合不足 |

每条判定记录 `{pair, tier, match, reason_code, evidence}`；evidence 含
触发值（DOI/别名/归一题名/Jaccard/重合度/年份差/阈值），支持第三方复算。

## 4. 仲裁政策（哪些必须人工/模型，哪些允许脚本自动）

**允许脚本自动决定（无需仲裁）**：
- Tier 1 全部精确归并（含显式别名的跨标识符互链）；
- Tier 2 全等归并；
- `NON_DUP_*` 拒并（证据为硬冲突：年份不同、作者不重合）。

**必须人工/模型仲裁（脚本只排队）**：
- `T3_FUZZY_ARBITRATE`：一切模糊相似对；
- 同簇出现多个不同 DOI/PMID（merge_records.py 记入 conflict_log，
  需复核是否误并）；
- 年份缺失但其余证据强的对（`NON_DUP_YEAR_UNKNOWN`）如业务上重要，
  模型可主动送裁。

**仲裁操作**（模型，SKILL.md 步骤 5）：逐条审 `arbitration_queue.json`，
写 `arbitrations.json`：`{"pair": [uidA, uidB], "decision": "merge"|"split",
"decided_by": "model", "rationale": "书面依据"}`；rationale 必填，
空 rationale 的决议视为无效并写入 uncertainty。无仲裁文件时
merge_records.py 如实标注 `arbitration_status=pending_arbitration`，
result.json status 不得为 complete。

**阻断规模控制**：Tier 3 只对 Jaccard ≥ 阈值的候选对计算，日志量与
候选对数同阶；材料规模上百条时仍远优于全对比较。
