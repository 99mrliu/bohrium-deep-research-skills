---
name: structure-refs-cartographer
description: >-
  将科学论文的线性抽取文本重建为可导航结构：多级标题树（1 / 1.1 / 1.1.1 编号标题，
  以及按排版线索定级的无编号标题）、带页锚点的重建目录、图表题注索引
  （Fig. 1 / Table 2 → 页码 + 题注文本）、以及从字符串解析为结构化记录的参考文献
  （authors / year / title / venue / volume / pages / DOI），同时支持编号方括号
  （[1] ...）与作者-年份两种风格，并做一致性检查（章节编号断档/跳级、题注与正文
  引用双向核对、不可解析参考文献以 parse_status: raw 原样保留，绝不臆造字段）。
  触发条件：输入是 PDF 抽取的逐页文本（或 case PDF），任务要求章节层级、目录重建、
  图表题注索引、参考文献结构化或结构一致性审查时使用。
  不在范围：全文阅读顺序重建、表格单元格网格抽取、OCR。
---

# structure-refs-cartographer

把一篇科学论文的线性文本变成一张"地图"：标题树、目录、图表题注索引、结构化
参考文献，外加一致性检查报告。核心是一个**层级/解析问题**，不是阅读顺序问题。

## 总览

```
 PDF 或逐页文本
      │  (若只有 PDF：先用 pdftotext -layout 等工具转成 === page N === 文本)
      ▼
 ┌─────────────────┐   headings.json / toc.json
 │ heading_tree.py │ ─────────────────────────┐
 └─────────────────┘                          │
      │ pages.txt                             ▼
 ┌─────────────────┐   references.json   ┌──────────────────────┐
 │  refs_parse.py  │ ──────────────────► │  structure_report.py │
 └─────────────────┘                     │  (题注索引+双向核对)  │
      ▲                                  └──────────┬───────────┘
      └─────────────────────────────────────────────┤
                                                     ▼
                              structure_report.json + result.json
```

## 运行契约

- **输入发现**：先 `ls -R /input`。必有 `/input/case.json`（含 `case_id` 与
  `output_contract`）与 `task.md`；case PDF 或预抽取的逐页文本也在 `/input` 下。
- **文本形态**：脚本接受两种输入——(a) 从 PDF 派生的逐页文本（自行用
  `pdftotext -layout` 等转换），(b) 已抽取好的逐页文本文件。统一页标记格式：
  `=== page N ===` 独占一行。可选字号提示 TSV：`page<TAB>行号(从1计)<TAB>字号`。
- **工作区**：中间产物写 `/app/work`；**最终产物写 `/app/output`**。
- **result.json 契约**（`/app/output/result.json`）：
  - 必须原样带回 `case_id`；
  - `output_contract` 中**每一个字段**都要出现：有数据则 `status: ok`，
    没有则 `status: empty` 并附 `explanation`，不得静默缺字段；
  - `status` 必须诚实：`success`（全部契约字段有产出）/ `partial`（部分为空
    或输入缺失）/ `failed`（标题与参考文献均无产出）；
  - 附 `sources`、`uncertainty`、`change_record`。
- **预算**：64 次请求 / 900 秒。**脚本优先**——标题检测、题注扫描、参考文献
  切分与字段抽取全部是确定性脚本完成；模型只用于判断性工作（如裁决个别
  模糊条目的类型归属、撰写 explanation 文案），不得用模型逐条"阅读"全文。
- 脚本均为 Python 3 标准库实现，退出码：`0` 成功，`2` 用法/IO 错误，
  `3` 降级情形（未检测到标题 / 未找到参考文献区 / 缺 --case）。

## 操作步骤

