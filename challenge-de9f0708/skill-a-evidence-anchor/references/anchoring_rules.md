# 原文锚定规则（anchoring rules）

本规则表是 skill-a-evidence-anchor 的判定纪律：每条 finding 的 `location` 必须能被
`scripts/quote_bind.py` 机械复验。Agent 手写 location 时逐条遵守以下规则。

## 1. 页码约定
- 页码一律以 **PDF 物理页** 为准（即 `pdftotext -layout` 输出的第 N 个 `\f` 分页，
  等于 `pages.json` 里的 `page_no`），**不使用论文印刷页码**（正文页眉的 "245" 之类）。
- 纯文本材料无 `\f` 时全文为第 1 页。
- 拿不准页码时：先在 `pages.json` 里用文本搜索定位，再填 page；禁止凭印象填页码。

## 2. quote 必须逐字
- `quote` 必须从抽取文本中**复制粘贴**，逐字（含原始大小写、标点、数字），不得改写、
  不得"润色"、不得省略中间词、不得把两行内容凭记忆拼接。
- 允许跨行摘录：quote 含换行时与原样一致可命中 `exact`；若把换行写成空格，
  会命中 `normalized`（仍算通过，但说明你没有逐字复制——优先做到 exact）。
- 长度建议 8–30 词：过短（如 "n = 102" 单独出现多次）定位力弱，应带上下文使
  `found_on_pages` 唯一；过长容易因换行/连字符断词失配。
- 禁止编造 quote：哪怕 finding 本身成立，quote 对不上原文就必须降级（见第 5 节）。

## 3. 跨页 quote
- 一句话被分页符切断时，允许 quote 跨页：`page` 填**起始页**，
  quote_bind 会自动用"起始页 + 下一页"拼接文本兜底匹配，命中记
  `cross_page_exact` / `cross_page_normalized`，仍算 verified。
- 跨两页以上的长摘录不允许；拆成两条 finding 或缩短 quote。

## 4. absence 类 finding（"全文缺失 X 声明"）
- 适用于伦理声明缺失、数据可用性声明缺失等"找不到原文"的否定式发现。
- `location.quote` 留空，`page` 填 null，`section` 填 "全文"；
  quote_bind 记 `match_level=skipped_absence_claim`，**不自动降级**。
- 纪律：absence finding 必须由 Agent 在 pages.json 全文上做关键词检索
  （如 ethic / consent / IRB / 伦理 / 知情同意）并人工通读确认后才能标"确认"；
  只扫了一遍关键词就下结论的，标"待复核"并写明检索词。

## 5. 找不到原文时的降级纪律
- `match_level=none`（声称页与跨页拼接都匹配不上）时，quote_bind **自动**把
  `verdict_status` 改为 `待复核` 并在 `verdict_reasons` 追加"锚定核验未通过"。
- Agent 看到降级后的两条正路：
  1. 用 `anchor.found_on_pages` 找到 quote 实际所在页，修正 location 后**重跑**
     quote_bind（修正后的 quote 仍须逐字）；
  2. 若 quote 是凭印象写的、原文根本没有这句话——**删除该 finding 或重写 quote**，
     并把"锚定失败"保留在 change_log 中，不得悄悄抹掉。
- 禁止绕过：不得关闭核验、不得手工把 `待复核` 改回 `确认` 而不修 quote、
  不得为凑匹配而反过来篡改 pages.json。
- `found_on_pages` 非空但 `match_level=none` 几乎总是"页码填错"，优先修 page。

## 6. 文件字段
- `location.file` 必须与 `pages.json.source_file` 一致（按 basename 比较）；
  不一致时 quote_bind 会标注 `file_mismatch` 提示人工确认。多材料案例逐文件各跑
  一次 extract_text，各生成一份 pages.json，再分别绑定该文件的 findings。
