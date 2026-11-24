# 分诊 taxonomy（12 + 1 类）

每个输入文件恰好归入一类。检测规则全部机械化、证据可回查；处置与恢复建议
固定映射，不允许"看情况"。

| 类别 | 检测规则 | 处置 | 恢复建议 |
|---|---|---|---|
| `ok` | 可读取且文本抽取正常 | 按规则归档 | — |
| `duplicate_bytes` | SHA-256 与组内另一文件相同 | 保留组内最小 fid，其余 `_archive_dups/` | 字节级重复，不删除 |
| `sidecar` | .md/.csv/.json/.bib/.txt/.ris/.yml 旁挂文件 | `00-admin/` | — |
| `encrypted_pdf` | pdftotext 失败且 stderr 含 password/encrypt | `_quarantine/encrypted_pdf/` | `pdftotext -upw 密码` 后重新 triage |
| `corrupt_pdf` | pdftotext 失败且无加密特征 | `_quarantine/corrupt_pdf/` | 重新下载或 `qpdf --repair` |
| `no_text_layer` | 抽取成功但文本 <20 字符 | `_quarantine/no_text_layer/` | OCR（如 ocrmypdf）后重新 triage |
| `permission_denied` | 打开触发 PermissionError | `_quarantine/permission_denied/` | chmod/chown 后重新 triage |
| `read_error` | 其他 OSError | `_quarantine/read_error/` | 检查文件系统/介质 |
| `empty_file` | size=0 | `_quarantine/empty_file/` | 确认来源并重新获取 |
| `garbled_encoding` | 文本文件 U+FFFD 占比 >1% | `_quarantine/garbled_encoding/` | 按原始编码（GBK/Big5 等）转 UTF-8 |
| `unknown_binary` | 非 PDF 非文本的二进制 | `_quarantine/unknown_binary/` | 确认类型与配套工具 |
| `extract_unavailable` | 运行环境缺 pdftotext | `_quarantine/extract_unavailable/` | 安装 poppler 后重新 triage |
| `processing_error` | 处理中抛出未预期异常（运行时追加） | 进 skipped，不复制 | 人工检查后重跑 |

## 判定优先级

`duplicate_bytes` > 不可读类（permission_denied/read_error）> `empty_file` >
`encrypted_pdf`/`corrupt_pdf` > `no_text_layer` > `unknown_binary` >
`garbled_encoding` > `sidecar` > `ok`。

## 隔离区约定

- `_quarantine/<类别>/<原始文件名>`：原样复制，不改名、不修复、不删除；
  重名不同内容自动 `-n` 后缀。
- `quarantine_manifest.json`：每条的 `preserved_at` 与 `sha256` 必须与实际
  文件一致（verify 阶段复核）。
- 隔离文件计入 skipped（含 recovery），不计入 library_index 的归档区。
