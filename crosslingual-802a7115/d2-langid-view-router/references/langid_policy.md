# 语言识别与视图分类策略（langid & view policy）

## 语种判定

- **正文优先于标签**。`language` 字段只作对照；判据全部来自抽取的真实文本，
  每条判定保留各语种得分与 margin，人工可复核。
- 假名（ひらがな/カタカナ）≥5 → ja；汉字 ≥10 且无假名 → zh。
- 拉丁语系：NFKD 折叠后按停用词命中计分；变音字符画像每语种上限 +15
  （ã/õ/ç→pt、ñ/¿/¡→es、ä/ö/ü/ß→de、à/â/è/ê→fr）。
- 置信度 = 0.4 + 0.6 × (top−second)/(top+1)，封顶 0.99；<0.7 的记录必须人工复核。
- 文本 <20 字符或无拉丁 token → und，不计入任何语种覆盖，写入 uncertainty。

## work 聚类

- DOI 相同（大小写不敏感）→ 同 work。
- 规范化标题（去变音、小写、只留 [a-z0-9] token）token Jaccard ≥ 0.6 → 同 work。
  0.6 容忍译名标题的用词差异（如 "Piroptose em macrófagos" vs "Pyroptosis in
  macrophages" 共享 macrophages 等实义词时仍可能低于阈值——此时 DOI 是主键；
  无 DOI 且标题不似的记录不会被强并，宁可分成两个 work 也不误并）。

## 视图分类（按优先级，首个命中生效）

1. **duplicate**：同 work 内同语种、正文 5-gram Jaccard ≥ 0.9 → 完全/近重复副本，
   countable=no，保留双方归因。
2. **translation（显式）**：正文出现翻译标记（translated from / tradução de /
   versão em português / versión en español / Übersetzung 等），标记原文照抄为证据。
3. **abstract_only**：body < 1500 字符但有摘要（或文首出现 Abstract/Resumo/Resumen）。
   只能支持"该工作存在"级别的结论，不得当全文证据引用。
4. **translation（隐式）**：同 work 异语种、无显式标记——证据必须写明"依据聚类与语种差，
   无显式标记"，供人工复核。
5. **bilingual_or_undetermined**：work 内多语种而本记录语种为 und。
6. **original**：其余情况——该语种在 work 内最完整的正文。

## 路由与计数

- `query_languages` = work 内全部已判语种（去 und）：检索该 work 时应覆盖的语种集合；
  缺失语种的查询要在 result.json 的 coverage 中显式说明。
- 多视图 work：每 work 计一次；duplicate 视图 countable=no。
- abstract_only 视图计入"存在性"，不计入"全文可核查"。

## 边界与限制

- 启发式语种判定在混合语种摘要（如葡英双语摘要并排）上可能给出中间置信度——
  这正是保留得分的意义：置信度 <0.7 一律人工复核，不自动决断。
- 无 DOI、标题又不似的同文版本无法自动聚类，会在 parse/聚类层面保持分离；
  下游若发现重复 DOI 之外的同文证据，应手工合并并记录变更（change_records）。
