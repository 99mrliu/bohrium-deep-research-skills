---
name: pdf-intake-forensics
description: >-
  何时触发：拿到案例 PDF 之后、任何正文解析之前，需要回答"这份 PDF 能不能解析、哪部分能、该走哪条路"时使用。
  核心做法：纯标准库字节级取证（扫描间接对象、校验 startxref/xref、解压内容流统计 Tj/TJ），
  再做每页文字层判定（pymupdf → pdftotext → 标准库计数三级降级引擎链，含乱码检测），
  最后产出路由计划（direct_text / mixed_ocr / full_ocr / handoff）与契约感知 result.json。
  不在范围内：不做正文重建、阅读顺序、表格抽取、章节结构、公式符号、OCR 后处理与渲染校对——
  本 Skill 只做输入取证与路由，输出交给下游方向。
---

# pdf-intake-forensics：PDF 输入取证与路由

**核心原则：先验货，再开工——在消耗任何解析预算之前，用确定性脚本对 PDF 做字节级体检，能读的如实路由，读不出的如实 handoff，绝不硬解析、绝不伪造文字层。**

## 总览

```
/input/case.json + 案例 PDF
        |
        |  ls -R /input 定位 PDF
        v
+------------------------+      纯标准库字节级扫描（不解析正文）
| scripts/pdf_forensics  | ---> /app/work/forensics.json
+------------------------+      pdf_version/encrypted/page_count/xref/metadata/每页字体图像
        |
        v
+------------------------+      引擎链 pymupdf -> pdftotext -> 标准库计数
| scripts/textlayer_probe| ---> /app/work/probe.json
+------------------------+      每页 text/sparse/none + 乱码检测
        |
        v
+------------------------+      路由 + 契约感知交付
| scripts/route_case     | ---> /app/output/routing_plan.json
+------------------------+      /app/output/intake_summary.md
                                /app/output/result.json
```

脚本是确定性的、不消耗模型请求。评测 Agent 只做四件事：读 case、调脚本、审报告、写需要判断的字段。

## 运行契约

- 输入：`/input/case.json`、`/input/task.md`、案例 PDF（可能在 `/input` 子目录，先 `ls -R /input` 定位）。
- 工作区 `/app/work`（中间产物 `forensics.json`、`probe.json`）；交付区 `/app/output`（`routing_plan.json`、`intake_summary.md`、`result.json`）。
- `result.json` 必须含原 `case_id` 与 `output_contract` 声明的全部字段；无法填充的字段置空并在 `uncertainty` 说明，`status` 标 `partial`；须含 `status`（success/partial/failed/unable）、`sources`、`uncertainty`、`change_record`。诚实 partial，绝不伪造。
- 预算纪律：64 次模型请求 / 900 秒 / 每响应 16384 tokens。三个脚本均为确定性脚本，先尽早落盘 partial（哪怕只跑完第 1 个脚本，也先把已得信息写进 `result.json`），再增量改善。
- 脚本退出码：0=成功、2=部分、3=失败；任何失败不得静默，全部写进 JSON 报告与 stderr。
- 核心逻辑只用 Python 3 标准库；PyMuPDF/pdftotext 仅作可选引擎，缺失时自动降级并在 JSON 里写明 `engine` 与降级原因。禁止联网、禁止 pip 安装。

## 操作步骤

```bash
# 0. 定位输入
ls -R /input
PDF=$(ls /input/*.pdf /input/**/*.pdf 2>/dev/null | head -1)
mkdir -p /app/work /app/output

# 1. 结构取证（纯标准库；有 PyMuPDF 时自动交叉验证）
python3 /skills/weekly-skill/scripts/pdf_forensics.py "$PDF" -o /app/work/forensics.json
echo "exit=$?"   # 0 ok / 2 partial / 3 failed

# 2. 每页文字层判定（自动降级引擎链）
python3 /skills/weekly-skill/scripts/textlayer_probe.py "$PDF" \
    --forensics /app/work/forensics.json -o /app/work/probe.json
echo "exit=$?"

# 3. 路由 + 契约感知交付
python3 /skills/weekly-skill/scripts/route_case.py \
    --case /input/case.json \
    --forensics /app/work/forensics.json \
    --probe /app/work/probe.json \
    --outdir /app/output
echo "exit=$?"
```

