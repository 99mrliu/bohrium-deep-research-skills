---
name: section-structure-cartographer
description: >-
  文献 PDF 章节结构制图：当任务要求还原论文骨架——多级标题层级与编号体系、
  摘要/正文/参考文献/附录分段、图表题注定位、参考文献条目级切分、结构一致性
  审计——时使用本 Skill。核心做法是四段确定性脚本流水线：行级样式抽取
  （pymupdf → pdftotext -bbox → pdftotext -layout 引擎链自动降级）→ 标题检测与
  层级定级（编号深度优先，无编号标题按字号秩映射）→ references 区间条目级切分
  （不丢字符，余量进 leftovers 诚实标注）→ 一致性审计（跳号/重复/逆序/层级断裂/
  图表引用与题注双向核对/字符覆盖率）并产出契约感知 result.json。每个结构节点带
  页码+纵坐标锚点，可复核。不在范围内：阅读顺序重建、表格单元格解析、公式线性化、
  正文语义抽取。
---

# section-structure-cartographer：论文骨架还原与结构审计

**核心原则：先跑确定性脚本拿到带页码+纵坐标锚点的结构化产物，模型只审报告、补判断字段；读不出的如实标注 partial，绝不伪造。**

## 1. 总览

```
/input/case.json + /input/**.pdf
        │
        ▼
scripts/extract_styled_lines.py   引擎链: pymupdf → pdftotext -bbox → pdftotext -layout
        │  → /app/work/lines.jsonl（page,y0,x0,text,max_size,sizes,bold,engine,mode）
        ▼
scripts/build_hierarchy.py        编号深度优先 + 字号秩 + 关键词
        │  → /app/work/document_tree.json（嵌套 children，节点含 number/title/page/y0/level）
        │  → /app/work/spans.json（front_matter/body/references/appendix 区间锚点）
        ▼
scripts/split_references.py       [n] / n. / 作者行 起始模式，leftovers 不丢字符
        │  → /app/work/references.json（raw_text, anchor, first_author_guess, year_guess）
        ▼
scripts/audit_structure.py        跳号/重复/逆序/层级断裂 + 图表双向核对 + 覆盖率
        │  → /app/output/audit_report.json
        │  → /app/output/result.json（契约感知，含 status/sources/uncertainty/change_record）
```

中间产物落 `/app/work`，最终交付物（含 result.json）落 `/app/output`。

## 2. 运行契约

1. 输入：`/input/case.json`、`/input/task.md`、案例 PDF（可能在 `/input` 子目录，
   先 `ls -R /input` 定位）。
2. 工作区 `/app/work`（中间产物）；交付区 `/app/output`（最终产物 + `result.json`）。
3. `result.json` 必须含原 `case_id` 与 `output_contract` 声明的全部字段；无法填充的
   字段置 `null` 并在 `uncertainty` 说明，`status` 标 `partial`；必须含
   `status`（success/partial/failed/unable）、`sources`、`uncertainty`、
   `change_record`。诚实 partial，绝不伪造。
4. 预算纪律：脚本是确定性的、不消耗模型请求。正确用法：先跑脚本拿结构化产物，
   模型只读 case、调脚本、审报告、写需要判断的字段。**先尽早落盘 partial，
   再增量改善**——第一步就把四段脚本跑完并写出 result.json，之后有时间再复核。
5. 退出码：0=成功、2=部分（降级/余量）、3=失败；每步写机器可读 JSON 报告；
   任何失败不静默。

## 3. 操作步骤（给评测 Agent）

```bash
ls -R /input                                  # 定位 case.json 与 PDF
mkdir -p /app/work /app/output
PDF=$(find /input -name '*.pdf' | head -1)

# 1) 行级样式抽取（自动引擎链；也可用 --engine bbox|layout 强制降级）
python3 scripts/extract_styled_lines.py --pdf "$PDF" \
    --out /app/work/lines.jsonl --report /app/work/extract_report.json

# 2) 标题检测与层级定级 + 结构区间
python3 scripts/build_hierarchy.py --lines /app/work/lines.jsonl \
    --tree /app/work/document_tree.json --spans /app/work/spans.json \
    --report /app/work/build_report.json

# 3) 参考文献条目级切分
python3 scripts/split_references.py --lines /app/work/lines.jsonl \
    --spans /app/work/spans.json \
    --out /app/work/references.json --report /app/work/split_report.json

# 4) 一致性审计 + 契约感知 result.json
python3 scripts/audit_structure.py --lines /app/work/lines.jsonl \
    --tree /app/work/document_tree.json --spans /app/work/spans.json \
    --references /app/work/references.json \
    --case /input/case.json --source-pdf "$PDF" \
    --audit /app/output/audit_report.json --result /app/output/result.json
```

随后：读 `audit_report.json` 与 `result.json`，把 `uncertainty` 中列出的空缺
与 `heading_candidates` 中无法定级的候选过目；只有当你能从 PDF 原文确认时才
手工修正，并把修正写进 `result.json.change_record`。将需要交付的最终 JSON
复制到 `/app/output/`。

## 4. 输出物说明

