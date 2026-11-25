# 权利要求切分语法与边界情形（claim_grammar.md）

本文件说明 `claim_segment.py` 采用的确定性切分语法、已知边界情形与 OCR 合并边界的处理方式。所有规则均由正则与字符偏移实现，不含任何模型推断。

## 1. 权利要求单元的识别

- 起始行模式：行首（允许前导空格/制表符）出现可选前缀 `权利要求` / `Claim`（大小写不敏感），随后是 1–3 位十进制序号，再随后是分隔符 `.` `、` `．` `:` `：` 之一。
- **顺序约束**：识别到的序号必须自 1 起连续递增（1, 2, 3, …）。某行虽匹配模式但序号不等于"期望的下一项"时，该行被当作正文延续，**不**开启新的权利要求单元。该约束用于区分权利要求编号与正文中的编号子步骤（如 `1)`、`2.` 列举）。
- 权利要求单元范围：从起始行行首到下一项起始行行首（或文末），去除首尾空白。
- 权利要求 1 之前的非空材料（标题、说明行等）记入 `front_matter`，不参与切分。
- 若全文未识别到任何合法起始行：整篇文本原样保留于 `raw_regions`（reason=`no_claim_boundaries`），并置 `segmentation_degraded: true`；退出码仍为 0。

## 2. 独立 / 从属判定

- 命中以下任一模式即判为从属权利要求，并抽取被引用编号列表 `references`：
  - 英文：`claim N`、`claims N, M`、`claims N-M`、`claims N or M` 等（`claims?` + 编号列表）；
  - 英文：`any preceding claim` / `any one of the preceding claims`（此时 `references` 可为空，`any_preceding_reference=true`）；
  - 中文：`权利要求N`、`权利要求N至M`、`权利要求N、M或K` 等。
- 未命中任何引用模式者判为独立权利要求。
- 已知盲区：引用以其他语言（德/法/日/韩）书写、或被 OCR 噪声打断（如 `cl aim 1`）时可能漏判，此时该项被判为独立。漏判不改变任何原文，仅为标签不确定；下游比对应在 `uncertainty` 中说明。

## 3. 前序 / 过渡语 / 要素

- 过渡语分两层匹配，先在权利要求正文中搜索第一层（高置信）：
  `comprising`、`consisting of`、`consisting essentially of`、`characterized in/characterised in that`、`wherein the improvement comprises`、`其特征在于`、`其改进在于`；
  第一层无命中再搜索第二层：`containing`、`including`、`包含`、`包括`、`含有`。
  同层取最左出现位置；并列时取最长匹配。英文短语要求词边界（`\b`）。
- 前序 = 正文起点到过渡语起点（去首尾空白）；过渡语 = 命中短语的精确 span；要素体 = 过渡语之后到权利要求末尾。
- 要素切分边界：
  - 硬分隔：分号 `;` `；`（分号本身不进入任何要素的 quote）；
  - 软分隔：`wherein`（词边界）、`其中`、编号子步骤 `(a)` `(1)` `(iv)`、`1)` 等的**起点**（分隔标记保留在新要素内部）；
  - 切分后的片段去除首尾空白；纯标点碎片（如残留逗号）与连接词 `and`/`以及`/`和` 不构成要素；
  - 要素类别：`wherein_clause`（以 wherein/其中 开头）、`substep`（以编号子步骤标记开头）、`element`（其余）。
- 独立权利要求未找到过渡语：`status=no_transition`，整体文本保留于 `preamble.quote`，`segmentation_partial=true`，且顶层 `segmentation_degraded=true`。
- 从属权利要求无过渡语属常态：以引用部分（如 `The mounting bracket of claim 1`）为前序，其余按软/硬分隔切为要素，`status=ok_no_transition_dependent`，不视为降级。

## 4. 边界情形（已知限制）

1. 正文中的编号子步骤若恰好形如 `2.`、`3.` 且与期望序号连续，可能被误判为新权利要求起始。顺序约束降低了但不能完全消除该风险；遇此情形应人工核对 `num_claims`。
2. 一项权利要求内出现多个过渡语（如 `comprising` 出现在 wherein 从句中）时，只认最左（第一层优先）的一个，其余保留在要素文本内。
3. OCR 噪声导致的全角/半角混用、序号缺字（`l.` 代替 `1.`）会导致起始行漏识别，进而触发降级保留原文——这是有意设计：宁可降级，不可猜切。
4. 多权利要求合并在一行（无换行）时不被识别；本工具按行识别起始。

## 5. OCR 合并边界

- 已声明的边界行由正则识别，默认 `OCR[ -]?MERGE[ -]?BOUNDARY`（可用 `--boundary-regex` 覆盖）；匹配命中后扩展到整行并记录 span 与逐字 quote 于 `ocr_boundaries`。
- 任何权利要求 / 前序 / 过渡语 / 要素的 span 与边界行 span 相交时，附加 `crosses_ocr_boundary: true`；任一权利要求被标记时顶层 `contains_ocr_boundary=true` 并在 `notes` 中说明。
- 边界行**不从文本中删除**：所有偏移始终相对于原始文本，保证逐字性可机器复核（`quote == text[span[0]:span[1]]`）。
- 跨越边界的 span 属于"部分可信"区域：下游 `claim_align.py` 会因此把比对状态降为 `partial` 并在 `limits` 中写明具体权利要求编号与偏移。
