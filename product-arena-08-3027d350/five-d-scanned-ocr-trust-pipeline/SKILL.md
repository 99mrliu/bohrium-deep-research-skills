---
name: scanned-ocr-trust-pipeline
description: >-
  扫描版 PDF 与 OCR 产物的可信度流水线。何时触发：输入 PDF 疑似扫描件/影印件
  （无文字层、整页位图）、或需要对 ocr-tool 输出做校验时。核心做法：①纯标准库
  字节级判定逐页 born_digital/scanned/mixed/empty/unknown 并产出 OCR 移交
  清单（OCR 本体移交平台 ocr-tool 执行）；②对 OCR 文本做词典+混淆对的保守
  纠错——只改唯一解、全部记账、多解/无解标 suspect 原文保留；③产出逐页
  high/medium/low/illegible 可信台账，verbatim 与 corrected 双写。不在范围内：
  OCR 识别本体、加密/字体/截尾取证全案、多栏阅读顺序还原。
---

# scanned-ocr-trust-pipeline：扫描件与 OCR 产物可信度流水线

**核心原则：宁可不改、不可改错——每个结论都要么有字节级证据，要么如实标注 unknown / suspect。**

## 1. 总览

```
/input/case.json + task.md + *.pdf
        |
        v
[scripts/scan_detect.py]  纯标准库字节级判定（可选 PyMuPDF/pdftotext 交叉验证）
        |--> /app/work/scan_report.json      （逐页 page_class）
        |--> /app/work/handoff_ocr.json      （扫描页清单 + 建议参数）
        |
        v   （handoff 清单交给平台 ocr-tool；得到 OCR 文本，\f 分页）
        |
[scripts/ocr_postcheck.py]  词典 + 混淆对保守纠错
        |--> /app/work/postcheck.json        （corrections / suspects / 统计）
        |--> /app/work/corrected.txt         （与原文同结构）
        |
        v
[scripts/trust_ledger.py]   逐页可信分级 + 契约感知 result.json
        |--> /app/work/pages/page-NNN.{verbatim,corrected}.txt  （双写）
        |--> /app/output/trust_ledger.json
        |--> /app/output/result.json
```

## 2. 运行契约

- 输入：`/input/case.json`、`/input/task.md`、案例 PDF（可能在 /input 子目录，
  先 `ls -R /input` 定位）。
- 工作区 `/app/work`（中间产物）；交付区 `/app/output`（最终产物 + `result.json`）。
- `result.json` 含原 `case_id` 与 `output_contract` 全部字段；无法填充的字段
  置空并在 `uncertainty` 说明、`status` 标 `partial`；必含 `status`
  （success/partial/failed/unable）、`sources`、`uncertainty`、`change_record`。
  诚实 partial，绝不伪造。
- 预算纪律：脚本是确定性的、不消耗模型请求。评测 Agent 应先跑脚本拿结构化
  产物，模型只读 case、调脚本、审报告、写需要判断的字段；先尽早落盘
  partial，再增量改善。
- 脚本退出码：0=成功，2=部分，3=失败；任何失败不得静默（写进 JSON 报告）。

## 3. 操作步骤（给评测 Agent）

```bash
SK=/skills/weekly-skill          # 平台安装路径；以实际为准
mkdir -p /app/work /app/output
ls -R /input                     # 定位 case.json 与 PDF

# 步骤 1：扫描页判定 + OCR 移交清单
python3 $SK/scripts/scan_detect.py --pdf /input/<case>.pdf --outdir /app/work

# 步骤 2：OCR（本技能之外，移交平台 ocr-tool）
#   读取 /app/work/handoff_ocr.json 的 pages 清单，对所列页调用 ocr-tool，
#   建议参数：dpi=300，预处理 deskew + binarize。
#   将 ocr-tool 输出整理为纯文本、页间以换页符 \f 分隔，存为 /app/work/ocr.txt。
#   若 ocr-tool 不可用：在 result.json 的 uncertainty 说明，相关页为 illegible。

# 步骤 3：OCR 后处理校验与保守纠错
python3 $SK/scripts/ocr_postcheck.py --ocr /app/work/ocr.txt --outdir /app/work

# 步骤 4：逐页可信台账 + result.json
python3 $SK/scripts/trust_ledger.py \
  --scan /app/work/scan_report.json --post /app/work/postcheck.json \
  --ocr /app/work/ocr.txt --corrected /app/work/corrected.txt \
  --case /input/case.json --workdir /app/work --outdir /app/output
cp /app/work/scan_report.json /app/work/postcheck.json /app/output/   # 可选归档
```

拿到四个 JSON 后：先读 `trust_ledger.json` 的分级分布，再抽查 low/illegible
页的 verbatim/corrected 双写文件；回答 task.md 时只引用 medium 及以上可信
页的 corrected 文本，low 页内容必须注明"低可信 OCR 结果"。