逐步判读：

1. 先看 `forensics.json` 的 `status` 与 `issues`：`encrypted=true` → 直接 handoff（勿尝试暴力解密）；`truncated=true` → 后续所有结论只覆盖可恢复部分。
2. 再看 `probe.json` 的 `classification_summary` 与每页 `garbled`：确认引擎链停在哪一级（`engine` 字段）、降级原因（`engine_notes`）。
3. 最后审 `routing_plan.json`：`strategy`、`ocr_pages`、`handoff_reason` 是否与前两份报告自洽；`intake_summary.md` 是给人读的同内容摘要。
4. `result.json` 由脚本按 `output_contract` 自动填充；Agent 只需复核 `uncertainty` 是否如实、并在需要时补充判断性字段。路由结论之后的正文解析（阅读顺序/表格/章节/公式/OCR 后处理/渲染）交下游方向，不属于本 Skill。

## 输出物说明表

| 文件 | 内容 | 复核方式 |
|---|---|---|
| `/app/work/forensics.json` | pdf_version、encrypted、page_count、object_count、xref 完好性/截尾、线性化、metadata、每页 MediaBox/Rotate/Tj-TJ 文本字节/字体清单(BaseFont/Subtype/ToUnicode/嵌入)/图像清单、crosscheck | `status` 与 `issues` 字段；`crosscheck.diffs` 应为空或有解释 |
| `/app/work/probe.json` | 引擎链选择结果与降级原因、每页 text/sparse/none 分类、乱码 metrics（U+FFFD、(cid:NN)、控制字符、高字节占比）、分类汇总 | 抽查 `sample` 字段首尾文本是否可读；`engine` 与 `engine_notes` 自洽 |
| `/app/output/routing_plan.json` | strategy（direct_text/mixed_ocr/full_ocr/handoff）、ocr_pages、handoff_reason、issues | 与 probe 分类汇总逐页对账 |
| `/app/output/intake_summary.md` | 人读摘要：体检结论 + 每页判定表 + 路由结论 + 风险清单 | 目检 |
| `/app/output/result.json` | 契约感知交付：case_id、output_contract 全部字段、status、sources、uncertainty、change_record | 字段齐全、无伪造、partial 诚实 |

## 方法要点（阈值与判据，与代码常量一致）

| 判据 | 数值 | 出处 |
|---|---|---|
| 页分类 `none`（扫描页） | 非空白字符数 ≤ 10 | `textlayer_probe.py: NONE_MAX_CHARS = 10` |
| 页分类 `sparse`（零星文字） | 10 < 非空白字符数 < 100 | 同上两个常量 |
| 页分类 `text`（正常文字层） | 非空白字符数 ≥ 100 且未判乱码 | `TEXT_MIN_CHARS = 100` |
| 乱码判定 `garbled` | garbage_ratio = (U+FFFD数 + (cid:NN)命中数 + 控制字符数) / max(非空白字符数,1) > 0.05，或出现任意 `(cid:NN)` 命中 | `GARBAGE_RATIO_THRESHOLD = 0.05` |
| 可疑高字节占比 | 非空白字符中码点 >126 的占比（仅记录不判罪，CJK 文献合法） | `garbage_metrics()` |
| 截尾判定 | 文件尾 1024 字节窗口内无 `%%EOF`，或 `startxref` 缺失/指向非法偏移 | `pdf_forensics.py: TAIL_WINDOW = 1024` |
| 线性化判定 | 文件头 1024 字节内含 `/Linearized` | `HEAD_WINDOW = 1024` |
| 文本字节计数 | 内容流（FlateDecode/ASCIIHexDecode 解码后）中 Tj/TJ 操作字面字符串字节数之和，forensic 近似值 | `count_text_bytes()` |
| 路由 `direct_text` | 全部页 = text 且无乱码页 | `route_case.py: decide()` |
| 路由 `mixed_ocr` / `full_ocr` | 部分 / 全部页 ∈ {none, sparse} 或乱码页，列入 `ocr_pages` | 同上 |
| 路由 `handoff` | 加密 / 非 PDF / 页面对象为零 / 三级引擎均无产出 | 同上 |
| 状态流转 | 截尾、降级、crosscheck 差异、契约字段无法填充 → `partial`；非 PDF → `failed`；否则 `success` | 三脚本退出码 0/2/3 对应 |

