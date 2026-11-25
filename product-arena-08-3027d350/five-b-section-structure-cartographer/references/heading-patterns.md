# 标题模式库与定级规则（section-structure-cartographer）

本文件是 `scripts/build_hierarchy.py` 与 `scripts/split_references.py`、
`scripts/audit_structure.py` 中全部阈值与判据的文档化版本。
**代码与本文件必须保持一致**；改动任一侧时同步另一侧。

## 1. 编号体系模式

| 模式 | 正则 | 定级 |
|---|---|---|
| 十进制章节 `2`、`2.1`、`2.1.3`（可带 `.` / `)`） | `^(\d+(?:\.\d+){0,3})[.)]?\s+(\S.*)$` | 深度 = 点分段数（`2`→L1，`2.1`→L2） |
| Appendix / 附录（可带字母/数字后缀） | `^(appendix|附录)\b\s*([A-Z0-9.:-]*)`（忽略大小写） | L1，kind=appendix |
| 关键词短行（≤60 字符） | `^(abstract|摘要)$`、`^(introduction|引言)\b`、`^(references|bibliography|参考文献)$`、`^(acknowledg(e)?ments?|致谢)\b` | L1，kind=对应语义 |

编号行的两条排除规则（防误检）：
1. References 标题行之后的数字开头行一律视为参考文献条目，不作标题；
2. 编号行长度 > 120 字符，或同时含 `(19|20)\d{2}` 年份与逗号（疑似文献条目/列表），
   降级为 `heading_candidates`，不定级。

## 2. 字号秩定级规则（仅 mode=styled 可用）

- 正文基线：`body_median` = 所有长度 ≥ 30 字符行的 `max_size` 中位数。
- 无编号标题候选：`max_size ≥ 1.15 × body_median` 且长度 ≤ 90 字符，
  且（粗体 或 `max_size ≥ 1.40 × body_median`）。
  - 粗体判定：字体名含 `Bold`/`Black`，或 pymupdf span flags 第 4 位（16）。
- 定级：候选按字号降序去重得秩 `[s1 > s2 > ...]`，rank 1 → L1，rank 2 → L2，依此。
- 文档题名：`max_size ≥ 1.40 × body_median` 的 front_matter 行，**不作章节标题**。
- front_matter 保护：首个关键词/编号标题之前的区域按定义为 front_matter，
  其中的大字号行一律不进层级树（防题名污染树）。

## 3. 全大写短行候选

- 判据：3 ≤ 长度 ≤ 60、字母字符 ≥ 2、全部字母大写。
- 处置：只进 `heading_candidates`，不独立定级（证据不足，诚实降级）。

## 4. 结构区间切分锚点

| 区间 | 起点 | 终点 |
|---|---|---|
| front_matter | 文档首行 | body 起点前一行 |
| body | 编号 `1` 或 Introduction 标题（缺则首个编号标题） | References/Appendix 标题前一行（缺则文末） |
| references | References/Bibliography 标题行 | 其后首个 L1 特殊标题（Acknowledgments/Appendix）前一行，缺则文末 |
| appendix | Appendix 标题行 | 文末或其后特殊标题前一行 |
| acknowledgments | Acknowledgments 标题行（若存在） | 同上 |

节点行区间：从标题行到下一个 level ≤ 自身标题的前一行；每个节点/区间带
`(page, y0)` 锚点，可在原文复核。

## 5. 参考文献条目起始模式（按优先级）

1. `[n]`：`^\[(\d{1,3})\]\s*`
2. `n.` / `n)`：`^(\d{1,3})[.)]\s+\S`
3. 作者行：`^[A-Z][A-Za-z'’\- .]+,.*(19|20)\d{2}`，且上一条目末行以句点收尾
   （防把续行误判为新条目）

其余行并入上一条目 `raw_text`（以单空格连接）；首条起始模式之前的行进
`leftovers`，**任何字符不丢弃**。对账式：
`Σlen(raw_text) + len(leftovers) + 标题行字符 + join_spaces_added == 区间总字符`。

- `first_author_guess`：去编号前缀后第一个逗号前的文本。
- `year_guess`：首个 `(19|20)\d{2}` 匹配。

## 6. 图/表题注与引用模式（audit）

- 题注行：`^\s*(fig(?:ure)?s?|tables?)\.?\s*(\d+)\s*[:.]`（忽略大小写），
  覆盖 `Figure 1:`、`Fig. 2.`、`Table 3:`。
- 正文引用：`\b(fig(?:ure)?s?|tables?)\.?\s+(\d+)\b`；题注行先剥去自身题注
  前缀再搜引用，避免自引误报。
- 双向差异：`cited_not_captioned`（引用了不存在）与
  `captioned_not_cited`（存在但未被引用）都列出。

## 7. 编号一致性检查（audit）

- 跳号：同级兄弟序列中 `b > a + 1`，列出缺失编号。
- 重复：同一编号出现两次。
- 逆序：同级序列非单调递增。
- 层级断裂：存在 `a.b.c` 但任一前缀（`a`、`a.b`）缺失。

## 8. 引擎链与降级

| 引擎 | mode | 提供 | 缺失 |
|---|---|---|---|
| pymupdf（可选 import） | styled | text/size/font/flags/bbox/page | — |
| pdftotext -bbox（可选） | geometry | 词级坐标，脚本自聚合行（y 容差 max(2pt, 0.3×行高)） | 字号、粗体 |
| pdftotext -layout（可选） | text | 页/行序、缩进 | 坐标（y0=行序代替并标注）、字号、粗体 |

geometry/text 模式下字号秩规则（第 2 节）不可用，仅靠编号与关键词；
报告与 result.json 中如实写明 engine、mode 与降级原因。
三者皆不可用 → 退出码 3，报告 status=failed，不静默。
