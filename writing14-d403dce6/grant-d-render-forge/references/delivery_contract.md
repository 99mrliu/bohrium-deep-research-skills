# 交付物清单合同（delivery contract）

基金申请书章节稿的交付不是对话框里的一段文字，而是一组**可编辑、可目检、可追溯**的文件。本合同规定交付物清单、命名约定与验收标准。

## 一、交付物清单与验收标准

| 交付物 | 命名约定 | 验收标准 |
| --- | --- | --- |
| Markdown 母稿 | `draft_v<N>.md`（N 从 1 起递增） | UTF-8 纯文本；章节结构对应案例体裁要求；可直接再编辑 |
| 可编辑 DOCX | `draft_v<N>.docx`（由 md2docx.py 从同名母稿生成） | zipfile 复读校验通过（含 [Content_Types].xml、_rels/.rels、word/document.xml、word/styles.xml）；Word/WPS/LibreOffice 可打开 |
| PDF 预览 | `draft_v<N>.pdf`（soffice 真实转换） | 文件非空；由 preview_status.json 记录生成工具与字节数 |
| PNG 页面预览 | `draft_v<N>-<页码>.png`（pdftoppm -png -r 110） | 每页一个非空 PNG；供不开 Office 时目检排版 |
| 修改记录 | `change_record.md`（version_diff.py 生成） | 含 unified diff、变更统计、按小节归组、人工确认项清单 |
| 结果装配 | `result.json`（assemble_result.py 生成，--validate 通过） | 含原始 case_id 与全部 output_contract 字段、诚实 status/reason/sources/uncertainty、deliverables 所列文件真实存在 |
| 预览状态 | `preview_status.json`（make_previews.py 生成） | 如实记录工具探测与产物状态；degraded 时写明缺哪个工具、哪个产物未生成 |

## 二、诚实降级规则

- soffice 或 pdftoppm 不可用：只写 preview_status.json 声明缺失，**绝不**用截图占位、空文件或改名文件伪造预览。
- result.json 中无法落实的合同字段：填【缺失：待补充】并列入 missing，status 不得报 success。
- 交付物未生成时不得列入 deliverables；列入即必须真实存在于输出目录。

## 三、案例格式要求映射

1. 运行时先读 `/input/case.json` 的 output_contract 与 `/input/task.md` 的格式要求，不硬编码字段。
2. 案例要求 docx：母稿定稿后用 `md2docx.py draft_v2.md draft_v2.docx` 生成并以其退出码验收；再 `make_previews.py draft_v2.docx --outdir <输出目录>` 出真实预览。
3. 案例要求"修改留痕/修改说明"：交付 `change_record.md` 并在 result.json 的相应合同字段中引用它。
4. 案例未要求 Office 格式：仍建议交付 docx 作为可编辑稿，并在 deliverables 中注明母稿为权威版本。
5. 每次改稿：先落新版母稿（draft_v3.md…），再重跑 diff/docx/previews，最后 assemble_result.py 幂等更新 result.json 并 --validate。

## 四、目录约定（赛题运行时）

- 工作目录 `/app/work`：中间产物、pdftotext 抽取文本。
- 交付目录 `/app/output`：上表全部交付物 + result.json。
