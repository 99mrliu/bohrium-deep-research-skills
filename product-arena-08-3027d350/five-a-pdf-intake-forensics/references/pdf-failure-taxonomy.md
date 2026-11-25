# PDF 失败模式分类学：字节级识别特征与处置

供 `pdf_forensics.py` / `textlayer_probe.py` 的判读参考。每类给出：字节级特征（可在十六进制编辑器或 `grep -a` 中直接验证）、成因、本 Skill 的处置。所有特征均为明文 token（未加密的 PDF 中对象声明部分不压缩）。

## 1. 加密 PDF

- **字节级特征**：trailer 或文档任意处出现 `/Encrypt`（通常形如 `/Encrypt 12 0 R`），指向加密字典，内含 `/Filter /Standard`、`/V`、`/R`、`/O`、`/U`。加密后内容流与字符串均为密文，正则扫描得到的"Tj/TJ 文本"是噪声。
- **识别**：`pdf_forensics.py` 全文搜索 `/Encrypt\b`，命中即 `encrypted=true`。
- **处置**：strategy=handoff（reason=encrypted_pdf）。不尝试解密、不硬解析；页数、字体等结构化字段即使扫到也不可信，一律在 uncertainty 声明。用户须先提供解密版（如 `qpdf --decrypt`，但评测环境禁止安装，故交人工）。

## 2. 无文字层扫描件

- **字节级特征**：页面对象的 `/Resources` 中含 `/XObject << /Im0 N 0 R >>`，被引对象含 `/Subtype /Image`（常伴 `/ColorSpace /DeviceGray|/DeviceRGB`、`/BitsPerComponent 1|8`、`/Filter /DCTDecode|/JBIG2Decode|/FlateDecode`）；内容流只有 `q ... cm /Im0 Do Q` 一类的图像绘制，没有任何 `Tj/TJ`。
- **识别**：forensics 每页 `text_showing_bytes=0` 且 `image_count≥1`；probe 分类 `none`（非空白字符 ≤ 10）。二者须同时对账：有图无文才判扫描页。
- **处置**：页入 `ocr_pages`；全部页如此 → strategy=full_ocr，交 OCR 后处理方向。本 Skill 不做 OCR。

## 3. 无 ToUnicode 的乱码字体

- **字节级特征**：字体对象含 `/Subtype /Type0` 或 `/TrueType` 但**缺失** `/ToUnicode`；或 `/Encoding` 为自定义 `/Differences` 私有映射。提取时字符码无法映射回 Unicode，表现为 U+FFFD（PyMuPDF）、`(cid:NN)` 字面串、或成段控制字符/高字节垃圾。
- **识别**：forensics 记录每字体 `has_tounicode=false`、`embedded`（`/FontDescriptor` 内有无 `/FontFile`/`/FontFile2`/`/FontFile3`）；probe 判 `garbled`：garbage_ratio = (U+FFFD + (cid:NN)命中 + 控制字符) / 非空白字符 > 0.05，或出现任意 `(cid:NN)`。注意：CJK 正文天然高字节占比高，**高字节占比只记录、不单独判罪**，须与 U+FFFD/(cid:NN)/控制字符联合判定。
- **处置**：乱码页入 `ocr_pages`（OCR 可绕过损坏的编码层从字形恢复文本）；strategy 按乱码页占比定 mixed_ocr/full_ocr。禁止把乱码字符串当正文交付。

## 4. 截尾 / 坏 xref

- **字节级特征**：文件尾 1024 字节窗口内无 `%%EOF`；或 `startxref` 后的偏移越界/不指向 `xref` 关键字或 xref 流对象；或最后一个对象缺 `endobj`。典型成因：下载中断、写入崩溃、按字节裁剪。
- **识别**：`check_xref()` 四项——`startxref_found`、`startxref_points_to_xref`、`trailer_eof_in_tail`、`truncated`。此时常规解析器（含 PyMuPDF/pdftotext）常只能部分重建甚至 0 页。
- **处置**：forensics 回退为按对象号顺序的页面扫描（页序不保证，issue 记 `page_order_fallback`）；probe 引擎链降级到 `stdlib_count` 兜底；strategy 按可恢复页给出但 status=partial，`uncertainty` 明确"仅覆盖已恢复部分"；0 页可恢复 → handoff（structure_unrecoverable）。不伪造缺失页。

## 5. 增量更新（incremental update）

- **字节级特征**：文件中出现**多个** `%%EOF` 与多个 `startxref`；trailer 含 `/Prev <offset>` 指向上一个 xref 段；同号对象出现多次（后出现的修订版生效）。
- **识别**：`eof_marker_count > 1` 或 `/Prev` 命中 → `incremental_update=true`。
- **处置**：正则扫描取同号对象**首次**出现，可能是旧修订；记录 issue 提示。需要精确修订语义时依赖 PyMuPDF crosscheck 的页数/字符数对账，差异写入 `crosscheck.diffs`。不静默覆盖。

## 6. 对象流（/ObjStm）与 xref 流压缩

- **字节级特征**：存在 `/Type /ObjStm` 对象（内部 `/N` 个压缩对象、`/First` 给出偏移表，整体常 `/Filter /FlateDecode`）；xref 不是 `xref` 关键字表而是 `/Type /XRef` 流对象。PDF 1.5+ 常见，线性化文件（头部 `/Linearized`）几乎必用。
- **识别**：`objstm_count`、`xref_stream`、`linearized` 三个字段。对象流内的对象**不在** `N 0 obj` 明文扫描范围内，`object_count` 系统性偏低。
- **处置**：记录 issue `object_streams: ... 计数可能偏低`；结构判断以明文可见部分为准，页数与文本以 PyMuPDF crosscheck 兜底；两者差异写入 `crosscheck.diffs` 并令 status=partial。本 Skill 不解包对象流（保持纯标准库、取证只读）。

## 处置矩阵速查

| 模式 | forensics status | strategy | result.json status |
|---|---|---|---|
| 加密 | partial | handoff | partial |
| 非 PDF | failed | handoff | failed |
| 扫描件 | ok | full_ocr / mixed_ocr | success |
| 乱码字体 | ok | mixed_ocr / full_ocr | success |
| 截尾（有部分可恢复） | partial | 按可恢复页 | partial |
| 截尾（0 页可恢复） | partial | handoff | partial |
| 增量更新 | ok + issue | 按页分类 | success（uncertainty 记录） |
| 对象流 | ok/partial + issue | 按页分类 + crosscheck | success/partial |
