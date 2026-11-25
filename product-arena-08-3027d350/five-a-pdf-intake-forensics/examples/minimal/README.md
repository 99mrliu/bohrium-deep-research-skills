# examples/minimal — 合成示例（非正式案例、非真实论文）

三个 PDF 全部由 `inputs/make_samples.py` 用**纯 Python 标准库**手写生成（经典 xref 表、无对象流、纯 ASCII 字节，满足 bundle 全 UTF-8 约束），可被 pdftotext / PyMuPDF 真实读取：

| 文件 | 构造 | 预期表现 |
|---|---|---|
| `inputs/ok_text.pdf` | 2 页 Helvetica 标准字体文字（每页 12 行 Tj，内容流不压缩） | pdftotext 可提取（1416 非空白字符）；路由 direct_text |
| `inputs/scan_like.pdf` | 1 页整页 64×64 DeviceGray 渐变图像 XObject（ASCIIHexDecode），内容流仅 `cm /Im0 Do`，无任何文字操作 | pdftotext 提取为空；路由 full_ocr |
| `inputs/broken_tail.pdf` | `ok_text.pdf` 前 60% 字节 | xref/trailer 缺失；取证如实报告 truncated；真实触发 partial（退出码 2/2/2） |

`inputs/case.json` 为合成契约（`case_id` + `output_contract`，5 个字段）。三个样本共用同一契约，scan/broken 运行时用 `--pdf` / `--case-id` 覆盖。

## 复现命令

```bash
cd examples/minimal
python3 inputs/make_samples.py   # 重新生成三个 PDF（确定性的）

S=../../scripts; I=inputs
# ok 样本（scan / broken 换成对应目录与 case-id：synthetic-intake-002 / 003）
python3 $S/pdf_forensics.py  $I/ok_text.pdf -o outputs/ok/forensics.json
python3 $S/textlayer_probe.py $I/ok_text.pdf --forensics outputs/ok/forensics.json -o outputs/ok/probe.json
python3 $S/route_case.py --case $I/case.json --forensics outputs/ok/forensics.json \
    --probe outputs/ok/probe.json --outdir outputs/ok \
    --pdf $I/ok_text.pdf --case-id synthetic-intake-001
```

`outputs/{ok,scan,broken}/` 为**真实本地运行产物**（macOS arm64，Python 3.12 + PyMuPDF 2.1 + pdftotext 25.01），非手写。

## 真实运行结果摘要

| 样本 | 页分类（probe, engine=pymupdf） | strategy | result status | 退出码 forensics/probe/route |
|---|---|---|---|---|
| ok | 2 页 text（各 708 字符，garbled=False） | direct_text | success | 0 / 0 / 0 |
| scan | 1 页 none（0 字符，含 1 幅 64×64 图像） | full_ocr，ocr_pages=[1] | success | 0 / 0 / 0 |
| broken | 1 页 text（864 字节，engine 降级为 stdlib_count） | direct_text（仅覆盖已恢复页） | **partial** | **2 / 2 / 2** |

## 目检结论（作者实际检查过）

1. **pdftotext 外部验证**：`pdftotext ok_text.pdf -` 提取出两页共 1416 个非空白字符（grep 验证第 2 页 12 行均在）；`scan_like.pdf` 输出 0 个非空白字符；`broken_tail.pdf` 报 `Couldn't find trailer dictionary / Couldn't read xref table`，退出码 1、无输出。
2. **forensics.json**：ok 样本 xref_ok=true、metadata（Producer/Creator/CreationDate）三项齐全、每页 text_showing_bytes=864（12 行 × 72 字节，与源文本精确一致）、字体 Helvetica/Type1/无 ToUnicode/未嵌入记录无误；scan 样本图像 XObject 的 Width×Height=64×64、DeviceGray、8bpc 识别正确；broken 样本 `startxref_found=false`、`truncated=true`、回退扫描恢复 1 页，crosscheck 如实记录 `page_count: stdlib=1 pymupdf=0`。
3. **probe.json**：broken 样本真实走完三级降级链 pymupdf（0 页）→ pdftotext（exit 1）→ stdlib_count，engine_notes 逐级留痕；乱码检测用 U+FFFD 串、`(cid:NN)` 串、干净中英混排串做了单元验证（前两者判 garbled，后者不误判）。
4. **routing/result**：三份 `result.json` 均含 case_id、契约 5 字段、status、sources、uncertainty、change_record；broken 的 uncertainty 明确标注"仅覆盖已恢复部分"，无任何伪造字段。
5. **修复过的真实 bug**：初版 `make_samples.py` 的 `/Pages /Kids` 指向了内容流对象（对象编号硬编码错误），导致 poppler 报 `Kid object is wrong type (stream)` 且 kids 遍历丢页——已改为按实际对象号生成 Kids 并加断言；初版 PDF 头含二进制注释行导致样本非 UTF-8——已移除，三个 PDF 现为纯 ASCII。
