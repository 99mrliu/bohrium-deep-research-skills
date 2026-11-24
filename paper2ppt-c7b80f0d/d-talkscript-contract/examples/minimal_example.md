# 最小调用示例

> **合成示例，非平台案例结果。** 以下输入由 `make_synthetic_case.py` 现场生成，论文、
> 数据、机构全部虚构（"Synth et al." / fictional QX-7）。真实数值来自本仓库
> 开发机上的实际运行（退出码均为真实返回值）。

## 1. 生成合成输入

```bash
python3 examples/make_synthetic_case.py --out runs/a/input
# exit=0；生成 paper.pdf(5 页) / target-template.pptx / data.csv / case.json / task.md
```

## 2. 证据扫描

```bash
python3 scripts/evidence_scan.py runs/a/input/paper.pdf --out runs/a/work/evidence.json
# exit=0；stdout: engine=pdftotext pages=5 figures=1 tables=1 anchors=11
```

## 3. 讲稿切拍校验

beats.json 共 7 拍（schema 见 references/talkscript-format.md）：

```bash
python3 scripts/beat_cut.py runs/a/work/beats.json --evidence runs/a/work/evidence.json \
    --minutes 10 --max-slides 8 --report runs/a/work/beat_report.json
# exit=0；stdout: beat_cut: PASS beats=7 total=565s/600s
```

## 4. 逐拍幂等投影

```bash
for i in 0 1 2 3 4 5 6; do
  python3 scripts/slide_forge.py runs/a/output/presentation.pptx \
    --beat runs/a/work/beats.json#$i --template runs/a/input/target-template.pptx \
    --evidence runs/a/work/evidence.json --paper runs/a/input/paper.pdf \
    --log runs/a/work/forge_log.json
done
# 每次 exit=0；slide 4: figure=rendered（pymupdf 裁出 Figure 1 区域）
# 重跑同一拍：元素数不变（forge_ 前缀管理，幂等）
```

## 5. 备注门禁 + 彩排

```bash
python3 scripts/notes_lint.py runs/a/output/presentation.pptx --minutes 10 \
    --report runs/a/work/notes_report.json
# exit=0；逐页 jaccard 0.07–0.14，总口播 597s/600s，PASS
# （负向测试：把备注改成页面文字复读后重跑 → 14 errors，exit=1，jaccard=1.00）

python3 scripts/rehearse.py runs/a/output/presentation.pptx --cpm 240 --wpm 150 \
    --minutes 10 --report runs/a/work/rehearsal.json
# exit=0；total=597s，无超速页、无过薄页
```

## 6. 渲染 + 组装 result.json

```bash
soffice -env:UserInstallation=file:///tmp/lo-a --headless --convert-to pdf \
    --outdir runs/a/output runs/a/output/presentation.pptx   # exit=0
pdftoppm -png -r 100 runs/a/output/presentation.pdf runs/a/output/preview  # exit=0

python3 scripts/make_result.py --case runs/a/input/case.json --task runs/a/input/task.md \
    --deck runs/a/output/presentation.pptx --pdf runs/a/output/presentation.pdf \
    --previews "runs/a/output/preview-*.png" --beats runs/a/work/beats.json \
    --evidence runs/a/work/evidence.json --notes-report runs/a/work/notes_report.json \
    --rehearsal runs/a/work/rehearsal.json \
    --change-records runs/a/work/change_records.json --out runs/a/output/result.json
# exit=0；stdout: status=success checks=5/5 pass sources_verified=11/11 contract_fields=7/7
```

## 7. 实测 result.json 摘要（合成案例）

- `status`: success；`exceptions`: []
- `editable_source`: slides=7, notes_present=true
- `export_artifact`: rendered=true, pages=7, previews=7
- `compliance_checks`（actual 全为实测）：
  slide_count 7≤8 ✓ / export_page_match 7=7 ✓ / placeholder_free 0 ✓ /
  evidence_coverage 1.0（11/11 条 quote 逐字命中论文提取文本）✓ /
  notes_coverage 7/7 ✓
- 示例 source（slide 5）：
  `{kind:"text", ref:"0.42 W/(m·K)", locator:"p.4",
    quote:"conductivity dropped to 0.42 W/(m·K) at 50 K, an improvement of 37 %",
    quote_verbatim_verified:true}`
