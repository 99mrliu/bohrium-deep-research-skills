# 合成示例（EXAMPLE-NOT-A-TEST-CASE）

**这是合成示例，非正式案例结果。** 所有输入数据均为虚构，仅用于演示
editable-deliverable-forge 的接口与完整流程。

## 目录

```
examples/
├── input/
│   ├── case.json        # 合成案例（case_id="EXAMPLE-NOT-A-TEST-CASE"，output_contract 5 键）
│   ├── task.md          # 合成任务说明
│   ├── draft.md         # 合成成稿（含标题/列表/表格/粗体/斜体，已注明合成）
│   └── edit_plan.json   # 3 条合成修改（第 3 条故意未命中，演示 misses 如实记录）
└── output/              # 真实运行产生的【文本】产物（二进制不随 bundle 分发，见下）
    ├── forge_report.md      # 验证报告：zip/XML 良构/段落表格计数/修订计数/保留率
    ├── review_record.csv    # 逐条复核台账（"接受状态"列留空供人工填写）
    ├── result.json          # 装配结果：契约 5 键 + 产物清单 + round_trip + preview_status
    └── preview.html         # HTML 兜底预览（用无渲染器 PATH 重跑 render 生成，演示降级链末端）
```

## 为什么 output/ 里没有 docx / pdf / png

bundle 规则要求包内**零二进制**。`deliverable.docx`、`deliverable_tracked.docx`、
`preview.pdf`、`preview-*.png` 是真实的运行时产物，构建本 bundle 时已在本机真实生成、
验证（见 forge_report.md 与 result.json 中记录的字节数与 sha256），随后移出 bundle。

`.gitignore` 风格说明：若把本目录纳入版本管理，应忽略——

```gitignore
examples/output/*.docx
examples/output/*.pdf
examples/output/*.png
```

注意：DOCX 是带时间戳的 zip，逐字节重建不保证相同 sha256；文本产物
（forge_report.md / review_record.csv / result.json）中的 sha256 是**构建当时**
真实文件的哈希，用于说明验证流程而非逐字节复现。

## 重建全部产物（一条命令）

```bash
python3 ../../scripts/docx_forge.py run \
  --case input/case.json \
  --md input/draft.md \
  --edit-plan input/edit_plan.json \
  --outdir output
# 或在 bundle 根目录：
python3 scripts/docx_forge.py run --case examples/input/case.json \
  --md examples/input/draft.md --edit-plan examples/input/edit_plan.json \
  --outdir examples/output
```

运行后 output/ 会多出 `deliverable.docx`、`deliverable_tracked.docx`，并按本机渲染
能力产出 `preview.pdf` / `preview-*.png`（命中 soffice/pandoc/textutil+cupsfilter/
qlmanage 之一）或重新生成 `preview.html`（全部不可用时）。

## 本机实际运行记录（构建时）

- 渲染探测：soffice / pandoc 不存在 → 命中 **textutil+cupsfilter** 产出真实 PDF，
  再由 **pdftoppm** 转 PNG（preview_status = `rendered_pdf_png`，PDF/PNG 均通过
  魔数校验）。
- round-trip 保留率：干净版与修订版均 **1.0000**（阈值 0.99）。
- 修订：3 条 edit，命中 2（w:ins=2 / w:del=2，author=skill-agent），未命中 1
  （如实写入 misses 与 result.json 的 uncertainty）。
- 降级链末端验证：以仅含 python3 的 PATH 重跑 `render`，正确落到 `preview.html`
  （本目录中的 preview.html 即该次真实运行的产物，非手工编写）。
