# PDF 文本层提取说明（pdf_text_layer.md）

本文件说明 `scripts/facsimile_register.py` 对 PDF 文本层的两级提取策略及其取舍。

## 1. 优先路径：poppler `pdftotext`

- 触发条件：`pdftotext` 在 PATH 上（`shutil.which("pdftotext")`），且未指定 `--no-poppler`。
- 调用形式：`pdftotext -layout <file> -`，按换页符 `\f` 切分逐页文本。
- 优点：对真实 USPTO 传真版 PDF 的字体编码、排版顺序、FlateDecode/对象流等兼容最好。
- 清单中记 `extraction.method = "poppler-pdftotext"`。

## 2. 回退路径：纯标准库提取器

- 触发条件：无 `pdftotext`，或显式 `--no-poppler`。
- 解析方式（仅用 `re`/`zlib` 等标准库）：
  1. 以正则切出全部间接对象 `N 0 obj ... endobj`；
  2. 从 `/Type /Pages` 的 `/Kids` 数组取得页面顺序（缺失时退化为全部 `/Type /Page` 对象）；
  3. 对每页的 `/Contents` 流：无 `/Filter` 视为未压缩；`/FlateDecode` 用 `zlib.decompress` 解压；其他过滤器直接报错降级；
  4. 解释内容流：收集 `Tj` 字符串与 `TJ` 数组中的字符串（字距调整数忽略），`T*`/`Td`/`TD`/`Tm`/`'`/`"`/`ET` 处插入换行；字面串支持 `\(...\)` 转义与八进制转义，`<...>` 十六进制串亦支持。
- 清单中记 `extraction.method = "stdlib-fallback"`。

## 3. 降级而非猜测

以下情形一律标记 `extraction_degraded: true` 并写明 `reason`，**不产出臆测文本**：

- 文件含 `/Encrypt`（加密 PDF）；
- 找不到间接对象或页对象（结构损坏或非 PDF）；
- 内容流使用非 FlateDecode 过滤器；
- 提取结果为零长度文本层（典型为扫描影像件；OCR 超出本技能范围，须在结果 `uncertainty` 中声明）。

## 4. 已知局限

- 不解析对象流（ObjStm）与交叉引用流（XRefStm）中的压缩对象；
- 不做 CID/ToUnicode 映射，非 Latin-1 可映射字形可能失真；
- 逐页字符数（`pages[].char_count`）用于粗检文本层是否存在，不代表版面质量。

## 5. 实务建议

评测环境若提供 poppler，始终以 poppler 结果为准；标准库回退的价值在于
无外部依赖环境下仍能对"文本型"（非扫描）PDF 取证。两种路径产生的
`extracted/<sha256>.pages.json` 结构完全一致，下游 `page_anchor.py` 与
`facsimile_discrepancy.py` 不感知差异。
