# 保真台账与锚定复验规则（provenance spec）

本文件定义 bundle-a 的两块基石：**保真台账**（inventory.json）的字段语义，与
**锚定复验**（anchor_report.json）的判定规则。目标是让每条审查结论都锚定在
可机器复验的原文证据上，杜绝"凭空结论"与"漏查静默跳过"。

## 1. 保真台账字段（inventory.json → files[]）

| 字段 | 含义 | 取值规则 |
| --- | --- | --- |
| `file` | 输入文件名 | 原样记录，不改名 |
| `relpath` | 相对路径 | 脚本执行视角的相对路径 |
| `ext` | 扩展名（小写） | 用于选择抽取方式 |
| `bytes` | 文件字节数 | `os.path.getsize` |
| `sha256` | 内容哈希 | 流式计算，全量 64 位十六进制；是"稿件版本"的唯一锚点 |
| `extract_method` | 抽取方式 | `direct_read(utf-8,errors=replace)` / `pdftotext` / `none` |
| `extract_status` | 抽取状态 | `ok` / `extract_error` / `needs_office_tool` / `unsupported` |
| `char_count` | 抽取文本字符数 | 仅 `ok` 时 >0；其余为 0 |
| `extracted_file` | 抽取文本落盘位置 | 相对 work 目录，如 `extracted/00-manuscript.md.txt` |
| `note` | 异常说明 | 失败/跳过原因，必须如实、具体 |

### 抽取方式分派

- `.md` / `.txt` / `.tex`：直读，统一 `utf-8, errors=replace`。
- `.pdf`：`shutil.which("pdftotext")` 检测；可用则 `pdftotext -enc UTF-8 <pdf> -`，
  不可用 / 非零退出 / 输出为空均记 `extract_error` 并写明原因（含是否疑似扫描件）。
- `.docx`：记 `needs_office_tool`。**禁止**用字符串猜测、禁止伪造正文。
- 其他扩展名：记 `unsupported`。任何状态都不是 `ok` 的文件必须出现在
  result.json 的 `uncertainty` 中——不允许静默跳过。

## 2. 锚定复验规则（anchor_report.json）

1. **语料**：inventory 中所有 `extract_status=ok` 文件的抽取文本，按文件名排序，
   顺序固定，保证确定性。
2. **归一化**：原文与引用统一做空白归一化——`re.sub(r"\s+", " ", s).strip()`，
   即所有连续空白（换行、制表、全角/半角空格序列）折叠为单个半角空格。
   除此之外**不做**任何变换（不改大小写、不去标点、不繁简转换）——
   引用必须逐字，锚定才有证据价值。
3. **判定**：归一化后的 `original_text` 是某个归一化语料文本的子串 → `verified`，
   记录 `matched_file` 与归一化偏移；否则 → `not_found`。
4. **前置拒绝**：`original_text` 为空/缺失 → `not_found`（理由"无法锚定"）；
   超过 300 字符 → `not_found`（理由"违反引用纪律"）。
5. **降级**：`not_found` 条目一律 `downgrade_to=pending_review`，理由写清；
   最终 result.json 中这些条目 `status=pending_review` 且保留
   `downgrade_reason`，**不得删除、不得改写引用后放行**。
6. **确定性**：同一 inventory + 同一 findings_draft 必得同一 anchor_report；
   条目编号（f-001 起）按草稿顺序分配，重跑稳定（幂等）。
7. **覆盖性**：草稿中出现但 anchor_report 未覆盖的条目（例如 verify 后草稿被改动），
   build_result 按未锚定处理，同样降级 pending_review。

## 3. 诚实门

最终 result.json 中，output_contract 的任一字段为 `null` 且 `null_reasons`
无对应说明时，`status` 强制降为 `partial`，并在 `uncertainty` 与
`change_log` 留痕。宁可 partial，不可假装 complete。
