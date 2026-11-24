# 锚点规范（anchor protocol）

## 什么算好锚点

锚点 = 一个 Markdown 段落（空行分隔的连续非空行块）。每个锚点有四要素：
anchor_id（A001 起按文档顺序编号）、heading（章节路径）、paragraph_index
（章节内段序）、quote（逐字原文）。

好锚点的标准：

1. **唯一性**：quote 在全文恰好出现 1 次。落稿引擎按整段 quote 匹配，
   重复段落（如模板化的套话段）会导致 anchor_not_unique。选锚点前用
   `anchor_map.py --find "段中一句"` 查 global_occurrences 是否为 1。
2. **长度适中**：整段作 quote，通常 30–300 字。过短的段（如一句套话）容易
   不唯一；过长的段使 changes.json 臃肿，但不影响正确性。
3. **稳定性**：专有名词、数据、术语多的段落不易与他段撞车，是优质锚点。
4. **跨段禁忌**：一个锚点永远只是一段。不要试图跨越空行拼锚点；
   要改相邻两段，就用两个 edit（两个 change_id）分别落。

## 落稿语义

- 修改：整段替换，原段被 `<!-- CHG-xx begin: R#.# -->` / `<!-- CHG-xx end -->`
  包裹的新文本取代。
- 新增：新段插在锚点段之后（position=after，默认）或之前（before），
  锚点段本身不动。
- 删除：整段移除，只留成对标记，保留可追溯性。

同一锚点可被多个 edit 引用（如「修改本段」+「在本段后新增」），因为匹配
按当前稿件状态顺序进行；但若前序 edit 删除/替换了该段，后续引用同一锚点
的 edit 会 anchor_not_found —— 因此**先排新增、再排修改、最后删除**，
或对同段的修改与新增合并为一个 edit。

## 锚点漂移与重锚

以下情况说明锚点已漂移，需要重锚：

- 组织方更新了基线版本：旧 anchors.json 全部作废，重新跑 anchor_map；
- apply_report.json 出现 anchor_not_found：用
  `anchor_map.py --find "记忆中的片段"` 反查，确认是基线变了还是
  前序改动覆盖了该段；
- 任何情况下禁止绕过锚点直接编辑 revised-manuscript.md —— 手工改稿会让
  changes.json 与稿件失配，三方核验必然 FAIL。

## 多轮返修的锚点维护

1. 新一轮返修以「上一轮的修订稿去掉 CHG 标记后」或组织方给的新基线为准，
   重新编译锚点图；旧 anchor_id 不复用。
2. CHG 编号全局续编：上一轮用到 CHG-05，新一轮从 CHG-06 开始，保证
   回复信、changes.json、修订稿三处的编号在全流程内唯一。
3. 新一轮回复信引用新一轮的定位；如需回指旧改动，写明「第 N 轮 CHG-05」
   并在 uncertainty 中说明跨轮引用。
