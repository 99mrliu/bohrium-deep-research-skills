---
name: citation-numeric-crosscheck
description: 论文审查中"引用支持 + 跨位置数值一致性"的确定性深查技能——当需要机械核对引文标记与参考文献表（悬空/未引/重复/DOI）、跨摘要/正文/结论/图表标题比对同一物理量取值时触发；不适用于文献全文不可见时的主张判定（一律 cannot_verify 进待复核），也不覆盖方法设计、统计分析、论证链的深度审查（仅按最低检查点轮查登记）。
---

# citation-numeric-crosscheck

## 核心思想

能用确定性算法查的绝不用印象：

1. **数值总表**：把稿件中全部"数值提及"（数值+单位+上下文关键词）抽成总表，按
   就近关键词聚类同一物理量，跨小节（摘要/正文/结论/图表标题）比对；同一量出现
   ≥2 个不同值且超出舍入容差 → 候选不一致 finding，带两处原文定位与逐字引用。
2. **引文台账**：全部正文引文标记与参考文献表机械对照（悬空引用、未被引用、
   重复著录、DOI 格式异常）；只有文献全文/摘要可见时才做"论断↔被引主张"支持判定，
   不可见一律 `cannot_verify` 进待复核，绝不臆断文献内容。

## 适用边界

- 适用：编号制/作者-年制引文对照；%、±、单位量、n=、p 值、倍数的跨位置一致性。
- 不适用：方法设计/统计分析/论证链/学术规范的深度审查（四面仅按
  references/facet_coverage.md 最低检查点轮查登记）；文献不可见时不产出支持结论；
  不编造页码、DOI、文献结论。

## 运行时契约

- Skill 安装到 `/skills/weekly-skill`，脚本以 `python3 /skills/weekly-skill/scripts/xxx.py` 调用。
- 输入 `/input/case.json`、`/input/task.md` 与材料（PDF/DOCX/MD/TXT/TeX）；
  case.json schema 未知须宽容：output_contract 支持字段名列表或 dict，缺失回退
  默认字段集并在 uncertainty 说明。
- 工作目录 `/app/work`；成果 `/app/output/result.json`（含原 case_id 与契约全部字段）
  + `/app/output/review_report.md`。
- 第一次脚本调用即产出保底 partial result.json（numeric_scan.py 自动写入），之后增量改进。
- 仅用 Python 3 标准库；PDF 抽取检测 `pdftotext`（shutil.which），不可用则记录
  extract_error；文本统一 `utf-8, errors=replace`。

## 分步工作流

```bash
# 第 1 步：数值一致性扫描（同时写保底 partial result.json）
python3 /skills/weekly-skill/scripts/numeric_scan.py \
  --input /input --work /app/work --output /app/output
# 产物：/app/work/numeric_report.json 与 .md；/app/output/result.json（保底）

# 第 2 步：引文标记 × 参考文献表机械对照 + 支持判定台账
python3 /skills/weekly-skill/scripts/cite_match.py \
  --input /input --work /app/work
# 产物：/app/work/citation_ledger.json 与 .md

# 第 3 步：汇总 → 契约对齐 result.json（原子写入）+ review_report.md
python3 /skills/weekly-skill/scripts/build_result.py \
  --input /input --work /app/work --output /app/output
```

## 输出 schema（result.json）

- 必含 case.json 的 `case_id` 与 `output_contract` 全部字段（缺省回退
  `["case_id","status","review_report","findings","sources","uncertainty","change_log"]`）。
- `findings[]`：`{id(NUM-xxx/CITE-xxx), facet, severity, type, title,
  locations[{section,line,quote}], evidence, basis, status}`。
- `pending_review[]`：cannot_verify 的支持判定等，含 `item/reason/action_needed`。
- `facet_coverage`：六分面状态（checked_clean/issues_found/partially_checked/
  unable_to_check + note）。
- `sources[]`：材料文件名 + sha256 + 字节数。

## 异常处置

- 材料解析失败 → 该材料记录 extract_error，其余材料照常处理，uncertainty 如实说明。
- 无参考文献小节 → WARNING 记录，引用支持分面标 unable_to_check，其余检查照常。
- 契约字段无法产出 → 置 null 并写 null_reasons，诚实门自动把 status 降为 partial。
- 任何脚本退出码非 0 → 失败原因已打印到 stderr，先修输入/环境再重跑。

## 文件清单

- `scripts/numeric_scan.py`：数值提及抽取、聚类、跨小节一致性比对 + 保底 result。
- `scripts/cite_match.py`：参考文献解析、引文定位、四项机械检查、支持判定台账。
- `scripts/build_result.py`：契约对齐汇总、诚实门、原子写入、报告渲染。
- `references/support_rubric.md`：支持判定四级规则与防误报纪律。
- `references/numeric_consistency.md`：容差、单位换算、舍入一致规则。
- `references/facet_coverage.md`：六分面最低检查点与状态值。
- `examples/`：合成示例（输入 + 真实跑出的输出），非正式案例结果。
