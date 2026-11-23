---
name: reading-order-reconstructor
description: >-
  多栏科研 PDF 的阅读顺序重建与逐块溯源解析器。当案例输入是单栏/双栏/多栏论文 PDF，
  任务要求"提得全、排得对、核得回"——即逐字提取正文/题注/脚注/参考文献、按原版面
  顺序输出（不串栏、不错行）、每个段落能指回页码与坐标区块——时触发本技能。核心做法：
  词级坐标抽取（PyMuPDF→pdftotext 回退链）→ 行/块聚类 → 页眉页脚剔除 → 直方图分栏
  与整宽屏障阅读顺序重建 → 带锚点全文 + 契约感知 result.json。读不出的部分如实标注，
  不靠猜补齐。不在范围内：复杂表格的单元格级重建（另有专门技能）、扫描件 OCR 本体
  （无文字层时如实报告并移交 ocr-tool）、图表科学含义理解。
---

# reading-order-reconstructor — 多栏阅读顺序重建 · 逐块溯源

**核心原则：顺序由版面几何决定，不由语言模型猜。每个输出块都带 `page/column/bbox`，可复核。**

本技能专攻 PDF 解析四难中的"排得对"与"核得回"：双栏/多栏串栏、跨栏整宽内容（标题、
摘要、通栏图）定位、页眉页脚混入正文、跨页续段。表格单元格级重建请配合表格专门技能；
扫描件请先走 OCR 取得文字层再回本流水线。

## 总览

```
/input/ 的 PDF
  → scripts/extract_words.py     → /app/work/words.tsv + pages_meta.json + extract_report.json
  → scripts/order_blocks.py      → /app/work/blocks.jsonl   （页/栏/序/类型/坐标/续接）
  → scripts/assemble_output.py   → /app/output/fulltext.md · sections.json · references.json
                                    · captions.json · coverage.json · result.json
```

三个脚本均只用 Python 3 标准库；引擎缺失时逐级回退，任何失败写 JSON 报告并以退出码
表达状态（0 成功 / 2 部分 / 3 失败），绝不静默产出"看起来像全文"的文本。

## 运行契约（平台评测环境）

- 输入：`/input/case.json`、`/input/task.md`、案例 PDF（可能在 `/input/` 或其子目录，
  先用 `ls -R /input` 定位；**读实际文件，不要凭文件名猜内容**）。
- 工作区：`/app/work`（中间产物）；交付区：`/app/output`（最终产物 + result.json）。
- `result.json` 必须含原 `case_id` 与 `output_contract` 声明的全部字段；无法填充的字段
  置空并在 `uncertainty` 中说明，状态标 `partial`，不得伪造。
- 预算纪律：64 次模型请求 / 900 秒。先跑脚本拿结构化结果（不消耗模型请求），
  模型只负责读 case、调用脚本、审阅报告、写 result.json 中需要判断的字段。

## 操作步骤

1. **识别输入**：`ls -R /input`；读 `case.json` 记下 `case_id` 与 `output_contract`
   字段名清单；找到 PDF 实际路径。
2. **词级抽取**：
   `python3 scripts/extract_words.py --pdf <PDF> --out /app/work`
   先读 `extract_report.json`：`status=failed/reason=encrypted_pdf` → 停止并在
   result.json 如实报告加密；`reason=no_text_layer` → 移交平台 ocr-tool 取得文字层后
   以 `--tsv` 回灌；`status=partial`（仅 layout 文本）→ 无坐标，标 partial 交付。
3. **结构重建**：
   `python3 scripts/order_blocks.py --words /app/work/words.tsv --meta /app/work/pages_meta.json --out /app/work`
   读 stdout 报告：`status=partial` 表示有页降级为单栏，记 uncertainty。
