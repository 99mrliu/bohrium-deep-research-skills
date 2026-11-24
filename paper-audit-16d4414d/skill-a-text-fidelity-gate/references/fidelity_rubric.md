# 保真判定细则（fidelity rubric）

本文件解释 fidelity.py 每种告警的含义、典型误报边界与标准处置。原则：**宁可降级也不冒进**——任何无法确认忠实的部分，进"未检查项"，不进审查结论。

## gate 三档

| gate | 含义 | 对审查的约束 |
|-|-|-|
| pass | 未发现保真问题 | 可正常全文审查；quote 仍须过 quotecheck |
| degraded | 有告警 | 告警涉及的部分列入未检查项或待复核；报告禁用"全文/所有章节"表述 |
| fail | 空文本等致命问题 | 不审查；result.json 标 `未检查/<原因>` 即交付 |

## 告警逐条

### empty_text（issue → fail）
抽取产出 0 字符。几乎必然是扫描版 PDF 无文本层，或文件损坏。
处置：标 `未检查/no_text_layer`。有 OCR 工具时可在报告中建议"需 OCR 后重审"，但不代替本次结论。

### encoding（warning）
文本含 U+FFFD 替换字符。少量（个位数）多见于特殊符号（希腊字母、上下标）丢失——相关句子引用时按渲染图目检核对；大量出现说明解码错误，应换编码重新 extract。

### no_abstract_heading / no_references_heading（warning，仅长文触发）
规范章节标题未检出。两种可能：(a) 文本在前端/末端被截断；(b) 标题非规范写法（如 "Summary"、"Summary and conclusions"）。
处置：先目检首末各 500 字符判断是 (a) 还是 (b)；(a) 进未检查项，(b) 仅记录，不影响审查范围。短文本（<4000 字符）不触发，避免对摘要级材料误报。

### abrupt_end（warning，truncation_suspected=true）
全文最后一个字符不是终止标点，文本疑似在句中被截断。
处置：最后完整句之后的所有内容不可作为审查依据；若截断发生在 References 之前，跨章节一致性检查范围要相应缩小并写入 uncertainty。

### fragmented_lines（warning）
>85% 非空行短于 45 字符。典型成因：双栏 PDF 抽取后行被切碎、OCR 断行。
处置：这只影响阅读体验，不影响逐字 quote（quote 取自切句后的台账）；但若同时有 column_interleave_suspect，必须先目检。

### column_interleave_suspect（warning）
大量行含两处以上宽空白，疑似左右栏内容同行拼接。
处置：对涉及页用 pdf-render-tool 渲染目检；确认串栏的段落，其句子 id 仍可定位，但"上下文"不可信（前后句可能来自另一栏），涉这些句子的跨段论证检查标待复核。

### very_short（warning）
全文 <1500 字符。提示输入可能只是摘要或节选。
处置：在 result.json 写明材料范围，审查结论只覆盖所给文本。

## 误报边界（本工具不会做的事）

- 不判断论文质量，只判断文本保真度；gate=pass 不代表论文没问题。
- 章节识别基于规范标题正则；非规范标题会导致 missing 误报，用目检仲裁，不改引擎。
- 切句对十进制小数安全（0.03 不会断句），但对 "Fig. 3" 类缩写可能多切；碎片句（<4 字符）自动丢弃，不影响定位。
- quotecheck 是逐字子串校验：引号内一个字符不符即失败。这是特性不是缺陷——评审核对的就是逐字。
