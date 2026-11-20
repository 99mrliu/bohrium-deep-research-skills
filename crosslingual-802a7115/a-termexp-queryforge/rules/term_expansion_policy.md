# 术语扩展与受控翻译规则（term expansion policy）

本规则约束 Agent 编写案例术语表与受控翻译条目时的判断，以及两个脚本的实现语义。脚本实际执行的规则在文中标注「（脚本强制）」；其余为 Agent 操作规范。

## 1. 何时扩展

- 只扩展研究问题中**承载检索区分度**的概念：疾病/生物体/方法/材料/表型等实体概念。问题中的泛用词（study、analysis、"研究"、"调查"）不建概念。
- 一个概念进入术语表的必要条件：能在至少一个目标语种给出**有来源**的变体（受控词表、种子论文关键词、作者给出译名、或附回译证据的受控翻译）。拍脑袋译名禁止入表。
- 概念数以查询可核对为限：每个概念在查询中是一个 AND 子句，概念越多各语种查询越容易整体零命中。建议 2–6 个概念；超出时按与研究问题的相关性排序取舍，取舍理由写入 uncertainty。

## 2. 变体类型与发散控制

变体 `type` 取值与使用边界：

| type | 含义 | 使用规则 |
|-|-|-|
| preferred | 学科规范用词（MeSH/DeCS/AGROVOC 等受控词表入口词） | 每概念每语种至多 1–2 个；必须带来源标识 |
| synonym | 同义/近义表达 | 只收论文中真实出现或受控词表收录的；不收字面机翻同义词 |
| abbreviation | 缩写（DENV、GSDMD） | 必须与全称同概念内 OR 联用；跨语种歧义须写 `ambiguity_note`（见 §5） |
| transliteration | 音译/外来语写法（日语片假名、俄语转写等） | 与本地译名并存；单一来源时标 unverified |
| hypernym / hyponym | 上下位词 | 见 §3 边界 |
| latin-name | 学名（Glycine max） | 跨语种通用，lang 标 en 或实际使用语种均可，但同一表面形式只入表一次 |

发散控制（Agent 规范）：每概念每语种变体 ≤ 4 个。变体多不提升可核对性，只放大假阳性；新增变体前问一句"这个表面形式会出现在目标语种论文的标题/摘要/关键词里吗"，答不上来就不加。

## 3. 上下位词使用边界

- 下位词（hyponym）只在研究问题明确覆盖该下位概念时加入，且查询时不替代上位词，只并列 OR。
- 上位词（hypernym）原则上**不**用于查询（召回暴涨且偏离问题）；仅当某语种该概念完全无对应译法时，可作为该语种查询的降级子句使用，必须标 `unverified` 并在 uncertainty 中说明"该语种使用上位词降级召回，命中需人工复核相关性"。
- 词表中的上下位关系来自受控词表时，在 `source` 中注明词表与条目号。

## 4. 受控翻译与回译校验（脚本强制）

- 术语表未覆盖的 概念×语种 对全部进入 `to_translate`；脚本**不**自动翻译。
- Agent 通过 `--translations` 文件供给译名，字段：`concept_id`、`lang`、`term`，建议 `translation_basis`（翻译依据，如所用词表/模型与日期）与 `back_translation`（回译）。
- 回译校验判据（term_table.py `verify_roundtrip`）：`back_translation` 经规范化（NFKD 变音折叠、小写、空白归一）后等于概念 `label_en` 或任一既有 en 变体 → `verified=true`，`verification=round-trip:back-translation-match`；不一致 → `verified=false`、`status=unverified`、置信减半、`verification=round-trip:failed`；无 `back_translation` → 维持来源声明的 verified 标志，标注 `round-trip:no-evidence`。
- 判据是**必要条件而非充分条件**：回译一致不保证译名是学科用词（如 "cell scorching" 回译也能对上焦亡的英文？对不上——这正是回译能挡住字面机翻的原因；但同义字面译名如 "inflammatory cell death" 可能漏过），因此 verified 变体的 `source` 仍须可供人工追查。

## 5. unverified 术语的降级规则（脚本强制）

- unverified 变体**保留**在对应语种查询中（删除会直接牺牲召回），但：
  1. query_log 中逐条标 `verified=false`，查询的 `generation_basis.n_unverified_variants` 计数；
  2. hit_alignment 中命中它的位置标 `UNVERIFIED`；
  3. result.json 的 uncertainty 汇总"N 个 unverified 变体参与查询，仅经其召回的命中需人工核对"。
- 人工核对发现 unverified 变体确实错误时：在术语表中删除该变体重跑，删除动作记入 `change_records`；不得直接改结果文件掩盖。

## 6. 缩写跨语种歧义处理

- 缩写在不同语种文献中可能撞形（如 DENV 与血清型编号、ACE 在多领域复用）。规则：
  1. 缩写变体必须带 `ambiguity_note`，说明已知歧义；
  2. 查询生成时缩写与全称同概念内 OR（脚本行为：同 concept 同 lang 的所有变体 OR），不单独成句；
  3. 命中若**仅**由缩写变体召回且该缩写有 `ambiguity_note`，Agent 在交付说明中将其列为需人工确认的假阳性候选（脚本不自动剔除）。

## 7. 匹配语义与局限性（脚本行为声明）

- 拉丁文变体：NFKD 分解去组合符（ á→a、ü→u、ç→c ），ß→ss，小写，词边界子串匹配。不做词形还原：复数、性数变化（葡 piroptoses、德 Sojabohnen）须作为变体显式入表。
- CJK/假名变体：直接子串匹配。中文简繁、日文新旧字体不互通，须显式列变体。
- 命中判据：某语种查询中**全部已覆盖概念**（uncovered 概念已从该语种查询剔除）各至少一个变体命中 → 该命中被该语种查询召回。partial 查询召回的命中带 `completeness=partial` 标记，相关性需人工复核。

## 8. 诚实性底线

- 不补造文献：命中只能来自解析过的本地记录；术语表空、语料空、语种零命中都如实报告。
- 不伪造来源：变体 `source` 只能是真实依据（词表条目号、种子论文关键词、作者译名、Agent 受控翻译及依据）；编不出 source 的变体不许入表。
- 归因不推断：命中记录的 language/version/translation_of 只转写记录原文字段；记录没说的，结果就是空。
