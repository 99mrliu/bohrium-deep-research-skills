# 合成示例运行说明（合成示例，非正式案例结果）

本目录为**合成示例输入**：`case.json`（含 case_id 与 output_contract 字段清单）、`draft_v1.md` / `draft_v2.md`（两版章节稿，含标题/列表/3 行表格/一处【待申请人确认】）、`bad_result.json`（故意缺字段的陷阱件）。运行产物一律写到 bundle 之外的 `example-runs/grant-d-render-forge/`（下文记为 `$RUN`），bundle 内不放任何二进制产物。

以下命令与输出均为本机（macOS arm64，Python 3.12.14）**真实运行**记录，退出码如实标注。

## 0. 本机工具探测实况

- `soffice`：PATH 中无，但存在于 `/Applications/LibreOffice.app/Contents/MacOS/soffice`（LibreOffice 26.2.5.2），make_previews.py 的候选路径命中 → **可用**。
- `pdftoppm`：PATH 中可用（poppler 25.01.0；另 `/opt/homebrew/bin/pdftoppm` 为 poppler 26.08.0）→ **可用**。
- 因此本机示例为**真实渲染**（status=ok），非降级；降级路径用环境变量模拟工具缺失另行验证（见第 5 节）。

## 1. md2docx：生成 docx 并复读校验（退出码 0）

```
$ python3 scripts/md2docx.py examples/draft_v2.md $RUN/draft_v2.docx
docx 生成并校验通过: .../example-runs/grant-d-render-forge/draft_v2.docx
  部件 [Content_Types].xml                     563 字节
  部件 _rels/.rels                             301 字节
  部件 word/_rels/document.xml.rels            286 字节
  部件 word/document.xml                      4307 字节
  部件 word/styles.xml                        1658 字节
（退出码 0）
```

确定性验证：换路径再生成一次，`cmp` 比较**字节一致**（zip 时间戳固定 1980-01-01）。失败路径验证：`python3 scripts/md2docx.py /nonexistent.md /tmp/x.docx` → 打印"错误：无法读取输入文件"，退出码 1。

## 2. make_previews：真实渲染（本机 status=ok，退出码 0）

```
$ python3 scripts/make_previews.py $RUN/draft_v2.docx --outdir $RUN/previews
PDF 已生成: .../previews/draft_v2.pdf（112902 字节）
PNG 已生成 1 页: draft_v2-1.png
preview_status.json 已写出，status=ok
（退出码 0）
```

`preview_status.json` 关键内容（真实）：`status: "ok"`；`tools.soffice: "/Applications/LibreOffice.app/Contents/MacOS/soffice"`；`tools.pdftoppm: ".../poppler/bin/pdftoppm"`；`products.pdf.bytes: 112902`；`products.pngs[0].bytes: 139954`。PNG 经目检为真实排版页（标题加粗、表格边框、列表项目符号、中文宋体/黑体正常）。

## 3. version_diff：生成修改记录（退出码 0）

```
$ python3 scripts/version_diff.py examples/draft_v1.md examples/draft_v2.md -o $RUN/change_record.md
change_record 已写出: .../change_record.md（新增 0 行 / 删除 0 行 / 修改 9 行）
（退出码 0）
```

change_record.md 含：变更统计表（新增 0/删除 0/修改 9）；按小节归组表（研究内容 4 行、技术路线 3 行、可行性说明 1 行、标题 1 行）；人工确认项 `- [ ] 【待申请人确认：最优含水率±2% 的具体取值】（新版 第 18 行）`；unified diff（上下文 2 行）。二次运行 `cmp` **字节一致**（确定性）。

## 4. assemble_result：装配 + 校验 + 陷阱

装配（全部合同字段落实，退出码 0）：

