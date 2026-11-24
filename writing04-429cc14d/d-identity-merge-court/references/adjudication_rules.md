# 裁决规则 M1–M5 精确定义（identity-merge-court）

本文件是 merge_adjudicate.py 校验逻辑的可读规范。规则只**限制 merge**；
`keep_separate` 与 `human_queue` 永不拒绝（保守方向不造成不可逆后果）。

## 术语

- **规范化 DOI**：小写、去 `https://doi.org/` / `http://dx.doi.org/` / `doi:` 前缀、去首尾空白
  与句点；`doi` 字段缺失时可从 `url` 字段提取，**绝不**从 `note` 等自由文本提取身份 DOI。
- **规范化题名**：NFKC → casefold → 去标点（Unicode 非字母数字折叠为空白）→ 空白折叠 →
  去停用冠词（the / a / an）。
- **书目坐标**：year / volume / issue / pages / article_number。规范化后比较
  （连字符与 en dash 折叠、大小写折叠）。
- ** corroboration（佐证）**：第一作者姓、年份、容器三项坐标中规范化一致的个数。
- **证据分级**：strong = 共享规范化标识符（DOI/PMID/arXiv）或材料内明确声明的版本/翻译关系；
  moderate = 规范化题名相同且佐证 ≥2，或同姓同年 Jaccard≥0.8 且容器一致，或仅材料内
  translation_of 线索；weak = 仅题名相似而无佐证。组分级取组内信号最高级。

## M1 — 同 DOI 且元数据一致 → 可 merge

**定义**：组内 ≥2 名成员持有同一规范化 DOI，且所有成员的书目坐标规范化后一致
（冲突表中 year/volume/issue/pages/article_number 均 `normalized_equal=true` 或缺失）。

- 正例：Crossref 记录 `10.55555/JNMC.2024.001` 与 PubMed 记录 `10.55555/jnmc.2024.001`，
  年/卷/期/页一致 → merge，canonical 取字段最全者。
- 反例：见 M2。
- 注意：题名/刊名/作者的语种与格式差异（中英译名、罗马化、大小写、连字符样式）
  **不构成 M1 的障碍**，记入 exception list 供人工抽查即可。理由：同一 DOI 由同一注册方
  颁发给同一工作；CNKI/Crossref/EndNote 对同一刊物的命名差异是已知的导出现象。

## M2 — 同 DOI 但元数据冲突 → human_queue，禁止自动并

**定义**：组内 ≥2 名成员持有同一规范化 DOI，但**书目坐标**（年/卷/期/页/文章号）存在
规范化后仍不一致的冲突。

- 正例（应 human_queue）：两条记录共享 `10.55555/abl.2021.033`，但年份 2021 vs 2022、
  页码 77–88 vs 177–188 冲突 → 禁止 merge；核查 DOI 落地页后再判。
- 反例：页码 `3561-3574` vs `3561–3574`（连字符样式差异，规范化后一致）→ 不触发 M2。
- 脚本行为：对此类组判 merge 直接拒绝（退出码 1，不写产物）。

## M3 — 仅题名相似无 corroboration → 不可 merge

**定义**：组证据分级为 weak 且不共享规范化 DOI——即匹配只建立在题名相似上
（裸题名相同但作者/年/容器全无佐证，或 Jaccard 触达但容器不同）。

- 正例（应 keep_separate）：两篇题名同为 "Digital twins in manufacturing"，但第一作者、
  年份、容器、卷页、DOI 全异 → 短通用题名撞车，keep_separate。
- 反例：规范化题名相同 + 同第一作者 + 同年 + 同容器（佐证 3/3，moderate）→ 不在 M3 射程，
  可 merge。
- 脚本行为：weak 组判 merge 直接拒绝。

## M4 — 预印本-正式版关系成立 → 并入正式版，留谱系

**定义**：规范化题名相同，一方为预印本（`type=preprint` 或有 arXiv id 且无容器），另一方为
正式版，且满足二者之一：(a) 共享规范化标识符；(b) 材料内证据（预印本 note 声明
"Published in ... DOI ..." 或含正式版容器名）。

