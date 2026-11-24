# 结构齐备判据（structure_rubric）

本判据用于 doc_map.py 生成的角色矩阵与结构树之上做结构判定。结构类判定是客观机械判定
（标题在/不在），可直接 confirmed，无需 candidate 缓冲；但"层级合理性"与"角色歧义"
需要人工核对。

## 1. 标准角色齐备性（IMRaD + 首尾）

| 角色 | 可接受标题（中/英，含编号前缀） | 缺失严重度 |
|---|---|---|
| abstract | Abstract / 摘要 | major |
| introduction | Introduction / 引言 / 前言 / 研究背景 | major |
| methods | Methods / Materials and Methods / 方法 / 材料与方法 / 研究设计 / 对象与方法 | major |
| results | Results / 结果 | major |
| discussion | Discussion / 讨论 | major |
| conclusion | Conclusion(s) / 结论 / 总结 / 小结 | major（结论缺位时，讨论兼结论需在 uncertainty 说明） |
| references | References / 参考文献 | major |

- present：恰好一个标题命中该角色。
- ambiguous：多个标题命中同一角色 → minor + pending_review，需人工判断是否误分段
  （如"讨论"与"讨论与展望"并存通常是后者吞并前者，不算问题）。
- absent：零命中 → major + confirmed。

## 2. 什么算"结构看着完整但关键部分缺位"

以下情形标题齐全仍要报结构问题（Agent 在 doc_map 对齐表上人工判）：

1. **摘要↔结论要素断裂**：结论句在摘要中找不到任何对应要素（对齐表重叠度 < 0.2），
   说明摘要未承载结论，或结论越出了摘要声明的范围。
2. **引言问题↔结论回答断裂**：引言以问句明确提出研究问题，结论节无任何句子回应
   （配对表"疑似未回应"且人工确认无同义改写）→ 答非所问 major。
3. **空壳小节**：标题存在但正文 ≤ 1 句或只有占位语（"结果见表 1"而无任何数据），
   视同缺位，报 major，引用该小节全文作证。
4. **方法-结果错位**：方法节承诺的分析在结果节无任何对应产出（在论证链登记表
   key_methods→core_results 链边上标 inconsistent）。

## 3. 层级合理性

- 编号层级应单调（1 → 1.1 → 1.1.1，不允许 1 直接跳 1.1.1 而无 1.1）。
- 同级标题粒度应相近（"2. 方法"下不应一个子节 800 字、另一个只有标题）。
- markdown # 层级与编号层级混用时，以内容从属关系为准，不按字面 level 判错；
  拿不准一律 pending_review 并在 uncertainty 说明。
- 无标题纯文本稿件：role_matrix 全部 absent，在 uncertainty 标注
  "无法解析标题层级，结构分面 unable_to_check"，不得凭空判定结构完整。

## 4. 防误报

- 某些期刊明确合并"结果与讨论"（"Results and Discussion"合并标题命中两个角色）：
  两者都记 present，标题注明合并，不算缺位。
- "结论"并入讨论末节（讨论最后一个子标题为"结论"）：conclusion 记 present。
- 摘要若以"目的/方法/结果/结论"四段式结构式摘要出现且无"摘要"二字标题，
  命中"目的："起首段落即记 abstract present，并在 uncertainty 说明判定依据。
