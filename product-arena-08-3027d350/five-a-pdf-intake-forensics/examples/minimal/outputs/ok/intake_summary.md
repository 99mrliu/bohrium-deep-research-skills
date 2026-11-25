# Intake Summary — synthetic-intake-001

- PDF: `/Users/liuhengshen/Desktop/bhr_product/ra01-5dir/bundles/a-intake-forensics/skill/examples/minimal/inputs/ok_text.pdf`
- 文件大小: 2978 字节；PDF 版本: 1.4；线性化: False；加密: False
- 取证状态: ok；探测状态: ok（引擎: pymupdf）
- 页数: forensics=2 / probe=2
- 元数据: Producer=pdf-intake-forensics make_samples.py; Creator=stdlib synthetic generator; CreationDate=D:20261125090000+08'00'

## 每页判定

| 页 | 分类 | 非空白字符 | 乱码 | 文本字节(标准库) | 图像数 | 字体 |
|---|---|---|---|---|---|---|
| 1 | text | 708 | False | 864 | 0 | Helvetica(无ToUnicode) |
| 2 | text | 708 | False | 864 | 0 | Helvetica(无ToUnicode) |

## 路由结论

- **strategy: direct_text**
- ocr_pages: []
- 下一步: 下游可直接做文本解析（阅读顺序/表格/章节等，超出本 Skill 范围）。
