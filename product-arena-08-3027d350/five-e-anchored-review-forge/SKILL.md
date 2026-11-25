---
name: anchored-review-forge
description: >-
  何时触发：已有带坐标的解析块（blocks.jsonl + page_meta.json，任何上游产出，
  或需用附带的最小提取器从 PDF 现做）需要渲染成"人可复核"的评审交付物时。
  核心做法：逐页 SVG 锚点叠加图（页点 1:1、kind 着色、锚点标签）+ 单文件自包含
  review.html（右栏块文本带 [p1.b3] 徽章，hover/点击与左栏 SVG 矩形双向联动，
  纯内联 JS 无外部资源）+ sha256 产物清单 manifest.json 与契约感知 result.json。
  不在范围内：抽取算法本体（mini_extract.py 仅为喂数据）、证据门判定
  （不裁决对错，只保证每段文字能指回原文区块）。
---

# Anchored Review Forge：解析块 → 评审级可视化交付物

**核心原则：渲染端只做确定性的坐标映射与转义，让每一段文字 5 分钟内可被人眼指回原文区块；不裁决对错，只保证可复核。**

## 总览

```
/input/  case.json + task.md + *.pdf        （先 ls -R /input 定位）
   │
   ├─ 上游已给 blocks.jsonl + page_meta.json？──是──┐
   │否                                              │
   ▼                                               │
scripts/mini_extract.py  (pymupdf → pdftotext -bbox 自动降级)
   │  → /app/work/blocks.jsonl, /app/work/page_meta.json
   ▼                                               ▼
scripts/render_overlay.py  ── blocks + page_meta ──→ /app/output/overlays/page-N.svg
   │
   ▼
scripts/render_review.py   → /app/output/review.html（内嵌同一字节 SVG）
   │
   ▼
scripts/render_manifest.py → /app/output/manifest.json + result.json（契约感知）
```

四步均为确定性脚本，不消耗模型请求；模型只读 case、调脚本、审报告、写
result.json 中需要判断的字段（本 bundle 的 result.json 由脚本直接生成）。

## 运行契约

- 输入：`/input/case.json`、`/input/task.md`、案例 PDF（可能在 /input
  子目录，先 `ls -R /input` 定位）。若上游已在 /input 或 /app/work 提供
  符合 `references/block-schema.md` 的 blocks.jsonl + page_meta.json，
  **跳过 mini_extract.py 直接渲染**。
- 工作区 `/app/work`（中间产物：blocks.jsonl、page_meta.json）；交付区
  `/app/output`（最终产物 + `result.json`）。
- `result.json` 必含原 `case_id` 与 `output_contract` 声明的全部字段；
  无法填充的字段置 `null` 并在 `uncertainty` 说明，`status` 标
  `partial`；必含 `status`（success/partial/failed/unable）、`sources`、
  `uncertainty`、`change_record`。诚实 partial，绝不伪造。
- 预算纪律：64 次模型请求 / 900 秒 / 每响应 16384 tokens。脚本是确定性
  的；先尽早跑通四步落盘（哪怕 partial），再增量改善。
- 脚本退出码：0=成功、2=部分、3=失败；每步写机器可读
  `*.report.json`；任何失败不得静默。

## 操作步骤（给评测 Agent）

```bash
ls -R /input                                    # 0. 定位 case.json 与 PDF
mkdir -p /app/work /app/output

# 1. 仅当没有现成 blocks 时：PDF -> blocks.jsonl + page_meta.json
python3 scripts/mini_extract.py --pdf /input/<case>.pdf --out-dir /app/work

# 2. 逐页锚点叠加 SVG
python3 scripts/render_overlay.py \
  --blocks /app/work/blocks.jsonl --page-meta /app/work/page_meta.json \
  --out-dir /app/output

# 3. 自包含 review.html（需 overlays/ 已存在；缺失页会就地重建并记 warning）
python3 scripts/render_review.py \
  --blocks /app/work/blocks.jsonl --page-meta /app/work/page_meta.json \
  --out-dir /app/output

# 4. 清单 + 契约感知 result.json
python3 scripts/render_manifest.py \
  --out-dir /app/output \
  --blocks /app/work/blocks.jsonl --page-meta /app/work/page_meta.json \
  --case /input/case.json --pdf /input/<case>.pdf
```

注意：若 blocks 在 /app/work 而产物在 /app/output，第 4 步的 manifest
只哈希 /app/output 内文件；如需把 blocks.jsonl / page_meta.json 纳入交付，
先 `cp` 进 /app/output 再跑第 4 步（示例即如此）。每步结束读对应的
`extract/overlay/review/manifest.report.json`，非 0 退出码必须处理：
2=部分（读 warnings 决定是否接受），3=失败（按报告修复或如实上报）。

## 输出物说明