降级引擎链：pymupdf（首选，逐页 `get_text`）→ pdftotext（`-enc UTF-8`，按 `\f` 分页）→ 标准库计数（复用 forensics 的 Tj/TJ 字节计数，只有字节数、无乱码检测）。引擎返回 0 页视为失败并继续降级（典型于截尾/坏 xref）。

## 异常与限制表

| 情形 | 处置 |
|---|---|
| 加密 PDF（存在 `/Encrypt`） | strategy=handoff，reason=encrypted_pdf；不尝试解密 |
| 非 PDF（无 `%PDF-x.y` 头） | forensics status=failed，退出码 3，result.json status=failed |
| 截尾/坏 xref | 标记 truncated，回退按对象号顺序扫描页面（页序不保证，如实记录）；路由仅覆盖可恢复部分，status=partial |
| 增量更新（多个 `%%EOF` 或 `/Prev`） | 记录 incremental_update；正则扫描取首个同名对象，可能非最新修订，写入 issues |
| 对象流（`/ObjStm`）/ xref 流 | 标准库扫描看不到压缩对象，计数可能偏低；记录 object_streams，依赖 PyMuPDF crosscheck 兜底 |
| 无 ToUnicode 的字体 | forensics 记录 has_tounicode=false；若 probe 判 garbled=true，该页入 ocr_pages 交 OCR |
| 扫描件（整页图像、无文字操作） | 页分类 none → full_ocr/mixed_ocr，交 d-scan-ocr-trust 方向 |
| pymupdf/pdftotext 均缺失 | 降级 stdlib_count，status=partial，乱码检测不可用，如实写明 |
| 内容流使用未知 Filter | decode 报错写入 decompress_errors，该页文本字节按已解码部分计，status=partial |
| 正则扫描的固有误报（流内出现 `N 0 obj` 字样等） | 同号对象取首次出现；crosscheck 用 PyMuPDF 页数对账，差异写入 diffs |

## 最小示例（**合成示例**，非正式案例、非真实论文）

`examples/minimal/` 内含三个纯标准库手写的合成 PDF：`ok_text.pdf`（2 页正常文字）、`scan_like.pdf`（1 页整页灰度图像、无文字）、`broken_tail.pdf`（ok_text 截尾 60%）。`outputs/` 为真实本地运行产物。

```bash
cd examples/minimal
python3 inputs/make_samples.py            # 重新生成三个 PDF
S=../../scripts
python3 $S/pdf_forensics.py  inputs/ok_text.pdf -o outputs/ok/forensics.json
python3 $S/textlayer_probe.py inputs/ok_text.pdf --forensics outputs/ok/forensics.json -o outputs/ok/probe.json
python3 $S/route_case.py --case inputs/case.json --forensics outputs/ok/forensics.json \
    --probe outputs/ok/probe.json --outdir outputs/ok \
    --pdf inputs/ok_text.pdf --case-id synthetic-intake-001
# scan / broken 同理（broken 真实触发 partial：退出码 2/2/2，stdlib_count 兜底）
```

预期：ok → direct_text/success；scan → full_ocr（ocr_pages=[1]）/success；broken → direct_text（仅覆盖已恢复页）/partial，xref 损坏如实报告。详见 `examples/minimal/README.md`。
