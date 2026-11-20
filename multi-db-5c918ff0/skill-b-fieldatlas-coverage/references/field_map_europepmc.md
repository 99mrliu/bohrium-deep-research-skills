# 字段映射表 — EuropePMC（search API 结果 / 单条结果）

> 归一字段全集（FIELDS）见文末；缺失三级语义判定伪代码见
> `references/gap_taxonomy.md` §0。记录定位：列表响应
> `resultList.result[i]`；`hitCount`/`request` 仅供状态台账使用。

## 映射表

| 归一字段 | 源字段路径 | 提取 / 清洗规则 | 语义注释 |
|---|---|---|---|
| identifiers.doi | `result[i].doi` | 去前缀 + 小写化（同 Crossref 规则） | — |
| identifiers.pmid | `result[i].pmid`；缺失且 `source=="MED"` 时回退 `id` | 字符串原样 | `id` 仅在 MED 源下即 PMID |
| identifiers.pmcid | `result[i].pmcid` | 字符串原样 | 仅开放全文记录有 |
| title | `result[i].title` | 压缩空白 | EuropePMC 题名常以句点结尾，聚类前须归一化（去标点、小写） |
| authors | `result[i].authorString`（优先）→ `authorList.author[*].fullName` | 解析 `"Surname I; Surname J"` 串：按 `;` 切分；每段含 `,` 走 `Family, Given`；否则从尾部收集全大写首字母 token（`L`、`J P`、`L.` 去点后 `^[A-Z]{1,4}$`）作 given，其余作 family；统一为 `[{family, given}]` | **authorString 为空字符串是典型 unknown 案例**（字段存在但无值）；单 token 作者告警留痕 |
| container | `journalInfo.journal.title` | 嵌套提取；`journalInfo` 存在而 `journal` 嵌套缺失 → **schema 漂移留痕**，字段降级 | 漂移示例见 examples（pmid 99001234） |
| year | `journalInfo.yearOfPublication` → `pubYear` | 取 4 位年份 | 两字段并存且不一致时取 `journalInfo.yearOfPublication` 并**告警留痕** |
| volume | `journalInfo.volume` → `journalInfo.journal.volume` | 字符串原样 | EuropePMC 部分版本将卷期放在 journal 嵌套内 |
| issue | `journalInfo.issue` → `journalInfo.journal.issue` | 字符串原样 | 同上 |
| pages | `journalInfo.pages` → `pageInfo` | 字符串原样 | — |
| type | `pubTypeList.pubType[]` | 列表 `; ` 拼接 | pubType 是**多值词表**（如 `Journal Article; Retracted Publication`），跨库与 Crossref `type` 仅作参考 |
| abstract | `abstractText` | 剥离 HTML 标签 + 实体反转义（EuropePMC 摘要常含 `<p><b>` 标签） | 载荷级动态判定同 Crossref |
| pub_date | `firstPublicationDate` → `journalInfo.printPublicationDate` → `journalInfo.electronicPublicationDate` | 字符串原样 | `firstPublicationDate` 是 EuropePMC 归一的“首次发表”日期；print/electronic 原始日期语义不等价，仅在首选缺失时回退 |
| cited_by | `citedByCount` | 转 int | EuropePMC 内部被引计数，口径与 Crossref 不等价，**不可直接合并求和** |
| references | `referenceList.reference[]` | 有数组取 `len` | 检索 API 通常不含；载荷级动态判定 |
| license | `license` | 字符串原样 | 载荷级动态判定 |
| status | `pubTypeList.pubType[]` | pubType 文本匹配 `retract\|withdraw` → 标记拼接；有 pubTypeList 但无标记 → `active_no_marker` | `Retracted Publication` / `Retraction of Publication` 是本 bundle 的撤回识别依据；标题前缀 `Retracted:` 亦计入（通用提取器） |

## 静态 not_provided 清单

无（EuropePMC 检索结果对全部 17 个归一字段均为“schema 提供但记录可能为空”，
故以载荷级动态判定 + unknown/missing 区分为准）。

## 载荷级动态判定示例

- `authorString: ""` → `authors = unknown`（字段存在、值为空）；
- 载荷内其他记录有 `journalInfo.journal`、本条嵌套缺失 → `container = missing`
  （同时 schema_drift 留痕）；
- 整载荷无 `referenceList` 键 → 全部记录 `references = not_provided`。
