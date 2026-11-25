# Intake Summary — synthetic-intake-003

- PDF: `/Users/liuhengshen/Desktop/bhr_product/ra01-5dir/bundles/a-intake-forensics/skill/examples/minimal/inputs/broken_tail.pdf`
- 文件大小: 1786 字节；PDF 版本: 1.4；线性化: False；加密: False
- 取证状态: partial；探测状态: partial（引擎: stdlib_count）
- 页数: forensics=1 / probe=1

## 每页判定

| 页 | 分类 | 非空白字符 | 乱码 | 文本字节(标准库) | 图像数 | 字体 |
|---|---|---|---|---|---|---|
| 1 | text | 864 | None | 864 | 0 | Helvetica(无ToUnicode) |

## 路由结论

- **strategy: direct_text**
- ocr_pages: []
- 下一步: 下游可直接做文本解析（阅读顺序/表格/章节等，超出本 Skill 范围）。

## 风险与问题

- truncated_input: 文件疑似截尾，以下路由仅覆盖已恢复部分
- [forensics] truncated: 文件尾缺少完整 startxref/%%EOF，疑似截尾或写入中断
- [forensics] page_order_fallback: kids walk failed, pages listed in object-number order
- [forensics] crosscheck_diff: page_count: stdlib=1 pymupdf=0
- [probe] pymupdf: pymupdf_zero_pages: 打开成功但未重建出任何页（典型于截尾/坏 xref）
- [probe] pdftotext: pdftotext_exit_1: Syntax Error: Couldn't find trailer dictionary / Syntax Error: Couldn't find trailer dictionary / Syntax Error: Couldn't read xref table
- [probe] stdlib_count: counts_are_bytes_not_unicode_chars
