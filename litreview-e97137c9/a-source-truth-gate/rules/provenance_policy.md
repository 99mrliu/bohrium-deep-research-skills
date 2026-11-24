# 来源信任分层与表述强度规则（provenance policy）

## 信任分层（由 scripts/source_forensics.py 判定，模型不得自行提升）

| 层级 | 条件 | 允许用途 |
|-|-|-|
| T1 | 代表篇（或独立篇）+ fulltext + 无撤稿标记 + 元数据不冲突 | 可支撑 established / suggestive / contested |
| T2 | abstract_only，或元数据冲突待核（metadata_mismatch） | strength ≤ suggestive |
| T3 | metadata_only（仅题录/URL）、failed（抽取失败）、撤稿/撤回标记、duplicate_of | 不进入证据池，只在筛选记录与 uncertainties 中说明 |

模型职责是**使用**层级，不是重新判定层级。认为脚本误判时，在 uncertainties 中说明理由，不得静默改写 source_manifest.json。

## 表述强度谓词（中文书面语）

| strength | 可用谓词 | 禁用谓词 |
|-|-|-|
| established（多篇 T1 一致且方法可比） | 表明、证实、显示 | 有望、暗示 |
| suggestive（单篇 T1 或 T2 来源） | 初步表明、提示、在……条件下观察到 | 证实、证明 |
| contested（文献间结论相反） | 存在分歧、另有研究报道相反结果 | 一致表明、公认 |
| unknown（无证据覆盖） | 现有材料无法确定 | 任何断言式谓词 |

## 摘录规范

- `verbatim_quote` 为 `pages/<doc_id>.jsonl` 对应页文本的逐字子串；仅允许归一化换行、断词连字符与多余空白，不得转述、翻译或凭记忆重写。
- 中英混排文献：摘录保持原文语言，在证据行加 `quote_lang` 字段。
- locator 格式 `p<页>.¶<段>`；段落号用于人工复核，门控按页校验。

## 冲突处理

同一主题内方向相反的论断并列两条 `contested` 证据行，各自注明对象/条件差异；不得取平均、不得只留正向。
