# 审计判定规则（lib-forensics references）

## 真实类型识别（魔数优先于扩展名）

| 文件头 | 判定 |
|-|-|
| `%PDF` | pdf |
| `PK\x03\x04` | zip 容器 → 再看内部目录：`word/`→docx、`xl/`→xlsx、`ppt/`→pptx，否则 zip |
| `\x89PNG` / `\xFF\xD8\xFF` / `GIF8` | png / jpeg / gif |
| `\xD0\xCF\x11\xE0` | OLE 复合文档（旧版 doc/xls/ppt） |
| 前 4096 字节可 UTF-8 解码 | utf8-text |
| 其余 | binary-unknown → 状态 unrecognized |

扩展名与真实类型不一致 → `type_mismatch`，状态 suspect，不得作为证据引用。

## 副本与别名

- sha256 全等即同一文件。同组内排序键：`路径含别名标记（副本/备份/copy/backup/(1)）优先排后`，
  再按路径字典序；第一名 canonical=true，其余 status=duplicate。
- 文件名规范化（小写、去别名标记、去首尾装饰符）得到 norm_base，供上层做
  版本族归并时引用；本技能不臆断版本先后，只提供证据。

## 状态机

verified（默认）→ suspect（类型不符/无法识别）→ duplicate（精确副本）→
unreadable（权限/IO）→ encrypted（zip 加密位）。任何非 verified 文件：

1. 进入 recovery.jsonl（含 action、reason、recovery 三要素）；
2. 不参与作答证据；
3. 在 result.json 的 excluded 与 uncertainty 中可见。

## PDF 文本层探测

`pdftotext -l 2 file -`：有文字→has_text；空白→needs_ocr（本机有 tesseract
时可由 Agent 手动 OCR 并把结果落 /app/work/ocr/，注明来源）；工具缺失→
unavailable 并写入 uncertainty。绝不把无文本层扫描件当作可引用文本来源。
