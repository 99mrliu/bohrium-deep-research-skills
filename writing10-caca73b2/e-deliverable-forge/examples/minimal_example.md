# 最小可运行示例(SYNTH-EXAMPLE-001)

**本示例为合成示例:输入稿件、全部数据与结论均为虚构,仅用于演示交付流程,不构成任何科学主张。** 文中所有命令与输出均为本地真实运行结果(macOS, Python 3, 仅标准库),无任何伪造。

## 目录

- `input/case.json` — 案例定义(case_id `SYNTH-EXAMPLE-001`,output_contract 5 键)
- `input/task.md` — 任务说明
- `input/manuscript.md` — 合成"结果与讨论"定稿(图1、图2、表1,题注与正文引用齐全,审计 PASS)
- `input/manuscript_broken.md` — 埋雷变体(**表1 有题注但正文从未引用;图编号 1→3 跳号**),用于负向测试
- `output/` — 全部真实产物(见下)

## 1. 负向测试:审计埋雷变体

```bash
$ python3 scripts/xref_check.py --input examples/input/manuscript_broken.md \
    --report-md examples/output/xref_report.md --report-json examples/output/xref_report.json
- 审计结果: **FAIL**(错误 2 项, 警告 0 项)
$ echo $?
1
```

`output/xref_report.md` 如实列出两个被埋入的问题:

```text
- 图类编号不连续: 实际为 [1, 3], 应为 [1, 2]
- 表1 (题注在第13行) 从未在正文中被引用
```

## 2. 修复(两步,均记入 change_log)

**步骤 1(编辑性修复)**:补上 表1 的正文引用("汇总于**表1**"),不改任何数值。
**步骤 2(机械重编号)**:

```bash
$ python3 scripts/xref_check.py --input manuscript_cited.md \
    --fix-renumber examples/output/manuscript_fixed.md --moves examples/output/moves.json
fix-renumber: wrote examples/output/manuscript_fixed.md; residual errors after fix: 0
```

`output/moves.json` 记录映射 `{"figure": {"3": 2}}`;题注与 3 处正文引用一并改写。

## 3. 复审修复稿

```bash
$ python3 scripts/xref_check.py --input examples/output/manuscript_fixed.md \
    --report-md examples/output/xref_report_fixed.md --report-json examples/output/xref_report_fixed.json
- 审计结果: **PASS**(错误 0 项, 警告 0 项)
$ echo $?
0
```

## 4. 构建可编辑 docx(本地真实生成并通过自验)

```bash
$ python3 scripts/build_docx.py --input examples/output/manuscript_fixed.md \
    --out manuscript.docx --manifest examples/output/build_manifest.json
docx built: manuscript.docx
self-verification summary:
  zip integrity: OK (testzip passed)
  required parts: [Content_Types].xml, _rels/.rels, word/document.xml, word/styles.xml
  document.xml: parsed by xml.etree, 33 paragraph(s), 1 table(s)
  size: 3353 bytes
  sha256: 0636c208098cb37b0e70c7903b01590a1585ea3013a1c576ed4f93a0d636bc78
$ echo $?
0
$ unzip -l manuscript.docx
  Length  Name
---------  ----
      557  [Content_Types].xml
      298  _rels/.rels
      283  word/_rels/document.xml.rels
     6651  word/document.xml
     1079  word/styles.xml
```

**manuscript.docx 在本地真实生成并通过上述自验;但因平台只收 UTF-8 文本文件,二进制 docx 不随 bundle 提交,此处提交 SVG 预览(`output/preview-1.svg`)与构建清单(`output/build_manifest.json`,含 docx 的 sha256 与字节数)为证。** 构建是确定性的(zip 条目固定时间戳):同输入两次构建 sha256 完全一致,可用同一脚本复现并核对。

## 5. 生成 SVG 渲染预览

```bash
$ python3 scripts/render_preview.py --input examples/output/manuscript_fixed.md --out-dir examples/output
rendered 1 page(s) from examples/output/manuscript_fixed.md -> preview-1.svg
$ echo $?
0
```

`output/preview-1.svg` 经 `xml.etree` 解析验证为合法 SVG(40 个 text、17 个 rect 元素,题注居中、表格网格线、页码齐全);重渲染产物与提交版逐字节一致(确定性)。

## 6. 组装并校验 result.json

```bash
$ python3 scripts/result_contract.py init --case-json examples/input/case.json --out examples/output/result.json
init OK: wrote examples/output/result.json with case_id='SYNTH-EXAMPLE-001' and 5 contract key(s): deliverable, preserved_facts, evidence_map, change_log, preview_files
# …按契约填写后…
$ python3 scripts/result_contract.py check --case-json examples/input/case.json --result examples/output/result.json
PASS: case_id verbatim; 5 contract key(s) present; status=success; sources/uncertainty present.
$ echo $?
0
```

最终 `output/result.json`:`case_id` 原样、output_contract 5 键齐全、`status=success`,并在 `uncertainty` 中如实声明"SVG 预览为排版近似、docx 未随 bundle 提交可复现核对"。

## 7. 降级路径演示(不交付,仅验证)

以空稿件触发构建失败,脚本自动写出 `manuscript.md` + `manuscript.html` 降级产物、清单记 `status: fallback`、退出码 2:

```bash
$ python3 scripts/build_docx.py --input empty.md --out manuscript.docx --manifest manifest.json
ERROR: docx build/verify failed: no content blocks parsed from input
fallback written: manuscript.md, manuscript.html; manifest: manifest.json
$ echo $?
2
```
