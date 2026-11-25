---
name: math-symbol-fidelity-lab
description: >-
  数学公式与特殊字符的符号级保真抽取。当任务是解析科研 PDF 并需要还原数学结构时触发:
  把靠排版表达的数学结构(上标 x²、下标 E_i、Symbol 字体的 α β γ、右端编号 (1))
  重建为可继续处理的线性形式(linear 字段,LaTeX 风格 ^{}/_{}),同时逐字符保留原文
  对照(verbatim);映射不了的符号进 unmapped 台账并告警,绝不静默替换。
  不做 OCR、不做章节树、不做公式语义理解。
---

# math-symbol-fidelity-lab

**核心原则:先保真、再线性化——每个字符都能指回原文页码与坐标,映射不了的进台账,绝不静默替换。**

## 1. 总览

```
/input/case.json + 案例 PDF
        │
        ▼
[1] scripts/extract_glyphs.py      引擎链: pymupdf rawdict(char 级)
        │                          → pdftotext -bbox(word 级降级)
        ▼                          输出: glyphs.jsonl + extract_report.json
[2] scripts/detect_math_zones.py   行分组(y 重叠) + ≥2 信号判公式行
        │                          输出: math_zones.json
        ▼
[3] scripts/linearize_math.py      基线分组 → ^{}/_{} 重建; Symbol/ZapfDingbats
        │                          字体映射; 编号配对; unmapped 台账
        ▼                          输出: equations.json + fidelity_report.json
[4] scripts/make_result.py         汇总契约字段
        │                          输出: /app/output/result.json
        ▼
   /app/work(中间产物)  →  /app/output(最终产物)
```

## 2. 运行契约

- 输入:`/input/case.json`、`/input/task.md`、案例 PDF(可能在 /input 子目录,
  先 `ls -R /input` 定位)。
- 工作区 `/app/work`(中间产物);交付区 `/app/output`(最终产物 + `result.json`)。
- `result.json` 必须含原 `case_id` 与 `output_contract` 声明的全部字段;无法填充的
  字段置 `null` 并在 `uncertainty` 说明,`status` 标 `partial`;必须含
  `status`(success/partial/failed/unable)、`sources`、`uncertainty`、`change_record`。
- 预算纪律:脚本是确定性的、不消耗模型请求。评测 Agent 只应:读 case → 依次调 4 个
  脚本 → 审 fidelity_report.json 与 unmapped 台账 → 写需要判断的字段。
  **先尽早落盘 partial result.json,再增量改善。**
- 脚本退出码:0=成功,2=部分(降级/告警/unmapped),3=失败;任何失败不静默。

## 3. 操作步骤(给评测 Agent)

```bash
ls -R /input                                   # 定位 case.json 与 PDF
mkdir -p /app/work /app/output

# [1] 字符/词级抽取(自动引擎链;缺 pymupdf 时自动降级 pdftotext 并写明原因)
python3 /skills/weekly-skill/scripts/extract_glyphs.py /input/<PDF> \
    --out /app/work/glyphs.jsonl --report /app/work/extract_report.json

# [2] 公式行判定
python3 /skills/weekly-skill/scripts/detect_math_zones.py /app/work/glyphs.jsonl \
    --out /app/work/math_zones.json

# [3] 线性化 + 保真报告
python3 /skills/weekly-skill/scripts/linearize_math.py \
    /app/work/glyphs.jsonl /app/work/math_zones.json \
    --out /app/work/equations.json --report /app/work/fidelity_report.json \
    --extract-report /app/work/extract_report.json

# [4] 契约感知汇总(尽早先跑一次落盘,再按需复查)
python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json \
    --glyphs /app/work/glyphs.jsonl --zones /app/work/math_zones.json \
    --equations /app/work/equations.json --fidelity /app/work/fidelity_report.json \
    --extract-report /app/work/extract_report.json --out /app/output/result.json
```

退出码非 0 时先读对应 JSON 报告里的 `degrade_reason` / `baseline_anomalies` /
`unmapped_symbols`,再决定人工复核点;2 是诚实 partial,不是错误。

## 4. 输出物说明

| 文件 | 内容 | 复核方式 |
|---|---|---|
| glyphs.jsonl | 每行一条 char(gid/page/c/codepoint/font/size/bbox/origin)或 word 记录 | 抽条与 PDF 页对照 |
| extract_report.json | 引擎、降级原因、页级 mode、计数 | 看 `degraded_pages` 是否为空 |
| math_zones.json | 公式区:page/y/raw_chars/detected_number/signals/partial | `signals` ≥2 才入区;核对编号 |
| equations.json | 每式 {id,page,anchor,verbatim,linear,number,unmapped[],partial} | verbatim vs linear 逐条目检 |
| fidelity_report.json | 替换计数、trusted_decoded、unmapped 台账、基线异常告警、status | unmapped>0 必须人工核 |
| result.json | 契约字段 + status/sources/uncertainty/change_record | 对照 case.json 的 output_contract |