4. **组装交付**：
   `python3 scripts/assemble_output.py --blocks /app/work/blocks.jsonl --words /app/work/words.tsv --case /input/case.json --out /app/output`
   随后人工（Agent）抽查：`fulltext.md` 随机 3 段的锚点坐标是否落在 PDF 对应页对应栏；
   `coverage.json` 的 `coverage_pct` 与 `dropped` 记账是否合理（dropped 应基本等于
   页眉页脚字符量）。
5. **异常落盘**：任何一步 partial/failed，都先把已有产物拷入 `/app/output`，
   在 result.json 写明 `status`、`uncertainty`、`handoff`（人工接管点）。

## 输出物说明

| 文件 | 内容 | 复核方式 |
|-|-|-|
| `fulltext.md` | 阅读顺序正文，每段前置锚点 `[p2.c1.b7 p2 body]`；跨栏/跨页续段标 `(续 ...)` | 锚点 → blocks.jsonl → 页码+坐标 |
| `sections.json` | title/heading 层级清单（含页码锚点） | 与原文目录/标题比对 |
| `references.json` | 参考文献块（页码锚点） | 抽查条目逐字一致 |
| `captions.json` | 图表题注（页码锚点） | 抽查题注逐字一致 |
| `coverage.json` | 字符覆盖台账：保留/剔除（页眉页脚）/未读 | 剔除项须有类别，不许静默丢弃 |
| `result.json` | case_id + output_contract 全字段 + status/sources/uncertainty/change_record | 契约字段逐项核对 |

## 方法要点（详见 references/method.md）

- 行聚类：y 重叠 >50% 归一行；块切分：纵间距 > 1.35×中位行高。
- 页眉页脚：页面顶部 9% / 底部 7% 内、且归一化文本（数字抹成 #）在 ≥40% 页面重复。
- 分栏：x 向找 ≥12pt 的最宽连续空白带，两侧各 ≥3 行才判双栏；整宽行（跨全部栏且
  宽度 >80% 版心）视为屏障，把页面切成纵向带，带内先左栏后右栏。
- 块类型：题注（Fig./Table/图/表 开头）、公式行（短行含数学符号或编号）、标题
  （编号模式 + 字号高于中位）、首页大字号整宽块为 title、References 之后为 reference。
- 续接：前块末非句读且后块非同栏标题时记 `continues_from`（同页跨栏与跨页均支持，
  只记关系、不擅自合并文本）。

## 异常与限制

| 情形 | 处置 |
|-|-|
| 加密 PDF | extract 报 `encrypted_pdf`，停止，result.json 标 failed+handoff |
| 无文字层（扫描件） | 报 `no_text_layer`，移交 ocr-tool，OCR 词表可经 `--tsv` 回灌 |
| 三栏以上/复杂版式 | 判不出空白带时按单栏降级并在 uncertainty 逐页列出 |
| 竖排/旋转页 | 未支持；检测词高宽比异常时如实标注 |
| 公式 | 按结构元素整行保留原符号，不转 LaTeX、不解语义 |

## 最小示例

`examples/minimal/` 是一份**合成示例**（非正式案例、非真实论文）：手工合成的双栏
两页词表 `inputs/words.tsv`（含页眉页脚、通栏摘要、跨页续段、参考文献区），
合成 `inputs/case.json`。复现：

```bash
python3 scripts/extract_words.py --tsv examples/minimal/inputs/words.tsv --out /tmp/ro_work
python3 scripts/order_blocks.py --words /tmp/ro_work/words.tsv --meta /tmp/ro_work/pages_meta.json --out /tmp/ro_work   # 无 meta 时可省略 --meta
python3 scripts/assemble_output.py --blocks /tmp/ro_work/blocks.jsonl --words /tmp/ro_work/words.tsv --case examples/minimal/inputs/case.json --out /tmp/ro_out
```

`examples/minimal/outputs/` 内是真实执行上述命令得到的产物，已目检：阅读顺序
摘要→引言→左栏→右栏→跨页续接→参考文献，页眉页脚被剔除并计入 coverage 台账。
