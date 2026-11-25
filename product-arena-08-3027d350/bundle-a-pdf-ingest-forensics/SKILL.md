---
name: pdf-ingest-forensics
description: >-
  在解析任何科学 PDF 之前，先对输入做法医式分诊（forensic triage），
  保证下游步骤永远不会解析垃圾输入、永远不会从不可读输入中编造内容。
  触发时机：收到任何需要先读取 PDF 的 case（全文抽取、表格抽取、文献综述、
  数据提取等）时，本 Skill 是解析之前的第一道工序。它检测：加密 PDF、
  逐页文本层覆盖率、扫描页、字体/字形乱码（CID 自定义编码、PUA 私用区字符、
  U+FFFD 替换符）、页面旋转异常、重复页，并给出路由决定
  （直接走文本层 / 移交 OCR / 停止并如实上报）。超出范围：本 Skill 不做正文
  抽取本身、不做 OCR 本身、不修复 PDF、不猜测任何内容；它只回答一个问题——
  "这份输入能不能读、每一页该交给谁读"，并对"读不了"诚实地说读不了。
---

# pdf-ingest-forensics：PDF 入库前法医分诊

上游数据真实性优先：宁可诚实地报告"这份输入读不了"，也绝不从垃圾输入里
编造看似合理的内容。本 Skill 在任何解析动作之前运行，输出一份逐页的路由
决定和一份诚实填写的 result.json 骨架。

## 总览

```
                 ┌─────────────────────┐
   case PDF ───► │ 1. pdf_probe.py      │  加密? 页数? 旋转? 图像 vs 文本层?
   (或 manifest) │    容器级 + 逐页探针  │  逐页字符覆盖率(文本层) / 重复页
                 └─────────┬───────────┘
                           │ intake_report.json   (加密 → 直接 failed, exit 3)
                           ▼
                 ┌─────────────────────┐
   已抽取文本 ──► │ 2. glyph_audit.py    │  U+FFFD / PUA 私用区 / 控制字符 /
   (若有)        │    字形乱码审计       │  UTF-8-as-Latin-1 乱码签名
                 └─────────┬───────────┘
                           │ glyph_audit.json
                           ▼
                 ┌─────────────────────┐
   case.json ──► │ 3. route_decision.py │  路由: direct_text_layer /
                 │    融合 + 路由决定    │  ocr_handoff / mixed_pagelevel /
                 │                     │  refuse_with_handoff
                 └─────────┬───────────┘
                           ▼
        route_decision.json + result.json（诚实状态 + 契约字段骨架）
                           │
        ┌──────────────────┼───────────────────────┐
        ▼                  ▼                       ▼
  direct 页面 → 文本层抽取   ocr 页面 → 移交 OCR 工具   refuse → 停止并如实上报
```

## 运行契约

**输入（先读真实文件，不要凭印象）：**

- `/input/case.json`：case 定义，含 `case_id` 与 `output_contract`（必须逐字
  遵守其中列出的字段名）。
- `/input/task.md`：任务叙述，读它确认交付物口径。
- case PDF 本体：用 `ls -R /input` 实际列目录定位，不要假设文件名。

**工作目录与交付：**

- 在 `/app/work` 下跑脚本、放中间产物（intake_report.json、glyph_audit.json、
  route_decision.json）。
- 交付物写入 `/app/output`。
- `/app/output/result.json` 必须：① 原样携带 case 的 `case_id`；② 包含
  `output_contract` 点名的每一个字段；③ 填不了的字段留空，并在
  `uncertainty` 中逐条解释为什么空；④ `status` 如实取
  `success | partial | failed`——只要有扫描页/乱码页/旋转页/重复页/覆盖率
  未测量，就是 `partial`；加密或零页就是 `failed`。

**预算纪律（64 次模型请求 / 900 秒）：**

先把三个脚本跑完（秒级、零模型消耗），模型只花在机器做不了的判断上：
异常措辞、路由复核、result.json 的最终措辞。不要逐页用模型"看"PDF。

## 操作步骤

1. `ls -R /input` 并读取 `case.json`、`task.md`，定位 case PDF。
2. 运行 `python3 scripts/pdf_probe.py <case.pdf> --out /app/work`。
   - exit 3（如 `encrypted_pdf`）→ 直接跳到第 5 步，route 为
     `refuse_with_handoff`，不要尝试破解或跳过加密。
   - 若环境装有 poppler（`pdftotext`）或 PyMuPDF，脚本会自动测量逐页字符
     数；没有这些工具时报告会标注 `text_layer_measured: false`，路由只能
     是临时性的，必须在 uncertainty 中声明。
3. 若已有（或平台工具产出了）抽取文本，运行
   `python3 scripts/glyph_audit.py <txt目录> --out /app/work` 审计字形乱码。
