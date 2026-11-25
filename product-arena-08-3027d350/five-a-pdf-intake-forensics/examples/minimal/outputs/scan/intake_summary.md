# Intake Summary — synthetic-intake-002

- PDF: `/Users/liuhengshen/Desktop/bhr_product/ra01-5dir/bundles/a-intake-forensics/skill/examples/minimal/inputs/scan_like.pdf`
- 文件大小: 9058 字节；PDF 版本: 1.4；线性化: False；加密: False
- 取证状态: ok；探测状态: ok（引擎: pymupdf）
- 页数: forensics=1 / probe=1
- 元数据: Producer=pdf-intake-forensics make_samples.py; Creator=stdlib synthetic generator; CreationDate=D:20261125090000+08'00'

## 每页判定

| 页 | 分类 | 非空白字符 | 乱码 | 文本字节(标准库) | 图像数 | 字体 |
|---|---|---|---|---|---|---|
| 1 | none | 0 | False | 0 | 1 | — |

## 路由结论

- **strategy: full_ocr**
- ocr_pages: [1]
- 下一步: 全文无可用文字层，整体走 OCR 管线（交 d-scan-ocr-trust 方向）。
