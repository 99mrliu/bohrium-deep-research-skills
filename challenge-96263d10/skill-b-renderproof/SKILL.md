---
name: render-proof-template-adaptation
description: 学术格式与模板适配——渲染实测验收法（交得出）。不信 XML 声明，只信页面事实：把适配产物经 LibreOffice 真实渲染成 PDF+PNG，在 PDF 上实测页面尺寸、版心边距（逐词字形框）、栏数、字体清单与内嵌，再与规格逐项裁决出 PASS/FAIL/UNMEASURED 渲染账本；渲染器缺失时诚实降级并在 limits 声明，绝不拿 XML 检查冒充渲染验证。适用于"导出可交付文件""验证页边距/栏数/字体内嵌是否真符合模板""生成可供人工复核的预览"类任务；测量层纯 Python 3 标准库 + poppler（缺失自动降级），渲染层调用系统 LibreOffice。
---

# 渲染实测验收（render-proof：只信页面，不信声明）

版本 1.0。核心主张：格式适配的终局证据是**渲染后页面上的实测几何**，
不是 OOXML/LaTeX 源里的声明值。方法边界见 `references/render-method.md`。

以下 `$SK` 指本 SKILL.md 所在目录（平台安装为 `/skills/weekly-skill`，先 `ls /skills/` 确认）。

## 运行契约（平台约定，必须遵守）

- 输入 `/input/case.json` + `/input/task.md` + 材料；先读任务再读材料实际内容。
- 工作目录 `/app/work`，交付 `/app/output`；预览进 `/app/output/preview/`。
- `/app/output/result.json`：`case_id` + case.json `output_contract` **全部字段** +
  `status`（complete/partial/failed）+ `sources` + `changes` + `uncertainties` +
  `limits` + `artifacts`（带 sha256）。UNMEASURED 项未落实就是 partial。
- 预算约 900 秒：**第一步先落 partial result.json 骨架**，之后每阶段就地更新。
- 渲染工具缺失：render_status.json + limits 声明"无渲染证据"——诚实 partial
  优于伪造预览。

## 流水线（五步）

### 1. 规格就位
规格可以来自任何地方：任务说明直接给出、配套 spec 工具抽取、或手工整理。
落成扁平 JSON `/app/work/spec.json`：
```json
{"page.size.width_cm": 21.0, "page.margin.top_cm": 3.17, "page.columns": 2,
 "fonts.required": ["Liberation Serif"], "fonts.embedded_all": true}
```
规格里没有的项不验收；每个规格值注明来源（进 sources）。

### 2. 渲染
```bash
python3 $SK/scripts/render.py /app/output/交付件.docx --outdir /app/output/preview
```
退出码 0=PDF+PNG 齐备；3=渲染器缺失（转第 5 步的诚实降级）；1=渲染失败
（产物本身有问题，先修产物）。命令与返回码全部记录在 render_status.json。

### 3. 测量
```bash
python3 $SK/scripts/pdf_measure.py /app/output/preview/交付件.pdf --out /app/work/measurements.json
```
三层证据：MediaBox 页面几何（stdlib 恒可用）→ 字体清单与内嵌启发式 →
pdftotext 词框边距/栏检测（poppler 缺失时记 UNMEASURED，不猜）。

### 4. 裁决
```bash
python3 $SK/scripts/render_verdict.py /app/work/spec.json /app/work/measurements.json \
    --json /app/work/verdicts.json --md /app/output/render_ledger.md
```
- FAIL：改产物重渲染（不许改测量脚本迁就产物；规格错了改规格并记录 changes）。
- UNMEASURED：逐条人工看 PNG 落实，或进 manual_confirm 且 status=partial。
- render_ledger.md 是交付证据，必须进 /app/output。

### 5. 人工目检 + 交付
打开 preview/ 的 PNG 逐页目检（版式观感、题注位置、参考文献换行这类
机器不测的项），把结论写进 result.json 的 changes/uncertainties；
render_status.json、render_ledger.md、verdicts.json 随产物一并交付。

## 异常处理

| 情况 | 处置 |
|---|---|
| 渲染器缺失（退出 3） | 保留可编辑产物 + render_status.json，limits 声明无渲染证据，status=partial |
| 渲染失败（退出 1） | 产物损坏或含 LibreOffice 不支持的构造：修复后重渲，不交付打不开的文件 |
| pdftotext 缺失 | 几何项 UNMEASURED；页面尺寸/字体照常裁决；manual_confirm 记录 |
| PDF 是扫描件/无文本层 | 词框为空 → 边距栏数 UNMEASURED，limits 声明"内容疑似图片化" |
| 字体替换（如 Liberation Serif 缺失被换成 Carlito） | fonts.required 会 FAIL：要么安装指定字体重渲，要么在 uncertainties 声明替换事实 |
| 多栏含跨栏图表 | 栏检测可能误判 → columns 项转人工目检，不硬判 |
| 时间不足 | 骨架 → render → verdict 最小链先交付，测量细分项后补 |

## 资源清单（均在 `$SK/` 下）

| 路径 | 作用 |
|---|---|
| `scripts/render.py` | 渲染器探测 + docx→PDF→PNG + 全程状态记录（诚实降级） |
| `scripts/pdf_measure.py` | PDF 三层实测：MediaBox/字体内嵌/词框几何与栏检测 |
| `scripts/render_verdict.py` | 规格×实测逐项裁决 + 渲染账本（人读） |
| `references/render-method.md` | 方法论、判定边界（字形框/栏检测/内嵌启发式）、工具矩阵 |
| `examples/` | 合成示例：手写 PDF 的诚实 FAIL 演示 + DOCX 全链渲染实测 |

## 自查清单（交付前）

1. preview/ 有真实 PDF+PNG，render_status.json 记录完整命令链（或有缺失声明）。
2. render_ledger.md 无 FAIL；UNMEASURED 项全部有着落。
3. PNG 已逐页目检，观感问题进了 uncertainties。
4. result.json 契约字段全填，status 与证据一致。
