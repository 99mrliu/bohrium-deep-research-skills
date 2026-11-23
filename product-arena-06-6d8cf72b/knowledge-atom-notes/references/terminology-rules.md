# 术语归一化规则（knowledge-atom-notes）

`kb_lint.py` 与 `kb_index.py` 使用同一套归一化，保证“同词必同形”：

1. 大小写折叠（casefold）。
2. 希腊字母转名称：α→alpha、β→beta、μ→mu、σ→sigma、Δ→delta 等（双向书写都归到名称形）。
3. Unicode 减号 − 与连接号 – 统一为 ASCII `-`。
4. 空白与下划线折叠为单个空格；连字符两侧空白去除（"counting - bloom" → "counting-bloom"）。

## 缩写与别名

- 每条 atom 的 `aliases` 列出文中出现过的全部表面形式，包括全称与缩写对。
- 归一化后 `canonical` 相同的同类型条目会被 lint 标为 duplicate 候选；确认同义后，在 atoms.json 的 `merges` 中记录归并（保留一个 kept_id，其余 id 指向它）。
- 归一化后同词形但定义内容词集合不相交时标 conflict 候选；这是给人看的，不代表必然矛盾（可能是一词多义，需加限定词区分，如 `term: "drift (sensor aging)"`）。

## 禁止事项

- 不为了通过 lint 而改写原文定义措辞；quote 永远逐字。
- 不把 not_reported 当成“有但懒得找”：必须写明检索过的章节范围。
- 跨论文合并不在本 Skill 单篇流程内；多案例各自产出 atoms，比较由下游消费 index.jsonl 完成。
