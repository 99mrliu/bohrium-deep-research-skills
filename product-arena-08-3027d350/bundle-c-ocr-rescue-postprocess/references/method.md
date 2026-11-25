# 方法说明：混淆分类、门控理由与词典

## 1. 混淆分类学（taxonomy）

扫描版科学 PDF 的 OCR 错误高度模式化，本 Skill 覆盖七类（见
`ocr-confusions.tsv`，35 条规则）：

1. **char_in_word —— 词内字符混淆**：`0/O`、`1/l/I`、`5/S`、`2/z`、`$/@/|` 等。
   数字出现在纯字母词内几乎必错（`rec0gnize`），反向则几乎从不错，因此
   基线置信度 high——但仍要求词典证据（见 §2）。
2. **seq_in_word —— 序列混淆**：`rn↔m`、`vv↔w`、`cl↔d`、`iii→m`、`ri→n`、
   历史印刷的 long-s（`f→s`）。这类模式双向存在于真词中（barn、kernel 含
   真 `rn`），所以基线只有 medium/low，必须词典门控。
3. **ligature_insert —— 连字丢失**：`fi/fl/ff/ffi` 连字在某些字体的 OCR 中
   整体脱落，留下截断词（`nished` ← finished）。对非词典词尝试在每个位置
   补回连字，**唯一**词典命中才给 high，多命中降级 low（ambiguous）。
4. **space_merge —— 伪分词**：一个词被空格劈成两段（`diff raction` ←
   diffraction）。合并结果在词典中且至少一段非词典词时才候选。
5. **greek_latin —— 希腊字母拉丁化**：`α→a`、`β→b/B`、`γ→g/y`。只在物理
   后缀语境（`-particles/-decay/-rays/-radiation/-emission`）触发；
   `B` 因同时是硼符号和磁场记号只给 medium。
6. **unreadable —— 符号乱码**：`#7@z~` 这类符号混杂串没有任何词典解释，
   高置信地标记为 `[unreadable]`——标记动作本身不是猜测。
7. **standalone_confusable —— 孤立混淆字符**：孤立的 `l/I/O` 处于数字或
   单位旁（`l mV`）时，可能是 `1/0`，也可能是升（litre）或正常记号。
   **真正歧义**，永远 low，永远进 review_list 由人定夺。

## 2. 门控理由：precision over recall

一处错误的“纠正”会把正确文本改错、并销毁证据；而一个不修改的诚实标记
只是把判断交还给人。因此：

- **词典即证据**：除希腊字母与 unreadable 外，候选成立的充要条件是
  “原词元不在词典 ∧ 建议在词典中”。这一条自动保护：
  - 真 `rn` 词（barn、kernel、internal）——原词在词典，不产生候选；
  - 化学式（C12、Fe2O3）——大写开头+数字守卫直接跳过 char_in_word；
  - 已正确的文本——在词典中，永不改动。
- **置信分级**：high 默认应用；medium 必须显式 `--aggressive`（或
  `--threshold medium`）；low **永不**应用，原文原样保留并记入
  review_list。同一 span 多重词典命中 → 自动降级 low。
- **全量留痕**：每个已应用编辑写入 change_log.jsonl（page/line/col/
  before/after/rule/confidence）；每个未应用候选写入 review_list.json
  并给出机器可读原因（below threshold / plausibility gate / span
  mismatch / overlap）。
- **绝不猜测**：垃圾串只标记 `[unreadable]`，不保留原串于正文（保留在
  change_log 的 before 字段），不臆造内容。退化越重，标记越多——这是
  特性而非失败。

## 3. 词典的编制与局限

`lexicon-en.txt`（约 420 词）手工编制，三部分：

1. 常见英语功能词与通用词（the/was/about/...）；
2. 通用科学词汇（measurement/spectrum/sample/...）；
3. 材料/物理/化学领域词（spectroscopy, catalyst, diffraction, annealing,
   photon, lattice, plasmon, synchrotron, ...）加常用单位（nm, mV, keV...）。

局限（诚实声明）：

- 覆盖面按“常见科学英语”编制；高度专业术语（如特定矿物名、罕见反应名）
  不在其中时，其正确文本会被 QC 计为 suspicious（误报方向：偏保守，只多
  报不少改）。词典是证据而非禁令：**不在词典中的词永远不会被改掉**。
- 单语种：仅英文。CJK 混淆（形似汉字、全半角、注音符号）需要完全不同
  的词表与规则集；检测到中日韩文本时应只标记不纠正。
- 词典不区分词性与搭配，无法发现“语法错误但词都合法”的 OCR 错误
  （这类错误不在本 Skill 范围）。

## 4. 可疑词元率（QC 指标）定义

满足任一即 suspicious：(a) 词内同时含字母与数字；(b) 含垃圾符号集中的
字符；(c) 孤立的 `l/I/O`；(d) 长度≥3 的纯 ASCII 字母词不在词典。
该定义偏向“宁可多报”，配合 precision-first 门控：QC 负责暴露，纠错
负责克制。`[unreadable]` 标记本身（方括号被分词器剥离、unreadable 在
词典中）不会被计为 suspicious。
