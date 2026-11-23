---
name: table-grid-reconstructor
description: >-
  科研 PDF 复杂表格的结构重建器。当案例任务涉及表格提取——空白对齐表、跨行折行
  单元格、合并表头、线框（ASCII 线）表——并要求输出可继续处理的 Markdown/CSV/JSON
  结构、每个单元格能指回原文页码与源行区间时触发本技能。核心做法：保版式文本抽取
  → 共识分列位检测表格区域与题注绑定 → 分列位吸附切格、折行续接合并、跨列表头
  colspan 还原 → 三态输出（JSON 网格 + Markdown + CSV）。空单元格与歧义一律标
  unresolved 落盘，不靠猜补齐。不在范围内：多栏阅读顺序重建（另有专门技能）、
  图片型表格的视觉识别（无文字层时如实报告并移交 ocr-tool）、表格数值的科学解读。
---

# table-grid-reconstructor — 复杂表格结构重建 · 单元格可溯源

**核心原则：表格的结构（行列归属、折行、合并）由版式几何证据决定；判不出的单元格
标 unresolved，绝不填猜测值。**

本技能专攻 PDF 解析四难中的"拆得清"：把表格从一串空格对齐的文字还原成有行列归属、
合并标记和溯源信息的网格。多栏正文顺序请配合阅读顺序专门技能。

## 总览

```
/input/ 的 PDF（或既有版式文本）
  → scripts/extract_layout.py    → /app/work/pages/pageNN.txt + extract_report.json
  → scripts/detect_tables.py     → /app/work/tables_index.json（区域+题注+分列位+置信度）
  → scripts/reconstruct_grid.py  → /app/output/table_<id>.{json,md,csv}
                                    + reconstruction_report.json + result.json
```

三个脚本仅用 Python 3 标准库；失败写 JSON 报告 + 退出码（0 成功 / 2 部分 / 3 失败）。

## 运行契约（平台评测环境）

- 输入：`/input/case.json`、`/input/task.md`、案例 PDF（先 `ls -R /input` 定位真实文件）。
- 工作区 `/app/work`，交付区 `/app/output`；`result.json` 含原 `case_id` 与
  `output_contract` 全部字段；无法填充的字段置空 + `uncertainty` 说明 + `status: partial`。
- 预算纪律：先跑脚本拿结构化结果，模型只做判读、命名与 result.json 撰写；
  900 秒内先落盘诚实 partial，再增量完善。

## 操作步骤

1. `python3 scripts/extract_layout.py --pdf <PDF> --out /app/work`
   读 `extract_report.json`：`encrypted_pdf` → 停止并如实报告；`no_text_layer` →
   移交平台 ocr-tool 取得文本后以 `--layout-dir` 回灌；`partial`（空页）→ 记录后 continue。
2. `python3 scripts/detect_tables.py --pages /app/work/pages --out /app/work`
   读 `tables_index.json`：每张表带 page、caption、region（源行区间）、kind
   （whitespace/ruled）、columns（分列位）、confidence；无题注或题注偏远的表
   自带 unresolved 说明。`status=partial` 表示全文未检出表格——如实报告，不伪造。
3. `python3 scripts/reconstruct_grid.py --index /app/work/tables_index.json --pages /app/work/pages --case /input/case.json --out /app/output`
4. 抽查：`table_<id>.md` 中 ⚠ 标记的单元格逐一回到原文页核对；`reconstruction_report.json`
   的 notes 是全部歧义清单，必须进入 result.json 的 uncertainty。
5. 异常时先把已重建的表拷入 `/app/output`，写明 status 与 handoff。

## 输出物说明

| 文件 | 内容 | 复核方式 |
|-|-|-|
| `table_<id>.json` | 完整网格：每格 text/row/col/rowspan/colspan/wrapped/merged_into/unresolved；表级 page、caption、source_region、confidence | 单元格 → 页码+源行区间 |
| `table_<id>.md` | 阅读用 Markdown；⚠=未判定，〔跨n列〕=合并表头 | 与原文并读 |
| `table_<id>.csv` | 计算用纯净网格 | 直接入 pandas |
| `tables_index.json` | 检测层清单与置信度 | 漏检/误检核查 |
| `reconstruction_report.json` | 全部歧义 notes | 必须转写进 result.json |
| `result.json` | case_id + 契约全字段 + status/sources/uncertainty | 逐字段核对 |

## 方法要点（详见 references/method.md）

- 表格检测：≥3 行、每行 ≥2 处宽空白（≥2 空格，环视匹配允许相邻空隙）、
  空白列位共识聚类（±3 列）后 ≥60% 行覆盖；折行续接行（缩进 ≥6 且空隙不足）
  允许留在区域内但不参与共识。线框表由 ─-+|= 行簇识别，两类区域重叠去重。
- 题注绑定：区域内/上下 4 行内最近的 `Table n` / `表 n` 行；距离 >3 行标疑。
- 切格：分列位先吸附到"所有行均为空白"的列（±4 搜索），保证不切断文字。
- 折行续接：首格为空且仅一格非空 → 并入上一行该列（标 wrapped）。
- 合并表头：表头文字跨过分列位 → colspan，被跨列标 merged_into。
- 空数据格：可能是纵向合并也可能是缺失——不判定，标 unresolved。

## 异常与限制

| 情形 | 处置 |
|-|-|
| 加密 PDF | extract 报 encrypted_pdf，result.json 标 failed+handoff |
| 扫描件/图片表格 | 报 no_text_layer，移交 ocr-tool 后回灌 |
| 无线框也无对齐空白的"隐形表格" | 检不出，如实 partial |
| 跨页续表 | 各页独立重建；region 含页码，可在 result.json 注明同源后人工并表 |
| 多层表头 | 首行合并还原为 colspan；两层以上在 notes 说明，不硬猜层级 |

## 最小示例

`examples/minimal/` 为**合成示例**（非正式案例）：`inputs/page01.txt` 含空白对齐表
（4 列、折行单元格、一个空数据格），`inputs/page02.txt` 含线框表（一个空数据格），
`inputs/case.json` 为合成契约。复现：

```bash
python3 scripts/extract_layout.py --layout-dir examples/minimal/inputs --out /tmp/tg_work
python3 scripts/detect_tables.py --pages /tmp/tg_work/pages --out /tmp/tg_work
python3 scripts/reconstruct_grid.py --index /tmp/tg_work/tables_index.json \
  --pages /tmp/tg_work/pages --case examples/minimal/inputs/case.json --out /tmp/tg_out
```

`examples/minimal/outputs/` 是真实执行产物（已目检）：Table 1 四列正确、折行
"not detected (below 1 %)" 并入上格、两处空单元格标 ⚠ 未判定，status 为诚实的
partial（歧义已落盘）。