```
$ python3 scripts/assemble_result.py --case examples/case.json --outdir $RUN \
    --status partial --reason "…待确认，故为 partial。" \
    --source "（合成示例）材料中已有试验方案" \
    --uncertainty "试样含水率具体取值缺失，母稿以【待申请人确认】占位。" \
    --deliverable draft_v1.md --deliverable draft_v2.md --deliverable draft_v2.docx \
    --deliverable previews/draft_v2.pdf --deliverable previews/draft_v2-1.png \
    --deliverable previews/preview_status.json --deliverable change_record.md \
    --set change_records='"change_record.md"' \
    --set element_mapping='{"研究内容":"draft_v2.md#研究内容","技术路线":"draft_v2.md#技术路线","研究基础与可行性":"draft_v2.md#可行性说明"}'
result.json 已装配: .../result.json（status=partial，missing=无）
（退出码 0）
```

校验通过（退出码 0）：

```
$ python3 scripts/assemble_result.py --validate --case examples/case.json --result $RUN/result.json --outdir $RUN
合同符合性校验通过: .../result.json
（退出码 0）
```

幂等验证：同样参数二次装配，`cmp` 比较 result.json **字节一致**。

占位路径验证：装配时省略 `--set` 字段，缺失合同字段被填 `【缺失：待补充】` 并列入 `missing`（status=partial），再 --validate 报 5 项"仍是占位"退出码 1。

**陷阱件**（`examples/bad_result.json`：status 写成非法值 "done"、缺 reason/sources/uncertainty/change_records/element_mapping、deliverable 指向不存在文件）：

```
$ python3 scripts/assemble_result.py --validate --case examples/case.json --result examples/bad_result.json --outdir $RUN
合同符合性校验不通过（10 项）：
  - status 非法: 'done'（须为 success/partial/unable_to_determine/refused 之一）
  - 缺少基础字段: reason
  - 缺少基础字段: sources
  - 缺少基础字段: uncertainty
  - 缺少 output_contract 字段: reason
  - 缺少 output_contract 字段: sources
  - 缺少 output_contract 字段: uncertainty
  - 缺少 output_contract 字段: change_records
  - 缺少 output_contract 字段: element_mapping
  - deliverable 文件不存在: not_exist_preview.pdf
（退出码 1）
```

## 5. 降级路径验证（环境变量模拟工具缺失，非伪造预览）

本机工具齐全，故用 `MAKE_PREVIEWS_SOFFICE=none` / `MAKE_PREVIEWS_PDFTOPPM=none` 模拟缺失，真实走降级代码路径：

```
$ MAKE_PREVIEWS_PDFTOPPM=none python3 scripts/make_previews.py $RUN/draft_v2.docx --outdir /tmp/deg
PDF 已生成: /tmp/deg/draft_v2.pdf（112902 字节）
降级：未找到 pdftoppm（poppler），无法生成 PNG 页面预览。
preview_status.json 已写出，status=degraded
（退出码 0；目录中只有 pdf 与 preview_status.json，无任何假 PNG）

$ MAKE_PREVIEWS_PDFTOPPM=none python3 scripts/make_previews.py $RUN/draft_v2.docx --outdir /tmp/deg2 --strict
（同上输出）+ 严格模式：降级即失败。
（退出码 1）

$ MAKE_PREVIEWS_SOFFICE=none MAKE_PREVIEWS_PDFTOPPM=none python3 scripts/make_previews.py $RUN/draft_v2.docx --outdir /tmp/deg3
降级：未找到 soffice（LibreOffice），无法生成 PDF 预览。
降级：未找到 pdftoppm（poppler），无法生成 PNG 页面预览。
（退出码 0；目录中只有 preview_status.json：missing_tools=[soffice, pdftoppm]、missing_products=[pdf, png]、products 全空）
```

## 6. 本机实际产物清单（`$RUN`，全部真实生成）

| 产物 | 字节数 | 来源 |
| --- | --- | --- |
| draft_v1.md / draft_v2.md | 931 / 1212 | 合成母稿拷贝 |
| draft_v2.docx | 2866 | md2docx.py（校验通过） |
| previews/draft_v2.pdf | 112902 | soffice 真实转换 |
| previews/draft_v2-1.png | 139954 | pdftoppm -png -r 110 真实渲染 |
| previews/preview_status.json | 548 | make_previews.py（status=ok） |
| change_record.md | 2815 | version_diff.py |
| result.json | — | assemble_result.py（--validate 通过） |