4. 运行
   `python3 scripts/route_decision.py --intake /app/work/intake_report.json --glyph /app/work/glyph_audit.json --case /input/case.json --out /app/work`，
   得到 route_decision.json 和 result.json 骨架。
5. 按路由执行后续（文本层抽取 / 移交 OCR / 停止上报），把最终 result.json
   写入 `/app/output`；保持诚实状态，空字段一律在 uncertainty 中解释。

## 输出物说明

| 文件 | 产出脚本 | 内容 | 去向 |
|---|---|---|---|
| `intake_report.json` | pdf_probe.py | 容器探针结果：加密标志、页数、逐页 char_count/image_count/rotate/指纹、扫描页/旋转页/重复页清单、status(ok/partial/failed)+reasons | 中间产物 + 附于交付 |
| `glyph_audit.json` | glyph_audit.py | 逐文件与全局的乱码指标：U+FFFD、PUA 比率、控制字符、mojibake 命中、严重度 | 中间产物 + 附于交付 |
| `route_decision.json` | route_decision.py | 总体路由 + 逐页 action 与理由 | 中间产物 + 附于交付 |
| `result.json` | route_decision.py | 契约字段骨架：case_id、status、fields（空字段已解释）、sources、uncertainty、change_record | `/app/output` |

脚本退出码统一：0 = ok / 2 = partial / 3 = failed。

## 方法要点

- **加密检测**：直接在原始字节中搜 `/Encrypt` 标记；命中即 exit 3、
  route=`refuse_with_handoff`。绝不尝试解密。
- **扫描页判定**：页上有图像 XObject 且可抽取字符 < 20 ⇒ scanned candidate。
- **乱码判定**：PUA 字符占字母类字符比率 > 0.5%、或出现 U+FFFD 连续段、
  或 UTF-8-as-Latin-1 签名（`â€`、`ç±»` 形态）成簇 ⇒ 该页文本层不可信，
  改派 OCR 重新获取，而不是把乱码当内容。
- **旋转页**：`/Rotate` 非 0 ⇒ 文本层可用，但任何版面/表格分析前必须先
  按声明角度回正。
- **重复页**：规范化文本指纹（或 manifest 指纹）相同 ⇒ 只解析一次，记录
  页码映射，防止下游把重复页当新证据。
- 阈值与失效模式详见 `references/method.md` 与
  `references/failure-taxonomy.md`。

## 异常与限制

| 输入异常 | 检测信号 | 路由动作 | result.json 处理 |
|---|---|---|---|
| 加密 PDF | `/Encrypt` 标记 | refuse_with_handoff | status=failed，内容字段全空并解释 |
| 无文本层（扫描件） | 有图像且字符 <20/页 | ocr_handoff（整本或逐页） | status=partial，声明该页内容来自 OCR |
| PUA/CID 乱码 | PUA 比率 >0.5% | 该页改派 ocr_handoff | status=partial，注明文本层不可信 |
| U+FFFD 替换符 | 连续段 >2 | 同上 | 同上 |
| 旋转页 | `/Rotate` ≠ 0 | direct，但标注先回正 | partial 或 success 视其他异常 |
| 重复页 | 指纹相同 | direct，只解析一次 | uncertainty 中记录页码映射 |
| 纯图像表格 | 该页被判 scanned | 移交 OCR + 表格工具 | partial；不编造表格数值 |
| 无 poppler/pymupdf | text_layer_measured=false | 临时路由 | partial，声明覆盖率未测量 |

## 最小示例

`examples/minimal/` 是一个**合成示例**（synthetic demo）：pages.json、
case.json 与所有 pageNN.txt 都是手工编造的，不是正式 case、不来自任何真实
论文。它让三个脚本在没有真实 PDF 的情况下跑通全流程，outputs/ 中的四份
JSON 是真实运行产生、并经过人工核对的。

```bash
cd skill
EX=examples/minimal
python3 scripts/pdf_probe.py --manifest $EX/inputs/pages.json --out $EX/outputs
python3 scripts/glyph_audit.py $EX/inputs/extracted --out $EX/outputs
python3 scripts/route_decision.py --intake $EX/outputs/intake_report.json \
  --glyph $EX/outputs/glyph_audit.json --case $EX/inputs/case.json \
  --out $EX/outputs
```

预期：pdf_probe 报出扫描页 [3,10]、旋转页 [7]、重复页 (8,9)，exit 2；
glyph_audit 把 page05.txt 判为 high（PUA + U+FFFD），exit 2；
route_decision 给出 `mixed_pagelevel`，OCR 页为 [3,5,10]，
result.json 状态为 `partial`。