```bash
ls -R /input                                   # 1. 发现 case.json / task.md / PDF或文本
mkdir -p /app/work /app/output
# 2. 若只有 PDF：pdftotext -layout paper.pdf /app/work/pages_raw.txt，
#    再按页插入 "=== page N ===" 标记得到 /app/work/pages.txt
python3 scripts/heading_tree.py  --pages /app/work/pages.txt \
        [--sizes /app/work/sizes.tsv] --out /app/work
python3 scripts/refs_parse.py    --pages /app/work/pages.txt \
        --headings /app/work/headings.json --out /app/work
python3 scripts/structure_report.py --pages /app/work/pages.txt \
        --headings /app/work/headings.json --toc /app/work/toc.json \
        --refs /app/work/references.json \
        --case /input/case.json --out /app/output
# 3. 阅读 JSON，必要时把 headings/toc/references 一并复制到 /app/output
```

## 输出物说明

| 文件 | 产生者 | 内容 |
|---|---|---|
| `headings.json` | heading_tree.py | 嵌套标题树 + flat 列表 + `inconsistencies` |
| `toc.json` | heading_tree.py | 扁平目录：anchor / number / title / level / page |
| `references.json` | refs_parse.py | 每条参考文献：raw/label/authors/year/title/venue/volume/issue/pages/doi + parse_status + confidence + reasons |
| `structure_report.json` | structure_report.py | 题注索引、正文提及、双向缺口、计数、标题不一致 |
| `result.json` | structure_report.py | 契约化汇总：case_id、status、按 output_contract 的 outputs、findings、sources、uncertainty、change_record |

## 方法要点

- **标题检测**：编号正则（多级 `1.1.1`、附录 `Appendix A` / `A.1`）→ 已知词表
  （Abstract/References/Acknowledgments…）→ ALL-CAPS 短行（大写比 ≥0.85）→
  字号提示短行（≥1.2×正文字号，仅提供 --sizes 时）。编号标题按"最长编号前缀"
  挂到正确父节点。
- **不一致只报告不修复**：`numbering_gap`（如 1.1 后直接 1.3）、`missing_parent`
  （存在 2.2.1 但无 2.2）、`level_jump`、`duplicate_number`。
- **参考文献**：先从标题树定位 References 区（取最后一次出现，其后同级标题截断），
  失败则回退"文末编号列表"。条目切分支持混排：方括号起始 / 姓-逗号起始且含
  (年份) / 异常起始字符。字段抽取失败一律置 null；`parse_status` ∈
  parsed / partial / raw，raw 条目原文保留，**绝不臆造字段**。
- **题注核对**：行首 `Fig(ure)?.? n` / `Table n` 视为题注；全文其它出现视为
  正文提及；双向求差集。

## 异常与限制

| 情形 | 行为 |
|---|---|
| 无编号标题风格未知（非词表、非全大写、无字号提示） | 漏检；在 uncertainty 中声明，可补 --sizes |
| 两种参考文献风格混排 | 支持，style_hint=mixed；条目切分依赖启发式，个别粘连条目降为 partial/raw |
| 非英语标题/姓名（含重音字符、CJK） | 作者正则只认拉丁字母；识别失败 → raw，不臆造 |
| 缺页锚点（文本无页标记） | 全部归入 page 1 并在 warnings 中声明 |
| 换行恰好以 "Fig. n" 开头 | 会被误当题注；已在 uncertainty 中声明 |
| 只有 PDF、无文本层 | 本 skill 不做 OCR；需先由其它工具产出文本层 |

## 最小示例

`examples/minimal/` 内含**完全合成的** 4 页迷你论文（非真实研究），已实际
跑通全流程并提交真实输出：

```bash
cd examples/minimal
sh run.sh        # 重跑 heading_tree → refs_parse → structure_report
```

预期：9 个标题、正确嵌套；`2.2` 缺失而 `2.2.1` 存在被标记
（missing_parent + level_jump）；`Table 1` 有题注无正文引用、`Fig. 2` 有正文
引用无题注，双向各标记 1 条；6 条参考文献中 5 条 parsed、1 条损坏条目
`parse_status: raw` 且字段全 null。详见 `examples/minimal/README.md`。

**声明**：示例论文、作者、期刊、DOI 均为虚构，仅用于冒烟测试。