| 文件 | 内容 | 复核方式 |
|---|---|---|
| lines.jsonl | 行级样式（page,y0,x0,text,max_size,sizes,bold,engine,mode） | 抽查任意行，按 (page,y0) 对照 PDF |
| document_tree.json | 嵌套标题树，节点含 number/title/level/kind/page/y0 + heading_candidates | 目检层级（如 1.1 挂在 1 下）；节点锚点回查原文 |
| spans.json | front_matter/body/references/appendix(/acknowledgments) 区间起止锚点 | 起止 (page,y0) 对照原文 |
| references.json | 条目级 raw_text、anchor、first_author_guess、year_guess、leftovers、字符对账 | char_accounting.balanced 必须为 true |
| audit_report.json | 编号审计、图表引用 vs 题注双向差异、覆盖率 | 差异条目按 (page,y0) 回查 |
| result.json | 契约字段 + status/sources/uncertainty/change_record | 契约字段逐个非空或有 null 说明 |

## 5. 方法要点（阈值与判据；详见 references/heading-patterns.md）

- 正文基线字号：长度 ≥ 30 字符行的 `max_size` 中位数。
- 无编号标题：`max_size ≥ 1.15×` 基线、长度 ≤ 90、且（粗体 或 ≥ 1.40× 基线）；
  按字号降序秩映射层级（rank 1 → L1）。
- 编号标题：`^\d+(\.\d+){0,3}[.)]?\s+`，深度 = 分段数；长度 > 120 或
  含年份+逗号者降级为候选。
- 首个关键词/编号标题之前为 front_matter，其中 ≥ 1.40× 基线的大字号行是
  文档题名，不进层级树。
- 关键词：Abstract/摘要/Introduction/References/Bibliography/Acknowledg/Appendix。
- 参考文献起始模式：`[n]` > `n.`/`n)` > 作者行（大写起始+逗号+年份，且上条以
  句点收尾）。字符对账必须平衡，任何余量进 leftovers 不丢弃。
- 图表双向核对：题注 `Figure N:`/`Fig. N`/`Table N:` 行集合 vs 正文引用集合，
  两个方向的差异都列出。
- 编号审计：跳号、重复、逆序、层级断裂（如 1 → 1.1.1 缺 1.1）。

## 6. 异常与限制

| 情形 | 处置 |
|---|---|
| pymupdf 缺失 | 自动降级 pdftotext -bbox（mode=geometry），报告写明 engine 与原因，退出码 2 |
| pdftotext 也缺 / -bbox 失败 | 再降级 -layout（mode=text，y0 用行序代替并标注），退出码 2 |
| 三引擎全失败 | 退出码 3，报告 status=failed，不静默 |
| geometry/text 模式 | 字号秩规则不可用，仅靠编号+关键词；result.json status=partial 并说明 |
| 无 References 标题 | split 退出码 3，报告 status=failed；result.json 对应字段置空 |
| 条目切不出 | 全部进 leftovers，status=partial，字符不丢 |
| 无法定级的标题候选 | 列 heading_candidates + degraded_notes，不猜层级 |
| 多栏排版 | 行序按 (page,y0,x0) 排序，**不做跨栏阅读顺序重建**（超出范围），多栏文档需谨慎复核 |
| 表格单元格 / 公式线性化 | 不在本 Skill 范围，见 description |
| 扫描版无文本层 PDF | 三引擎均抽不到行 → failed；本 Skill 不做 OCR |

## 7. 最小示例（**合成示例**，非正式案例、非真实论文）

`examples/minimal/`：输入 PDF 由 `inputs/make_sample.py` 纯标准库生成
（3 页单栏，Helvetica/Helvetica-Bold 多字号），含编号章节、图/表题注、
正文引用 Figure 1 与 Figure 3（Figure 3 故意无题注）、4 条 `[n]` 参考文献。

复现（在 skill 根目录）：

```bash
python3 examples/minimal/inputs/make_sample.py
python3 scripts/extract_styled_lines.py --pdf examples/minimal/inputs/sample.pdf \
    --out examples/minimal/outputs/lines.jsonl --report examples/minimal/outputs/extract_report.json
python3 scripts/build_hierarchy.py --lines examples/minimal/outputs/lines.jsonl \
    --tree examples/minimal/outputs/document_tree.json --spans examples/minimal/outputs/spans.json \
    --report examples/minimal/outputs/build_report.json
python3 scripts/split_references.py --lines examples/minimal/outputs/lines.jsonl \
    --spans examples/minimal/outputs/spans.json --out examples/minimal/outputs/references.json \
    --report examples/minimal/outputs/split_report.json
python3 scripts/audit_structure.py --lines examples/minimal/outputs/lines.jsonl \
    --tree examples/minimal/outputs/document_tree.json --spans examples/minimal/outputs/spans.json \
    --references examples/minimal/outputs/references.json \
    --case examples/minimal/inputs/case.json --source-pdf examples/minimal/inputs/sample.pdf \
    --audit examples/minimal/outputs/audit_report.json --result examples/minimal/outputs/result.json
```

预期：层级树 1.1 挂 1 下、2.1/2.2 挂 2 下；参考文献切成 4 条；
audit 报出 `cited_not_captioned: [3]`（Figure 3 被引用但无题注）。
降级自测：`--engine bbox` 与 `--engine layout` 可分别触发 mode=geometry /
mode=text 的 partial 路径。
