# 门禁清单与输出契约

## 12 条门禁（requirements.json 由 survey.py 生成）

| ID | 类别 | 判定方式 |
|-|-|-|
| G01-deck-editable | 产物 | python-pptx 重新打开成功 |
| G02-slide-count | 结构 | 页数 == 工单 total_slides |
| G03-roles | 结构 | required_roles 全覆盖 |
| G04-notes | 内容 | 每页 notes 非空 |
| G05-source-line | 内容 | 每页有「来源：…」行 |
| G06-anchor-numbers | 证据 | 每个数字命中锚定页文本 |
| G07-figure-real | 证据 | 插图均来自 PDF 真实裁剪 |
| G08-template-inherit | 模板 | slideMasters/slideLayouts/theme 字节级一致 + 无 run 级字体名 |
| G09-export-pdf | 产物 | PDF 存在且页数一致 |
| G10-content-map | 产物 | result.json 每页映射齐全 |
| G11-result-fields | 产物 | 七根字段齐全（由 result.py 保证） |
| G12-density | 内容 | ≤6 条/页，≤60 中文字符/条 |

status 语义：pass=过；fail=硬失败（必须修）；warn=降级提示（进 exceptions）；skip=输入缺失无法判定（进 exceptions）。

## result.json 根字段（契约原文）

`case_id, status, editable_source, export_artifact, content_map, compliance_checks, exceptions`

- status：completed（全过）/ partial（有 fail 或 PDF 未出）/ failed（无 pptx）。
- editable_source：pptx 路径、页数、模式、模板名。
- export_artifact：pdf 路径、预览目录、页数、转换器。
- content_map：每页 {slide, role, title, anchors, figure, notes_chars}。
- compliance_checks：门禁 ID → {status, evidence, desc}。
- exceptions：假设、警告、硬失败逐条列出——宁多勿少，诚实是评分点。

补充字段 sources / uncertainty / change_log 用于复核：记录实际使用的论文、模板、起始稿文件名，以及每一步的产物。