| 文件 | 内容 | 复核方式 |
|---|---|---|
| `overlays/page-N.svg` | 页面框 + 每块着色矩形 + 锚点标签，尺寸按页点 1:1 | `xmllint --noout`；矩形数 = 该页块数；坐标落在页宽页高内 |
| `review.html` | 自包含评审页：左栏内嵌 SVG，右栏阅读序块文本 + `[p1.b3]` 徽章，双向 hover/点击联动 | 浏览器打开抽查 3-5 个徽章；`html.parser` 解析无异常；文件头注释含生成时间与输入 sha256 |
| `manifest.json` | 每个产物文件的 sha256 + 块/锚点/页统计 + 输入哈希 | `shasum -a 256 <file>` 逐项比对 |
| `result.json` | 契约感知结果（case_id、契约字段、status、sources、uncertainty、change_record） | 对照 case.json 的 output_contract 逐字段检查 |
| `*.report.json` | 各脚本机器可读报告（engine、降级原因、warnings、退出码） | 读 `status` 与 `warnings` |

## 方法要点（阈值与判据，与代码常量一致）

- **坐标**：bbox 为 PDF 点、左上原点、y 向下；SVG 同系，直写 1:1 不做
  任何变换；viewBox = `0 0 W H`，数值两位小数。越界块不裁剪，记 warning。
- **转义**：SVG 侧 `&<>"'` 五字符 XML 转义；HTML 侧
  `html.escape(quote=True)` 五字符全覆盖；`<title>` 摘要取块文本前 80 字符。
- **锚点**：`p{page}.b{n}` 来自 blocks.jsonl，渲染端不重编号；SVG 元素
  id 加 `blk-` 前缀，卡片 id 加 `card-` 前缀；高亮 = 描边 1.2→3。
- **最小提取器聚块**：行归并容差 `max(2.0, 0.35×词高中位数)`；块切分
  为相邻行 y0 差 `> 1.5×基准行距`（全页正行距的 25 百分位）或 x 区间
  不重叠（容差 2pt）。
- **kind 规则**（按序）：Figure/Fig./Table 开头→caption；含 `=` 且字母
  占比 <0.6 且 <120 字符→equation；单行 ≤60 字符且编号开头→heading；
  首页首块字号 ≥1.25×中位数→title；其余 body。详见
  `references/block-schema.md`。
- **清单**：SHA-256，覆盖产物根目录全部文件，排除 manifest.json 与
  result.json 自身。详见 `references/render-contract.md`。

## 异常与限制

| 情形 | 处置 |
|---|---|
| pymupdf 缺失或打开失败 | 自动降级 `pdftotext -bbox`，报告写 `degraded_from` 与原因；title 判定改用兜底规则并记 warning，退出码 2 |
| 两引擎均不可用 / PDF 不存在 | 退出码 3，报告写失败原因，不产出 blocks |
| 某页零文本块 | 该页仍渲染空页面框，报告记 warning，退出码 2 |
| 块 bbox 越界或退化 | 照常渲染（不裁剪），报告记 warning，退出码 2 |
| 块指向 page_meta 中不存在的页 | 该块跳过，报告记 warning，退出码 2 |
| 上游 kind 不在 8 值枚举内 | 用兜底色 `#d62728` 渲染，不报错 |
| overlays/page-N.svg 缺失就跑 render_review | 按 svg_common 就地重建该页 SVG 并记 warning，退出码 2 |
| SVG 良构自检 / HTML 解析自检失败 | 退出码 3，不交付半成品 |
| 契约字段无法填充 | result.json 置 null + uncertainty 说明，status=partial |
| 扫描件无文本层 | mini_extract 产出零块 → 退出码 3；本 bundle 不做 OCR，如实上报 |
| 双栏/复杂版式 | mini_extract 的 column 只是中线占位实现，不保证分栏正确；评测中应换用上游 blocks |

## 最小示例（**合成示例**，非正式案例、非真实论文）

`examples/minimal/`：`inputs/make_sample.py` 用纯标准库生成合成单栏
PDF（2 页，含 title、heading、body、一条 `Figure 1:` caption、一条公式行），
四脚本端到端跑通，产物在 `outputs/`。复现命令与目检结论见
`examples/minimal/README.md`：

```bash
cd examples/minimal
python3 inputs/make_sample.py            # 生成 inputs/sample.pdf
python3 ../../scripts/mini_extract.py --pdf inputs/sample.pdf --out-dir outputs
python3 ../../scripts/render_overlay.py  --blocks outputs/blocks.jsonl --page-meta outputs/page_meta.json --out-dir outputs
python3 ../../scripts/render_review.py   --blocks outputs/blocks.jsonl --page-meta outputs/page_meta.json --out-dir outputs
python3 ../../scripts/render_manifest.py --out-dir outputs --blocks outputs/blocks.jsonl --page-meta outputs/page_meta.json --case inputs/case.json --pdf inputs/sample.pdf
```
