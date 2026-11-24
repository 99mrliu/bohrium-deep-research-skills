---
name: section-pinpoint
description: 章节定位方向。把文档库切成带层级地址的锚点（文件 › 物理页 › 章节标题 › 段落），处理印刷页码与 PDF 物理页错位、Markdown/编号标题、双栏 -layout 抽取与跨页段落；检索提问只返回命中章节/段落而非整篇文件，每条命中携带定位串、逐字锚点句、字符区间与置信说明，使"定位到的位置就是原文那一段"可被独立复核。当任务要求章节级定位、页码定位、避免返回整篇文件时使用；输入为 /input/case.json + task.md + 文档库。
---

# section-pinpoint：章节级定位引擎

## 重心

基础 Agent 的典型失分：用户要"哪一版哪一节"，得到的是整篇文件路径。
本技能把全库预先切成**带地址的锚点**（locator），检索只命中锚点，
答案永远落到"那一段"，并能被第三方按 locator 逐字复核。

## 运行契约（必须遵守）

1. 先读 `/input/case.json` 与 `/input/task.md`：记录 `case_id`，照抄
   `output_contract` 全部字段名；库路径与提问以 case.json 实际键名为准
   （常见 `library/library_root/data_dir` 与 `searches/questions/queries`），
   找不到就 `ls -R /input` 盘点，**不凭文件名猜内容**。
2. **立刻**写 `/app/output/result.json` 骨架（case_id + 全字段占位 +
   `"status":"partial"`），随后逐步填充。
3. 中间产物在 `/app/work`，交付物在 `/app/output`。`$S` 为技能安装目录
   （通常 `/skills/weekly-skill`）。脚本为 Python ≥3.9 标准库；
   `pdftotext`（poppler）存在时用于 PDF 逐页抽取，缺失则 PDF 如实记
   `no_pdf_tool` 并列入 uncertainty，**不要安装第三方包**。

## 执行步骤

```bash
S=/skills/weekly-skill
mkdir -p /app/work /app/output
# 1. 抽取 + 切锚点：每个文件产出一组 locator 记录 → anchors.jsonl
python3 "$S/scripts/pinpoint_ingest.py" <库根目录> /app/work/anchors.jsonl /app/work/ingest_report.json
# 2. 提问 → 章节级命中（每条含 locator、锚点句、字符区间、得分依据）
python3 "$S/scripts/pinpoint_search.py" /input/case.json /app/work/anchors.jsonl /app/work/hits.json
# 3. 组装 result.json（output_contract 全字段 + 诚实 status/uncertainty）
python3 "$S/scripts/pinpoint_result.py" /input/case.json /app/work /app/output/result.json
```

每步检查退出码；失败把错误原文记入 uncertainty 后继续。锚点定位规则与
页码错位处理见 `references/locator-scheme.md`。

## 输出形态（每个命中）

```json
{"question": "...", "status": "located",
 "hits": [{"locator": "项目A/开题报告_v2.md › §2.1 › ¶3",
           "page_physical": null, "page_printed": null,
           "heading": "2.1 缓冲液配方", "anchor_sentence": "缓冲液配方：50 mM …",
           "quote": "<=120字逐字片段>", "char_start": 812, "char_end": 960,
           "score": 7, "matched_terms": ["缓冲液", "配方"]}]}
```

找不到命中段： `status: no_match`，并记录检索过的词项与覆盖的文件数，
**不得放宽为整篇文件充数**。

## 异常处理

| 情况 | 处置 |
|-|-|
| PDF 无 pdftotext | 该文件记 no_pdf_tool，内容类提问在 uncertainty 声明 |
| 扫描件无文本层 | 记 needs_ocr；不虚构页码 |
| 文件读失败 | ingest_report.json 记录并跳过，写入 uncertainty |
| 提问无命中 | no_match + 检索词项清单，绝不返回整篇 |

## 最小示例

`examples/` 为**合成示例**（3 个多章节文本文件 + 1 个 CSV），运行
`python3 run_example.py`，预期见 `examples/README.md`。

## 限制

- 概念级同义扩展非本技能重心（它保证的是定位粒度与可复核性）。
- 双栏 PDF 依赖 `pdftotext -layout` 的栏序，复杂版式可能错序，会在
  锚点的 `note` 字段声明。
- 不处理库外文件与开放网络检索。
