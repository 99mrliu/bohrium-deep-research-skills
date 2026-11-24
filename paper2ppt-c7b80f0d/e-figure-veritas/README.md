# ppt-figure-veritas

论文转学术 PPT 的图表资产保真 Skill：每张入 deck 的图真实存在、出处明确、
种类合法；示意图永远不得充当实验证据；重绘只允许来自机器可读数据且数值
零漂移可核验。

## 依赖与版本

- Python ≥ 3.9（stdlib 优先；开发验证环境 3.12）
- 可选依赖（全部软导入，缺失走降级/honest tool_missing，不崩溃）：
  - `pymupdf`（位图抽取、整页渲染、PDF 页数）→ 降级 `pdfimages`/`pypdf`
  - `python-pptx`（构建与测量 pptx）→ 缺失时 build_deck exit 3 诚实报错
  - `matplotlib`（确定性重绘、合成输入生成）→ 缺失时 chart_redraw exit 3
  - `pypdf`（文本/PDF 页数兜底）
- 外部工具（subprocess，缺失自动降级）：
  - `pdftotext`（文本提取首选）→ pymupdf → pypdf
  - `soffice`（LibreOffice，渲染 pptx→pdf）；macOS 路径
    `/Applications/LibreOffice.app/Contents/MacOS/soffice`；并发必须加
    `-env:UserInstallation=file:///tmp/lo-<key>`
  - `pdftoppm`（pdf→png 预览）

安装：`pip install pymupdf python-pptx matplotlib pypdf`（均可选）。

## 调用步骤

```bash
# 0) 生成本地合成输入（示例；平台案例在 /input）
python3 examples/make_synthetic_case.py --out-dir runs/b/input

# 1) 收割：位图 + caption + 引用绑定
python3 scripts/fig_harvest.py runs/b/input/paper.pdf \
  --out-dir runs/b/work/figs --manifest runs/b/work/figure_manifest.json
# 2) 分类门禁
python3 scripts/fig_classify.py runs/b/work/figure_manifest.json \
  --report runs/b/work/classify_report.json
# 3) 重绘（spec.json 由 Agent 依据 data.csv 逐值撰写）
python3 scripts/chart_redraw.py runs/b/work/spec_fig1.json \
  --data runs/b/input/data.csv --out runs/b/work/figs/redrawn_fig1.png
# 4) 零漂移核验（mismatch>0 → exit 1）
python3 scripts/redraw_verify.py runs/b/work/spec_fig1.json \
  --data runs/b/input/data.csv --report runs/b/work/redraw_report.json
# 5) 绑定门禁（error>0 → exit 1）
python3 scripts/fig_binding_lint.py runs/b/work/deck.json \
  runs/b/work/figure_manifest.json --report runs/b/work/binding_report.json
# 6) 构建可编辑 pptx
python3 scripts/build_deck.py runs/b/work/deck.json \
  --template runs/b/input/target-template.pptx \
  --fig-dir runs/b/work/figs --manifest runs/b/work/figure_manifest.json \
  --out runs/b/output/presentation.pptx --report runs/b/work/build_report.json
# 7) 渲染 + 汇总 result.json
python3 scripts/make_result.py --case runs/b/input/case.json \
  --task runs/b/input/task.md --deck runs/b/work/deck.json \
  --pptx runs/b/output/presentation.pptx \
  --manifest runs/b/work/figure_manifest.json \
  --classify-report runs/b/work/classify_report.json \
  --redraw-report runs/b/work/redraw_report.json \
  --binding-report runs/b/work/binding_report.json \
  --render --render-dir runs/b/output --work-key b \
  --out runs/b/output/result.json
```

## 适用范围

- 论文 PDF（文本层存在）→ 学术汇报 PPT，且评测/受众要求图表可追溯。
- 重绘仅覆盖 line/bar 两类确定性图表；更复杂图请用 original-crop。

## 限制

- 扫描件无文本层时 caption 索引为空，只能 honest partial（见
  references/exceptions.md）。
- 整页渲染兜底（page-render）不裁剪到图区域，仅作存在性证据。
- redraw_verify 容差为 0 且不支持单位换算。
- fig_classify 为规则法，unknown 需 Agent 裁决。

## 失败处理

所有脚本：`--help` 可用；输入错误 exit 2 + 具体 stderr；关键依赖缺失
exit 3 + `tool_missing`；门禁失败 exit 1 + 报告明细。任何脚本不因缺依赖
直接崩溃。

## 维护

- bundle 内无二进制；合成输入由 `examples/make_synthetic_case.py` 现场生成。
- 修改规则（关键词、provenance 集合）时同步更新 references/ 三份文档。
- 版本：v1（对应挑战 ppt-c7b80f0d，方向 B）。
