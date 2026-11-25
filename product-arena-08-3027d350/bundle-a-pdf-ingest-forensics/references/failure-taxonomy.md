# 输入失效模式分类表（failure taxonomy）

每种失效模式给出：检测信号 → 路由动作 → result.json 中应使用的诚实措辞。
原则：**说"读不了"永远是合法答案；猜内容永远不是。**

| # | 失效模式 | 检测信号（脚本/字段） | 路由动作 | result.json 诚实措辞（uncertainty / intake_notes） |
|---|---|---|---|---|
| 1 | 加密 PDF（含权限加密） | pdf_probe: `/Encrypt` 标记；`encrypted: true`；exit 3 | `refuse_with_handoff`，status=failed | "Input PDF is encrypted (/Encrypt marker present). No content was extracted and none was guessed. Provide a decrypted copy or credentials through the proper channel." |
| 2 | 不是 PDF / 文件损坏 | pdf_probe: `header_ok: false` 或零页对象；exit 3 | `refuse_with_handoff`，status=failed | "Input does not start with a %PDF- header / contains no page objects; it cannot be parsed as a PDF." |
| 3 | 整本扫描件（无文本层） | 所有页 `scanned_candidate`（有图像、字符 <20/页） | `ocr_handoff`（整本），status=partial | "Document has no usable text layer on any page; all content must come from OCR and carries OCR uncertainty." |
| 4 | 部分扫描页 | 部分页 `scanned_candidate` | `mixed_pagelevel`；这些页 action=ocr_handoff | "Pages [N, M] are scanned images without a text layer; their content is deferred to OCR and was not read at triage time." |
| 5 | CID/自定义编码乱码（PUA） | glyph_audit: 页对应文件 PUA 比率 > 0.5%，severity=high | 该页改派 `ocr_handoff`（文本层不可信） | "Page N text layer consists of private-use-area glyphs (broken ToUnicode map); extracted characters are meaningless and were discarded in favour of OCR." |
| 6 | 解码失败（U+FFFD） | glyph_audit: U+FFFD 连续段 > 2 | 同上 | "Page N contains runs of U+FFFD replacement characters (failed decode); affected spans are unrecoverable from the text layer." |
| 7 | UTF-8-as-Latin-1 mojibake | glyph_audit: mojibake 命中成簇（`â€`、`ç±»` 形态） | 该页 OCR 或要求上游重新导出 | "Page N shows UTF-8-as-Latin-1 mojibake (e.g. 'â€'); the extraction encoding is wrong and the text must be re-acquired." |
| 8 | 旋转页 | pdf_probe: `/Rotate` ≠ 0 | `direct_text_layer` + 强制注明回正 | "Page N declares /Rotate=90|180|270; layout-sensitive analysis must apply this rotation first." |
| 9 | 重复页 | pdf_probe: 指纹相同，`duplicate_of` 非空 | `direct_text_layer`，只解析一次 | "Page M duplicates page N (identical text fingerprint); it was parsed once and must not be double-counted as evidence." |
| 10 | 空白页 | `empty_page`（字符 0 且无图像） | 记录，跳过 | "Page N is empty (no text, no images); treated as intentionally blank." |
| 11 | 纯图像表格/图版 | 所在页判 scanned 或图像占满 | OCR + 表格工具；本 Skill 不取值 | "Tables/figures on page N are image-only; no cell values were read or inferred at triage time." |
| 12 | 覆盖率未测量 | `text_layer_measured: false`（无 poppler/pymupdf/manifest） | 临时路由，status≤partial | "Per-page text-layer coverage was NOT measured (no poppler/PyMuPDF available); routing is provisional and must be re-confirmed." |
| 13 | 文本层存在但与图像不一致 | glyph 正常但 char_count 异常低 + 有图像 | 该页 OCR 复核 | "Page N text layer is suspiciously thin relative to its image content; OCR cross-check recommended." |
| 14 | case 契约字段无法填充 | route_decision: 非本 Skill 职责的字段 | 字段留空 | "Field '<name>' left empty: content extraction is downstream of this triage skill and was not performed." |

## 措辞纪律

- 永远写明**证据**（哪一页、哪个信号、哪个阈值），不写"似乎""大概"。
- 永远区分三件事：*没有读*（not read）、*读了但不可信*（discarded）、
  *读了且可用*（trusted）。
- status 只能是证据支持的最高档：有任何未解决异常就不到 `success`。
