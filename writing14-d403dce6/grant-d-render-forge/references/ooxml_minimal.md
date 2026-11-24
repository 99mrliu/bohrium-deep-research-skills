# 最小合法 docx（OOXML）部件清单与常见损坏原因

docx 是一个 zip 包。md2docx.py 生成的最小结构：

```
[Content_Types].xml              必需。声明各部件的 ContentType
_rels/.rels                      必需。包级关系：指向 word/document.xml（officeDocument）
word/document.xml                必需。正文，根元素 w:document
word/styles.xml                  必需（本 bundle 约定）。样式定义
word/_rels/document.xml.rels     建议。document.xml → styles.xml 的 styles 关系
```

## 各部件要点

- `[Content_Types].xml`：须含 `.rels` 与 `.xml` 两个 Default，以及 `/word/document.xml`（main+xml）与 `/word/styles.xml`（styles+xml）两个 Override。缺 Override 时 Word 报"内容有问题"。
- `_rels/.rels`：Relationship 的 Type 须为 `.../relationships/officeDocument`，Target 为 `word/document.xml`。
- `word/document.xml`：根元素带命名空间 `xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"`；所有 `w:` 前缀标签依赖该命名空间；正文须以 `w:sectPr`（页面设置）收尾，置于 `w:body` 末尾。
- `word/styles.xml`：docDefaults 声明默认字体（本 bundle：西文 Times New Roman、中文 `w:eastAsia="SimSun"` 即宋体）；标题样式 Heading1/2/3 中文字体 SimHei（黑体）并带 `w:outlineLvl`，否则目录/导航窗格不识别。

## 常见损坏原因（排错索引）

| 症状 | 常见原因 |
| --- | --- |
| Word 提示"文件已损坏/无法打开" | zip 内缺必需部件；XML 未转义（正文含 `&` `<` `>` 直接写入）；XML 声明缺失或编码不符 |
| "内容有问题，可恢复" | 标签不配对；`w:t` 内含裸 `&`；表格缺 `w:tc` 内段落（`w:tc` 里必须至少一个 `w:p`） |
| 中文显示为方框/字体不对 | styles.xml 未声明 `w:eastAsia`；只设了 `w:ascii` 字体 |
| 样式不生效 | 缺 word/_rels/document.xml.rels 中的 styles 关系；`w:pStyle w:val` 与 styles.xml 的 `w:styleId` 不一致 |
| 标题不进导航/目录 | Heading 样式缺 `w:outlineLvl` |
| 文本首尾空格丢失 | `w:t` 未加 `xml:space="preserve"` |
| 复跑字节不一致 | zip 条目时间戳未固定（md2docx.py 固定为 1980-01-01） |

## 目检方法

```bash
python3 - <<'PY'
import zipfile
with zipfile.ZipFile("draft_v2.docx") as z:
    for i in z.infolist():
        print(i.filename, i.file_size)
PY
```

md2docx.py 写出后自动复读校验：缺必需部件或任一 XML 不可解析即退出码 1，不要相信退出码 0 之外的"成功"。
