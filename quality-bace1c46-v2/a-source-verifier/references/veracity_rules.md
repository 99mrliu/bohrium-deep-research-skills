# 真实性核验规则表（veracity rules）

本文件是 crosscheck.py / build_result.py 判定逻辑的规范说明。改动脚本前先
改本表，保持一致。

## 1. 归一化规则（normalization）

对标题、作者姓等文本字段，比较前依次执行：

1. **NFKC**：`unicodedata.normalize("NFKC", s)`，兼容字符归并；
2. **casefold**：大小写无关；
3. **标点剥离**：非 `\w`/空白字符替换为空格（Unicode 模式）；
4. **空白折叠**：连续空白压成单个空格并去首尾。

DOI 额外规则：casefold 后做子串包含判断；**年份检索前必须先从正文中剥离
DOI/URL**（`10.\d{4,9}/...`、`https?://...`），否则 DOI 内嵌年份造成假命中。
年份按数字边界检索（`(?<!\d)YYYY(?!\d)`），避免命中页码片段。

## 2. 逐字段核对项

| 检查项 | 定义 |
|---|---|
| `title_exact` | 归一化标题是归一化正文的子串 |
| `title_fuzzy` | 标题 token 集与**正文每一行** token 集的 Jaccard 最大值 ≥ **0.8** |
| `year_match` | 快照年份在剥离 DOI/URL 的正文中按数字边界命中 |
| `doi_in_text` | casefold 后的 DOI 出现在正文中 |
| `first_author_surname_in_text` | 归一化首作者姓出现在归一化正文中 |

说明：模糊匹配采用**逐行 Jaccard**而非"标题 vs 全文"——论文标题通常独占一
行，逐行比较不会被全文 token 稀释；与全文直接算 Jaccard 恒近 0，无意义。

## 3. 判定阶梯（verdict ladder）

针对单个 来源对（文本文件 × 快照记录）：

| 判定 | 条件 |
|---|---|
| `verified` | 标题命中（exact 或 fuzzy）且其余有值字段全部命中 |
| `mismatch` | 标题命中但至少一个有值字段不一致（在 `mismatched_fields` 中逐字段列出）；或标题完全未命中 |
| `unverifiable` | 记录缺少全部可比字段，或文本层不可用（说明原因） |

针对单个来源文件（ledger 粒度）：

- 文本文件：其所有来源对中存在 `verified` → 该文件 `verified`；全部
  `unverifiable` → `unverifiable`；否则 `mismatch`；
- 快照文件：风味可识别且提取到 ≥1 条记录 → `verified`（"可解析"意义），
  其与正文的字段级矛盾通过对应文本文件的 mismatch 与 uncertainties 表达；
- 其他/不可解析/编排外文件 → `unverifiable` + 原因；
- `case.json` / `task.md` 属编排文件，**不进 ledger、不参与 status**。

铁律：mismatch 只上报，不静默修复，不猜测"哪个是对的"。

## 4. 弃权条件（abstain → unverifiable）

以下情形模型侧应主动弃权而非强行比对：

- **仅摘要条目**：正文层只有 abstract，无标题页/页眉锚点；
- **非拉丁文字标题**：归一化对 CJK 等文字失真，标题匹配不可靠（可仅核
  DOI/年份，并注明降级置信度）；
- **无文本层扫描件 PDF**：pdftotext 缺失或输出为空；
- **快照字段全缺**：无标题/年份/DOI/作者任一可用。

弃权必须写明原因，进入 `unverifiable` 与 uncertainties。

## 5. 判定如何汇入 result.json 的 status

| 情形 | status |
|---|---|
| 全部来源 `verified`（且 ≥1 个来源） | `success` |
| 存在任一 `mismatch` 或 `unverifiable` | `partial`，uncertainties 陈述限制与计数 |
| 零来源（空 ledger） | `partial`，空 ledger + 明确解释 |
| 连核验都无法执行（如无 manifest 且无法重建） | `failed` |

附加：`duplicates` 与 `version_conflicts` 总是如实列出并写入
uncertainties，但**不改变**上表的 status 映射（重复/冲突本身是材料现状的
客观记录，不等同于核验失败）；下游是否采信由 `usable_for_assessment`
（仅 `verified` 为 true）与各条不确定性说明共同约束。
