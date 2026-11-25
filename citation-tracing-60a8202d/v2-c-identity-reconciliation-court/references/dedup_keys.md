# 去重键（blocking keys）与成对打分表

本文档说明 `identity_merge.py` 的身份裁决方法：先做 blocking 缩小比较空间，再块内成对打分，最后阈值裁决。

## 1. 规范化

| 键 | 规则 |
|---|---|
| DOI 规范化 | 小写；剥去 `https://doi.org/`、`http://doi.org/`、`doi.org/`、`doi:` 前缀；去首尾空白与尾部 `.,;)` |
| 标题规范化 | NFKC 兼容分解 → 小写 → 去全部标点 → 坍缩空白；停用词（a/an/the/of/for/on/in/and/or/to/with/by/via/from/at/as/is/are/using/use/its）从 token 集合剔除 |
| 作者姓 | `Last, First` 取逗号前；`First Last` 取末词；`{family}`/`{family_name}`/`{surname}` 优先；小写 |

## 2. Blocking（三类块，任一命中即成对比较）

| 块键 | 构造 | 召回的互补关系 |
|---|---|---|
| `doi` | 规范化 DOI 精确相等 | 同文不同名（标题差异大）也能召回 |
| `title40` | 标题规范化前 40 字符 | 同文大小写/副标题差异、截断差异 |
| `surname_year` | 第一作者姓 + 年份 | 同库双键都缺（如无 DOI 的会议版）兜底 |

两键都缺的记录不参与 title40/surname_year 之外的精确匹配，可能落为独立实体（诚实保留）。

## 3. 成对打分（加权线性组合）

| 组件 | 计算 | 权重 |
|---|---|---|
| 标题 token | `max(Jaccard, containment)`；containment = |交| / min(|A|,|B|)，副标题差异兜底 | 0.50 |
| 作者重叠 | 作者姓集合 Jaccard | 0.25 |
| 年份差 | 0 年=1.0；1 年=0.7；2 年=0.3；≥3 年=0；任一缺失=0.5（中性） | 0.10 |
| venue 相似 | venue 规范化 token Jaccard；任一缺失=0.5（中性） | 0.10 |
| DOI 前缀类型 | 同前缀=1.0；一方是 arXiv/预印本前缀=0.6（常见版本对）；否则=0.4；任一缺 DOI=0.5 | 0.05 |

特殊规则：
- **同规范化 DOI** → 直接 1.0（强制合并），即使标题差异大。
- **作者矛盾护栏**：双方都有非空作者姓集合且交集为空、且 DOI 不同 → 得分压到 ≤0.55（阻断同名不同文误并）。

## 4. 阈值裁决

| 得分 | 裁决 | 落点 |
|---|---|---|
| ≥ 0.85 | 合并 | 并查集合并，进入合并组 |
| 0.60 – 0.85 | 存疑 | 不自动合并，写入 `review_queue`（带组件分与 locator），需人工复核 |
| < 0.60 | 不合并 | 保持独立实体 |

## 5. 特殊身份情形

- **同名不同文（distinct_same_title）**：标题 Jaccard ≥ 0.9、作者重叠 = 0、无同 DOI，且未合并 → 标注并写台账；audit 据此豁免"标题键共享"检查。
- **同文不同名（same_work_different_title）**：同 DOI 但标题 Jaccard < 0.5 → 强制合并，双标题保留在 `merge_evidence.conflicts.title` 与台账 `titles` 字段。

## 6. 阈值示例（合成语料实测）

| 对 | 组件 | 总分 | 裁决 |
|---|---|---|---|
| 期刊版 vs arXiv 预印本（同作者、±1 年、副标题差异） | title=1.0, authors=1.0, year=0.7, venue=0, doi_prefix=1.0 | 0.87 | merge |
| 同名不同文（同标题、作者无交、年份差 3） | title=1.0, authors=0, year=0, venue=0, doi_prefix=1.0（护栏压分） | 0.55 | no_merge → distinct_same_title |
| 同文不同名（同 DOI、标题差异大） | same_doi=true | 1.00 | merge → same_work_different_title |