## 4. 输出物说明表

| 文件 | 内容 | 复核方式 |
|------|------|----------|
| scan_report.json | 逐页 page_class、text_chars_approx、图像 XObject 数与像素量、引擎与交叉验证 | 对照 `engine.cross_validation` 各引擎是否 agree=true |
| handoff_ocr.json | 需 OCR 页清单：page、suggest_dpi=300、suggest_preprocess=[deskew,binarize]、reason | 抽查 scanned 页是否真无文字层 |
| postcheck.json | corrections 台账（page/line/from/to/rule）、suspects（多解/无解）、逐页统计 | 抽 3 条 corrections 在 corrected.txt 中核对 |
| corrected.txt | 与 OCR 原文同结构（\f 分页），仅台账记载的替换 | diff 原文，差异应逐条对应 corrections |
| trust_ledger.json | 逐页 trust 分级 + verbatim/corrected 双写路径 + 分级分布 | 对照阈值规则复算任意一页 |
| result.json | case_id、契约字段、status、sources、uncertainty、change_record | 字段是否齐、partial 原因是否写明 |

## 5. 方法要点（阈值与判据，代码与此一致）

扫描判定（scan_detect.py）：
- `MIN_TEXT_CHARS = 100`：页文本字符数阈值（BT..ET 内 Tj/TJ 字符串字符，字节级近似）。
- `FULLPAGE_PIXELS = 100000`：整页位图像素量阈值（/Width×/Height 求和）。
- 判定：text=0 且无图像→empty；text=0 且有图像→scanned；
  0<text<100 且有整页位图→scanned；0<text<100 无整页位图→mixed；
  text≥100 且有整页位图→mixed；text≥100 无整页位图→born_digital；
  内容流解码失败/引用对象缺失/截尾→unknown（绝不猜）。
- 截尾检测：文件尾 1KB 内无 `%%EOF` → warnings 记录并置退出码 2。

保守纠错（ocr_postcheck.py）：
- 混淆对：`l/1/I/|`、`O/0/o`、`rn/m`、`cl/d`、`5/S/s`、`vv/w`（详见
  `references/ocr-confusion-table.md`）。
- 词典：`references/lexicon-en.txt`（445 词，小写集合）。
- 改正条件（同时满足）：原 token 不在词典；单点替换后**唯一**小写形式在词典。
  数字上下文回退：token 仅一个非数字字符且两侧皆数字→改数字形
  （rule=numeric_context，如 `2O25→2025`）。
- 多解（≥2 候选在词典，如 `ha1l→hall/hail`）→ suspects 原文保留；
  无解但字母数字混排 → suspects 原文保留；普通未收录词只计 unknown_words。

可信分级（trust_ledger.py）：
- `RATE_MAX = 0.02`（修正率阈值）、`SUSPECT_MAX = 5`（单页 suspects 阈值）。
- born_digital 且无 suspect → **high**；born_digital 有少量 suspect → medium。
- scanned/mixed/unknown 页已 OCR、修正率 <2% 且 suspects ≤5 → **medium**。
- 修正率 ≥2% 或 suspects >5 → **low**。
- 无文字层且未 OCR（含 unknown 页无 OCR）→ **illegible**，不猜测内容。

## 6. 异常与限制

| 情形 | 处置 |
|------|------|
| PyMuPDF / pdftotext 缺失 | 主判定不受影响；engine.cross_validation 记 unavailable 及原因 |
| 内容流含 LZW/JBIG2 等标准库不可解滤镜 | 该页标 unknown，notes 记 unsupported_filter |
| PDF 截尾 | warnings 记录；缺失对象页标 unknown；退出码 2 |
| CJK / 复合字体 | text_chars_approx 为字节级近似，可能低估；页类判定（有无文字层）不受影响 |
| OCR 文本为空 | postcheck.json 标 partial（ocr_empty），corrected.txt 为空 |
| OCR 页数 ≠ PDF 页数 | 超出页按 unknown 类降级，uncertainty 记录 |
| 多解混淆（hall/hail 型） | 进 suspects 不改，由模型按上下文人工裁决 |
| 词典未收录的专名/术语 | 仅计 unknown_words，不改不报 |
| 加密 PDF | 不在本技能范围（属取证方向），scan_detect 解析失败页标 unknown |

## 7. 最小示例（**合成示例**，非正式案例、非真实论文）

`examples/minimal/`：`inputs/make_scan_pdf.py` 纯标准库生成 1 页纯位图
`scan_like.pdf`（ASCIIHexDecode DeviceGray，无文字）；`inputs/synthetic_ocr.txt`
为 3 页人工编造 OCR 文本（13 处典型错误 + 2 处多解 suspect）；`outputs/` 为
三个脚本真实运行的全部产物。复现命令与目检结论见 `examples/minimal/README.md`。