- 约束：**canonical 必须是正式版**（脚本强制）；年份差（预印本年 < 正式版年）属正常现象，
  入 exception list 而非 M2 冲突。
- 反例：会议**扩展版**与期刊版是不同工作（新增实质内容）→ 不适用 M4，keep_separate。
- 反例：无 (a)(b) 任何一条，仅凭"题名像 + 都有 arXiv"→ 降级 moderate/weak，human_queue。
- 禁止事项：**绝不凭印象补造正式版 DOI**。材料内没有正式版 DOI 时，canonical 的 doi 字段
  保持空缺，谱系中只记录已有标识符。

### 谱系记录格式（写入 canonical 记录的 `lineage` 数组）

```json
{
  "relation": "published_version_of",
  "canonical_record_id": "R009",
  "preprint_record_id": "R008",
  "preprint_arxiv": "2401.98765",
  "preprint_url": "https://arxiv.org/abs/2401.98765",
  "preprint_year": 2024,
  "preprint_version": "v2",
  "redirect": "R008 -> R009",
  "evidence": "材料内 note 字段声明版本关系"
}
```

三要素缺一不可：**preprint id**（arXiv 号/URL）、**版本关系**（relation + evidence）、
**重定向**（redirect，且同步写入 redirect_map.json 的 record_redirects 与
cite_key_redirects）。

## M5 — 同人不同作保护：同姓同年但题名/容器显著不同 → keep_separate

**定义**：组由 S5 信号（同第一作者姓 + 同年 + 题名 token Jaccard ≥ 0.8）触达，但
规范化容器不一致且规范化题名不相同。

- 正例（应 keep_separate）：Zhang, Wei 的 "Deep learning models for short term urban
  traffic flow prediction"（IEEE OJIT）与 Zhang, Lei 的 "...traffic speed prediction"
  （Transportation Research Procedia）：同姓同年、题名一词之差，但作者给定名不同、
  共同作者不同、容器/卷页/DOI 全异——是同名姓作者的两篇不同文献。
- 反例：同第一作者（姓名全同）+ 同年 + 同容器同卷 + 题名仅多副标题词 → 不在 M5 射程，
  可按 moderate 证据 merge。
- 脚本行为：此类组判 merge 直接拒绝，要求 keep_separate 并写明保护理由（或 human_queue）。

## human_queue 升级路径

1. 在 decisions.json 中判 `human_queue`，reason 写明：冲突字段、假设清单（数据错误？
   DOI 错配？不同工作？）、需要的核查动作。
2. 脚本施加阶段该组原样保留（两条记录都留在 merged_records.jsonl，无重定向）。
3. 阶段 4：未决清单逐条写入 result.json 的不确定性字段；若材料内（快照、辅助文件）
   可获得核查结论，回到阶段 3 重新裁决并重跑脚本。
4. 人工核查建议顺序：DOI 落地页 → 出版方页面 → 预印本版本历史 → 作者主页/机构库。
   本 skill 不联网核查；核查结论须以材料形式进入 records.jsonl 的 note 字段后方可改判。

## 决策矩阵速查

| 证据情形 | merge | keep_separate | human_queue |
|---|---|---|---|
| 同 DOI + 坐标一致（M1） | ✅ | ✅（过度保守但合法） | ✅ |
| 同 DOI + 坐标冲突（M2） | ❌ 拒绝 | ✅ | ✅ 推荐 |
| strong 预印本-正式版（M4） | ✅ canonical 须为正式版 | ✅ | ✅ |
| moderate（题名同+佐证≥2 / S5+容器同） | ✅ 须逐条列佐证 | ✅ | ✅ |
| weak 仅题名相似（M3） | ❌ 拒绝 | ✅ 推荐 | ✅ |
| S5 且容器/题名显著不同（M5） | ❌ 拒绝 | ✅ 推荐 | ✅ |
