# 保真指标与锚点格式（source-fidelity-notes）

## 锚点

- 行锚点：`p<页码>-l<行号>`，页码从 1 起，行号为该页阅读序中的视觉行序号（从 1 起）。
- 阅读序：坐标可用时按“跨栏行（页首标题区）→ 左栏 → 右栏”重建；仅文本导出时为导出原序，分栏审计不可用。
- 锚点与提取后端绑定：`source.json.backend` 改变时旧锚点全部作废，必须重扫并重跑 anchor_check。

## fidelity.json 字段

| 字段 | 含义 |
|---|---|
| `status` | `ok` / `degraded` / `unreadable` |
| `backend` / `backend_chain` | 实际后端与失败 probe 记录（数据，不是崩溃） |
| `sha256` | 原始输入字节哈希，复算留痕 |
| `page_count` / `total_chars` | 页数与总字符数；`chars<40` 的页列入 `empty_or_image_pages` |
| `page_flags` | 逐页旗标：`unicode_replacement_chars`、`control_chars`、`low_alnum_ratio`（编码损坏嫌疑）、`page_nearly_empty_text_layer`（扫描页嫌疑） |
| `sections` | 检测到的章节标题及其锚点；REFERENCES 之后不再认编号标题 |

## 判读规则

- `degraded` ≠ 失败：可在完好区域继续写笔记，但受损页必须进 `limits`，受损页支撑的论断标 `unverifiable`。
- `unreadable` = 立即停止：回执给出 `handover`（用平台渲染/OCR 工具导出文本后 `--text-file` 重跑）。
- 图内文字、公式上下标、表格单元格对齐不由文本层担保：凡决定性数值出自这些位置，回渲染页目检并在 `uncertainty` 记录。
- `columns.evidence` 记录分栏判据（跨中线行数等）；双栏之外的复杂版式不保证。

## 引文规则（anchor_check.py）

- `quote` 必须是锚点行的逐字子串（空白归一化后）；跨行引文允许取“本行+下一行”的连续片段，判 `needs_review` 而非 `fail`，须回渲染页确认。
- 引文中的数字必须出现在锚点行；缺失即硬失败。
- `"status":"unverifiable","reason":...` 的条目豁免锚点/引文检查，但必须在 `limits` 汇总。
- 校验退出码：0 通过 / 2 硬失败 / 3 输入错误。校验失败是修复指令，不是清空交付的理由。
