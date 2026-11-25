# minimal 示例（**合成示例**：非正式案例、非真实论文）

`inputs/sample.pdf` 由 `inputs/make_sample.py` **纯标准库**生成（不联网、不 pip）：
3 页单栏 US Letter，Helvetica / Helvetica-Bold，20/14/13/12/11/10/9pt 多字号。
PDF 仅含 ASCII 字节（可通过 UTF-8 解码检查），且能被 pymupdf 与 pdftotext 真实读取。

内容设计（用于验证流水线各环节）：

- 题名（20pt 粗体，两行）、作者行、机构行 → front_matter；
- Abstract（13pt 粗体）→ 关键词标题；
- `1 Introduction` / `1.1 Background` / `2 Methods` / `2.1 Data` / `2.2 Setup` /
  `3 Results` → 编号层级（1.1 挂 1 下，2.1/2.2 挂 2 下）；
- 正文引用 `Figure 1`、`Figure 3`、`Table 1`；题注行 `Figure 1: ...`、
  `Table 1: ...`（9pt）；**Figure 3 故意无题注**，供 audit 双向差异命中；
- `References` + `[1]..[4]` 四条（`[2]` 跨行，验证续行合并）；
- `Acknowledgments` 收尾。

## 复现命令

在 skill 根目录执行（命令与 SKILL.md 第 7 节一致）：

```bash
python3 examples/minimal/inputs/make_sample.py   # 重新生成 inputs/sample.pdf 与 inputs/case.json
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

`outputs/` 下全部为上述命令**真实本地运行**的产物（退出码 0/0/0/0），非手写。

## 目检结论（实际逐项检查过）

1. **引擎真实性**：`pdftotext inputs/sample.pdf -` 与 `pymupdf.open()` 均读出
   3 页文本；extract 报告 `engine=pymupdf, mode=styled, lines=38, pages=3`。
2. **层级树正确**：document_tree.json 中 `1.1 Background` 是 `1 Introduction`
   的 children；`2.1 Data`、`2.2 Setup` 是 `2 Methods` 的 children；
   Abstract/References/Acknowledgments 为 L1 特殊节点；文档题名（20pt 两行）
   **未**进入树，而是归入 front_matter 并填入 `title` 字段。共 9 个标题节点，
   `heading_candidates` 为空。
3. **区间锚点**：front_matter (p1,y30.6)→(p1,y208.15)；body (p1,y233.42)→
   (p2,y337.25)；references (p3,y37.02)→(p3,y142.15)；acknowledgments
   (p3,y167.42)→(p3,y196.55)。锚点与原文行位置一致。
4. **参考文献切分**：切成 4 条，`[2]` 的跨行续行正确合并进 raw_text；
   first_author_guess = Smith/Jones/Brown/Miller，year_guess =
   2020/2021/2019/2022；leftovers 为空；`char_accounting.balanced=true`
   （无字符丢失）。
5. **图表审计命中**：`figure.cited=[1,3]`，`captioned=[1]`，
   `cited_not_captioned=[3]`（Figure 3 被引用但无题注，按设计要求命中），
   `captioned_not_cited=[]`；table 双向一致；issue_count=1。
6. **覆盖率**：树区间字符覆盖率 1.0。
7. **result.json**：`status=success`，`case_id=synth-minimal-001`，
   契约 6 字段（document_tree/section_spans/references/reference_count/
   structure_audit/engine）全部非空。

## 降级路径自测（非 outputs 产物，另在临时目录真实触发）

- `--engine bbox`：mode=geometry，extract 退出码 2；build 报告
  "字号信号不可用，仅编号+关键词"，status=partial；仍检出 9 标题、4 条文献、
  Figure 3 命中；result.json status=partial 并在 uncertainty 写明降级原因。
- `--engine layout`：mode=text（y0=行序，已标注），结果同上，status=partial。
