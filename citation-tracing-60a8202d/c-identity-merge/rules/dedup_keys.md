# 去重键与合并规则（dedup keys & merge rules）

## 1. 规范化

| 字段 | 规范化 |
|-|-|
| DOI | 小写，去 `https://doi.org/`、`doi:` 等前缀 |
| arXiv | 提取 `YYMM.NNNNN`（去版本号 v N）或老格式 `archive/NNNNNNN` |
| 标题指纹 | 去 HTML 标签 → 小写 → 非字母数字折叠为空格 → 压缩空格 |
| 主题词 | 指纹分词去停用词 |
| 作者姓 | 取逗号前/末词，小写 |

## 2. 分块键（blocking keys）

1. `doi:<norm>`；2. `arxiv:<norm>`；3. `tfp:<标题指纹前80字符>`；4. `tok:<首主题词|末主题词>`；5. `ay:<第一作者姓|年份>`。
块 >200 条视为病态块（通常为缺标题桶）跳过并记日志。

## 3. 决策矩阵

| 条件 | 决策 | 置信 |
|-|-|-|
| DOI 相同 | AUTO_MERGE | 1.00 |
| arXiv 相同 | AUTO_MERGE | 1.00 |
| 标题指纹一致 ∧ 年份差≤1 ∧（作者重叠≥1 或一方缺作者） | AUTO_MERGE | 0.97 |
| 标题 Jaccard≥0.90 ∧ 第一作者相同 ∧ 年份差≤2 | AUTO_MERGE | 0.93 |
| 标题 Jaccard≥0.80 且 DOI 冲突 | REVIEW | — |
| 标题指纹一致 ∧ 作者集合不相交 ∧ 年份差≤2 | REVIEW（疑似同名不同文） | — |
| 标题 Jaccard≥0.80 ∧（第一作者相同或重叠≥2）但未达自动条件 | REVIEW | — |
| 其他 | KEEP_SEPARATE | — |

REVIEW 对永远不进同一簇；自查脚本强制校验。

## 4. 版本分类

- preprint：Crossref type 含 posted/preprint，或 venue 含 arXiv/bioRxiv/SSRN/ChemRxiv，或有 arXiv 号而无 DOI。
- conference：type 含 proceedings/conference。
- journal：type 含 journal。
- supplement：type 或标题前 80 字符含 supplement。
- dataset / book / unknown：按 type；无法判定时 unknown，不猜。

## 5. canonical 选择与字段合并

- 优先级：journal > conference > book > preprint > dataset/supplement > unknown；同级取字段完整度（DOI/arXiv/标题/年份/venue/卷/页＋作者数截断加权）最高者。
- 簇级标识并集：`all_doi`、`all_arxiv`、`all_ext_ids`；成员原始记录与 locator 全部保留在 `members`。
- 字段冲突（年份差、标题措辞、卷期差异）记入 `field_conflicts`；canonical 字段不做跨成员拼接（避免制造不存在的记录）。

## 6. 诚实性

- 合并只基于记录中存在的字段；不推测缺失 DOI、不补造作者。
- 每次 AUTO_MERGE 的证据（命中的键、相似度、年份差）写入 merge_ledger，复核人可逐对回指源文件。
- 同文不同名（DOI 相同标题不同）合法合并但必须在 `field_conflicts` 留痕；同名不同文一律进 REVIEW，宁可漏并不可错并。