## 5. 方法要点(阈值与判据,与代码一致)

- **公式行判定**:行内命中 ≥2 个信号 → math zone。信号:S1 希腊字母/Symbol 字体;
  S2 数学符号(∈∑∫√≤≥±×·=<> 等);S3 上下标结构(字号 ≤0.8×行中位 且 基线偏移
  ≥0.25×行字高);S4 行右端独立编号 `(n)`。行分组按 y 区间重叠聚合。
- **基线分组**:基线锚用 origin.y(rawdict 的 bbox 是字体 ascent/descent 盒,会
  抵消上下标位移,推导见 references/method.md);主组 = 字号 >0.8×行中位字号。
- **上标**:字号 ≤0.8×组中位 且 基线高于主组 ≥0.25×组字高 → `^{...}`;
  **下标**对称 → `_{...}`。小字号但偏移不足 → 按基线处理并告警
  `small-size-no-offset`;主字号偏离基线 >0.3×组字高 → `baseline-drift` 告警。
- **字体映射**:font 名含 Symbol 且字符仍是 ASCII 原始码位 → 按内嵌 Adobe Symbol
  编码映射表(149 条,完整表与信任判据见 references/symbol-map.md);抽取器已解出
  非 ASCII → 信任并计 `trusted_decoded`。ZapfDingbats 只认 3 条保守映射,其余进台账。
- **unmapped 台账**:无映射码位、U+FFFD、非 BMP(>U+FFFF)→ 台账(页码/坐标/字体/
  原始码位/原因),linear 用 `⟦U+XXXX⟧` 占位。台账覆盖公式区**及全局** Symbol/
  ZapfDingbats 字符(这两类字体只承载特殊符号,区外出现也要报警)。
- **编号配对**:行尾 `\((\d{1,4})\)$` 且首字符 x0 ≥ 行跨度 60% → 剥离存 `number`;
  verbatim 保留原样。

## 6. 异常与限制

| 情形 | 处置 |
|---|---|
| 环境无 pymupdf | 自动降级 pdftotext -bbox(word 级),extract_report 写明;该页标 partial,退出码 2 |
| 两者皆无 | 退出码 3,report 写双失败原因;result.json 落 failed/partial |
| word 级页 | 无字号 → 上下标判定跳过、字体映射不可用,zone 标 partial |
| Symbol 字体漏出原始字节 | 按编码表映射并计 replacement(fidelity_report 可核) |
| ZapfDingbats 生僻码位 | 进 unmapped 台账,不猜测 |
| U+FFFD / 非 BMP | 进 unmapped 台账,`⟦U+XXXX⟧` 占位 |
| 基线分组异常 | 告警写入 fidelity_report.baseline_anomalies,不中断 |
| 多行公式/分式/根号二维结构 | 不重组,按行线性化(见 references/method.md §5) |
| output_contract 含本 Skill 不产出的字段 | 置 null + uncertainty 说明,status=partial |

## 7. 最小示例(**合成示例**,非正式案例、非真实论文)

`examples/minimal/`:`inputs/make_sample.py`(纯标准库)生成 2 页合成 PDF——
Helvetica 正文 + /Symbol 字体 Greek(内容流字节 a b g → α β γ)+ Tm 位移构造的
上标 x²、下标 E_i + 三条编号公式 (1)(2)(3) + 一个 ZapfDingbats 生僻码位(0xA6)。

复现命令:

```bash
cd examples/minimal
python3 inputs/make_sample.py                    # 生成 inputs/sample_math.pdf
S=../../scripts; W=/tmp/msf-work; mkdir -p $W
python3 $S/extract_glyphs.py inputs/sample_math.pdf --out $W/glyphs.jsonl --report $W/extract_report.json
python3 $S/detect_math_zones.py $W/glyphs.jsonl --out $W/math_zones.json
python3 $S/linearize_math.py $W/glyphs.jsonl $W/math_zones.json --out $W/equations.json \
    --report $W/fidelity_report.json --extract-report $W/extract_report.json   # 退出码 2(预期)
python3 $S/make_result.py --case inputs/case.json --glyphs $W/glyphs.jsonl \
    --zones $W/math_zones.json --equations $W/equations.json \
    --fidelity $W/fidelity_report.json --extract-report $W/extract_report.json \
    --out $W/result.json                                                          # 退出码 2(预期)
```

预期:`E_{i} = x^{2} + χψ` 正确重建,(1)(2)(3) 编号配对,ZapfDingbats 字符进
unmapped 台账,result.json `status=partial`(诚实告警,非失败)。
`outputs/` 为本示例真实运行产物,目检结论见 `examples/minimal/README.md`。
