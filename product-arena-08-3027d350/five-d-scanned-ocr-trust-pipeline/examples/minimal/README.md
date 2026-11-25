# 最小示例（合成示例：非正式案例、非真实论文）

本示例的全部输入均为人工合成：`scan_like.pdf` 由 `inputs/make_scan_pdf.py`
用纯标准库生成（1 页、整页 ASCIIHexDecode DeviceGray 位图、无文字，整个文件
为纯 ASCII/UTF-8 文本）；`synthetic_ocr.txt` 为手工编造的 3 页 OCR 文本，内含
13 处典型 OCR 混淆错误与 2 处多解嫌疑词。**两文件页数故意不一致（PDF 1 页
vs OCR 3 页）**，用于触发 unknown 页类、partial 状态等诚实路径。
`outputs/` 下全部产物均为三个脚本在本机真实运行的结果，非手写冒充。

## 复现命令

```bash
SK=../..                      # skill 根目录
cd examples/minimal

# 0. 重新生成输入 PDF（可选；产物即 inputs/scan_like.pdf）
python3 inputs/make_scan_pdf.py

# 1. 扫描页判定 + OCR 移交清单（退出码 0）
python3 $SK/scripts/scan_detect.py --pdf inputs/scan_like.pdf --outdir outputs

# 2. OCR 后处理（真实评测中 ocr-tool 产生 inputs/synthetic_ocr.txt 的角色；退出码 0）
python3 $SK/scripts/ocr_postcheck.py --ocr inputs/synthetic_ocr.txt --outdir outputs

# 3. 可信台账 + 契约感知 result.json（本例退出码 2，见下）
python3 $SK/scripts/trust_ledger.py \
  --scan outputs/scan_report.json --post outputs/postcheck.json \
  --ocr inputs/synthetic_ocr.txt --corrected outputs/corrected.txt \
  --case inputs/case.json --workdir outputs/work --outdir outputs
```

## 目检结论（作者实际核对）

1. **扫描判定**：`outputs/scan_report.json` 将第 1 页判为 `scanned`
   （text_chars_approx=0、图像 400×300=120000 像素 ≥ 阈值 100000、
   fullpage_image=true）；PyMuPDF 与 pdftotext 交叉验证均 agree=true。
   `outputs/handoff_ocr.json` 含该页，suggest_dpi=300、
   suggest_preprocess=["deskew","binarize"]。

2. **保守纠错**：13 处高置信错误全部被唯一解规则命中并改正，
   逐条核对 `outputs/corrected.txt` 无误改：
   `5ample→sample`、`chernical→chemical`、`1nfrared→infrared`、
   `detecti0n→detection`、`rnicrowave→microwave`、`c1uster→cluster`、
   `vvave→wave`、`0xidation→oxidation`、`comparis0n→comparison`、
   `resu1ts→results`、`2O25→2025`（numeric_context 规则）、
   `rnethod→method`、`5pectra→spectra`。
   corrected.txt 与原文逐字符 diff，差异与 postcheck.json 的 corrections
   台账一一对应，无台账外改动。

3. **多解保留**：`ha1l`（候选 hall/hail）与 `wa1l`（候选 wall/wail）进
   suspects 列表，corrected.txt 中**原样保留未改**。

4. **台账分级**：第 1 页 scanned 且修正率 11.11% ≥ 2% → low；
   第 2 页 unknown（OCR 页超出 PDF 页数）已 OCR 且修正率 0% → medium；
   第 3 页 unknown 且修正率 14.89% ≥ 2% → low。
   分布 high:0 / medium:1 / low:2 / illegible:0。每页 verbatim/corrected
   双写文件在 `outputs/work/pages/`。

5. **诚实路径（本例真实触发）**：因 OCR 页数（3）≠ PDF 页数（1）且存在
   unknown 页类，`outputs/result.json` 的 status=partial，uncertainty 如实
   说明页数不一致与 unknown 降级，exit code=2。

另在开发自测中（未随包附产物）真实触发过：截尾 PDF → 页类 unknown +
退出码 2；无 PyMuPDF/pdftotext → 引擎降级记 unavailable；空 OCR 文件 →
postcheck 标 partial(ocr_empty)；scanned 页未 OCR → 台账 illegible；
born_digital 页（PyMuPDF 现造）→ 台账 high。
