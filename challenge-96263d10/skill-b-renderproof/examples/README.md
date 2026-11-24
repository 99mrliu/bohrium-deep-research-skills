# 最小调用示例（合成示例，非正式案件结果）

演示渲染证据链的两段。**全部输入由 make_fixture.py 现场合成（手写最小 PDF
与最小 DOCX）；expected/ 下为合成示例的真实运行产物，仅示意接口。**

## 运行

```bash
python3 examples/make_fixture.py
# 第一段：直接测量手写 PDF（含一条诚实的字体 FAIL）
python3 scripts/pdf_measure.py examples/work/sample.pdf --out examples/work/measurements.json
python3 scripts/render_verdict.py examples/work/spec.json examples/work/measurements.json \
    --json examples/work/verdicts_fail.json --md examples/work/ledger_fail.md      # 退出码 1
python3 scripts/render_verdict.py examples/work/spec_round2.json examples/work/measurements.json \
    --json examples/work/verdicts_pass.json --md examples/work/ledger_pass.md      # 退出码 0
# 第二段：完整渲染链 DOCX -> PDF -> PNG -> 测量 -> 裁决
python3 scripts/render.py examples/work/sample.docx --outdir examples/work/preview_docx
python3 scripts/pdf_measure.py examples/work/preview_docx/sample.pdf --out examples/work/measurements_docx.json
python3 scripts/render_verdict.py examples/work/spec_docx.json examples/work/measurements_docx.json \
    --json examples/work/verdicts_docx.json --md examples/work/ledger_docx.md
```

## 本示例实测结果（2026-11-24 真实运行，本机 LibreOffice + poppler）

- 第一段：sample.pdf 测得 A4、左边距 2.544cm、单栏；Helvetica 属 base-14 未内嵌，
  对 `fonts.embedded_all: true` 的规格判 FAIL（退出码 1）——演示"裁决跟规格走"，
  第二轮规格改为 `false` 后 6 项全 PASS。
- 第二段：sample.docx 经 LibreOffice 真实渲染出 PDF + 110dpi PNG（已目检：
  A4 页面、文字位置符合页边距声明）；实测 21.001×29.7cm、左边距 2.544cm、
  上边距 3.091cm（字形框含 ascent，容差内）、单栏、Carlito 内嵌，5 项全 PASS。
- 降级路径实测：PATH 中去掉 poppler 后几何记 UNMEASURED 但 MediaBox/字体
  检查照常（measurements_nopdftotext.json，未入 expected）。

expected/ 内容：measurements*.json、verdicts_*.json、ledger_*.md、render_status.json。
渲染 PNG 为二进制、不入包；正式运行时按契约写入 /app/output/preview/。
