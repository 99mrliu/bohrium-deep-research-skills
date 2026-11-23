---
name: source-fidelity-notes
description: Produce structured paper notes whose first-class concern is upstream truth — a forensically scanned, line-anchored text layer with an explicit fidelity receipt, so every summary claim, number and section boundary can be traced to a verified source line and every unreadable region is named instead of silently summarized. Use for literature summary, structured notes, paper cards and evidence-anchored Q&A on real PDFs, including two-column or damaged scans.
---

# Source-Fidelity Notes

重心在上游：笔记烂尾大多发生在“文本已经错了，后面全在错的文本上总结”。本 Skill 先把原文变成带行级锚点、可复算的保真文本层，拿到保真回执后再写笔记；文本层担保不了的内容（图内数值、公式上下标、扫描页）必须显式降级。

## 运行契约

- 输入：`/input/case.json`（含 `case_id` 与 `output_contract`）、`/input/task.md` 与随案例提供的真实论文文件。先读它们，确定交付形态（笔记/卡片/问答/核验），再决定笔记字段；不要假设每个案例都要长摘要。
- 工作区：`/app/work`；交付区：`/app/output`。最终必须写出 `/app/output/result.json`，其中含 `case_id` 与 `output_contract` 声明的全部字段；其余工件（source.json、fidelity.json、atlas.txt、anchor-report.json、notes.md）一并放入 `/app/output` 供复核。
- 状态诚实：`success` 仅当合同字段齐备且锚点校验通过；任何缺口 → `partial` 并在 `limits` 中逐项命名；文本层不可得 → `failed` 并给出人工接管位置。绝不编造缺失软件状态或论文内容。
- 预算：64 次模型请求 / 900 秒。开局 2 步内必须落盘骨架 result.json（见第 4 步），此后增量改进。

## 流程（设 K 为本 SKILL.md 所在目录）

### 1. 保真扫描（先于一切阅读）

```sh
python3 "$K/scripts/fidelity_scan.py" --pdf /input/<paper>.pdf --case-id "$CASE_ID" --out /app/work/scan
# 无 PDF 后端或扫描件时，用平台 PDF 文本/OCR 工具导出文本后：
python3 "$K/scripts/fidelity_scan.py" --text-file /app/work/ocr.txt --case-id "$CASE_ID" --out /app/work/scan
```

产出 `source.json`（行锚点 `p{页}-l{行}`）、`fidelity.json`（保真回执）与 `atlas.txt`（人读行图）。**先读 fidelity.json**：`empty_or_image_pages`、`page_flags`、`backend`、分栏证据。回执为 `degraded` 时，把受损页列入最终 `limits`，笔记里涉及这些页的内容标 `unverifiable`+理由。`unreadable` 时立即停止总结，按回执的 `handover` 处理。

### 2. 按回执阅读，写带锚点的笔记

在 `/app/work/notes.json` 中按 [references/note-fields.md](references/note-fields.md) 填：

- `result_fields`：与 case 的 `output_contract` 一一对应的交付内容（答案/卡片/章节笔记等），这是 result.json 的主体；
- 每个关键论断对象带 `anchor`（精确到行）与 `quote`（该行逐字片段，可跨行则取连续两行内的连续片段）；
- 无法核验的条目写 `"status":"unverifiable","reason":...`，锚点校验对这类条目豁免；
- `null_reasons`：result_fields 里每个 null 字段的检索范围与理由；
- `limits` / `uncertainty` / `change_records`：受损页、跨栏修复、你修正过的锚点。

锚点格式与保真指标含义见 [references/fidelity-metrics.md](references/fidelity-metrics.md)。决定性数值若落在表格/图内，回渲染页核对后在 `uncertainty` 留痕；文本层的表格对齐与公式上下标不作数。

### 3. 锚点校验（可复算质量门）

```sh
python3 "$K/scripts/anchor_check.py" --notes /app/work/notes.json \
  --source /app/work/scan/source.json --out /app/work/anchor-report.json
```

`fail`（引文不在锚点行）必须修复或标 `unverifiable`；`needs_review`（跨行/连字符）回渲染页目检后在 change_records 记录。校验不通过不得升级 success，但也不得清空已写内容。

### 4. 组装并交付

```sh
python3 "$K/scripts/make_result.py" --case /input/case.json --notes /app/work/notes.json \
  --scan /app/work/scan --anchor-report /app/work/anchor-report.json --out /app/output
```

脚本只做三件事：把 `result_fields` 拷入合同字段、做合同子集校验（required/类型/enum，未知关键字只警告不放行）、合并保真回执与锚点报告得出诚实状态。它从不删内容、从不自动升级状态。最后再写 `/app/output/notes.md`（人读版，按论文章节序，引用以 `[p页-l行]` 内联标注）。

## 异常处理

- 加密/无文本层/扫描 PDF：扫描器返回 `unreadable` 与接管指引；用平台 OCR 导出文本后走 `--text-file` 通道，保真回执会标明“无坐标、分栏审计不可用”。
- 双栏错序：几何分栏已重建阅读序，但三栏/杂志版式需回渲染页抽查；证据在 fidelity.json 的 `pages[].columns.evidence`。
- 超长论文：先扫全量，再只对任务相关章节做精读与锚点化；未精读章节在 `limits` 命名。
- 任何后端缺失：回执记录完整 probe 链，不静默换语义。

## 最小示例（合成）

`examples/synthetic-case/` 内含合成论文文本、case.json、task.md 与 `run_example.sh`（输出目录外置，示例输出标注为合成示例，非正式案例结果）：

```sh
sh "$K/examples/synthetic-case/run_example.sh" /tmp/sfn-demo
```

## 依赖与边界

Python 3.9+ 标准库；PDF 通道优先调用 `pdftotext`（poppler）或 PyMuPDF，二者皆无时必须经平台 PDF 文本工具导出文本走 `--text-file`。不联网、不安装包。锚点与后端绑定，换后端必须重扫重验。详细方法与已知边界见 [references/fidelity-metrics.md](references/fidelity-metrics.md)。
