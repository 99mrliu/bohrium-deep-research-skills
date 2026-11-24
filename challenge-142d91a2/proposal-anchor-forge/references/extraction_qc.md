# 抽取 QC 判据（manifest.json 解读）

anchor_extract.py 的 manifest 是「材料能不能信」的第一道判据。以下阈值为本 bundle
内置默认值，判据偏保守：宁可标记存疑，也不放过坏材料。

## 1. 乱码率（garble_ratio / garble_suspect）

- 定义：非空白字符中，可疑字符占比。可疑字符 = U+FFFD 替换符、除 TAB 外的 C0
  控制符、Unicode 私用区（U+E000–F8FF、增补私用平面）。
- 阈值：`garble_ratio > 0.01` 即 `garble_suspect=true`。
- 处置：受影响材料的段落仍可锚定，但引用它的论断在台账中应降级为 inference 或
  在 uncertainty 中注明「来源疑似乱码，引文可信度存疑」；整段乱码（ratio > 0.3）
  建议直接弃用该材料。

## 2. 截断迹象（truncation_suspect）

- 定义：段落数 > 3 且文末 160 字符内没有任何收束标记（句读标点、右括号、
  「参考文献」/references 字样）。
- 含义：材料可能被截断（下载不全、pdftotext 抽页失败）。末尾段落的内容可能
  是半句，不宜作为指标阈值、结论性引用的来源。
- 处置：涉及「结论边界/指标依据」的论断改用 partial 措辞，并在 uncertainty 点名。

## 3. 不可读文件（unreadable）

- 触发：UTF-8 解码失败、pdftotext 未安装/超时/非零退出码、PDF 输出为空
  （扫描件或纯图片）。
- 处置：**不得猜测内容**。逐条写入 result.json 的 uncertainty；若 unreadable
  覆盖全部材料，result.json 置 `failed`，不产出任何论断。

## 4. 空文件（empty_files）

- 触发：文件 0 字节，或全文仅含空白字符。
- 处置：不计入材料总数，不产出锚点；在 uncertainty 中说明「该文件无可用内容」。

## 5. 抽样复读（人工/模型自检）

抽取完成后，从每个材料随机抽 1–2 个锚点，用 `char_start/char_end` 回切原文复读，
确认无乱码、无段间错位、无页眉页脚粘连，再进入起草。重复运行同一输入必须得到
同一锚点集；任何手工改动抽取文本都必须记入 result.json 的 `change_records`。
