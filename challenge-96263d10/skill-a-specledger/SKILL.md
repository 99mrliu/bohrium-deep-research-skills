---
name: spec-ledger-template-adaptation
description: 学术格式与模板适配——规格账本先行法（认得准）。在改动任何稿件之前，先把模板 DOCX、投稿须知、任务说明里的格式要求抽成带溯源指针的结构化规格账本（页边距/字号/行距/栏数/标题层级/题注位置/参考文献标准），多来源冲突按优先级显式裁决并记录落选值；随后一切适配与验收都以账本为唯一依据，机器可核对项由脚本逐项 PASS/FAIL/UNKNOWN，UNKNOWN 项强制进入人工确认清单。适用于"把稿件按目标模板改到可交付""从模板/须知提取检查清单""核对一份稿件是否符合格式要求"等任务；纯 Python 3 标准库，无第三方依赖。
---

# 规格账本先行的模板适配（spec-ledger first）

版本 1.0。核心主张：**先取证，后排版**。格式错误的根源不是不会改 Word，
而是规格靠猜。本 Skill 把"认得准"做成强制工序：没有进账本的规格不许执行，
没有溯源的条目不许进账本。方法细节与 status 语义见 `references/spec-schema.md`。

以下 `$SK` 指本 SKILL.md 所在目录（平台安装为 `/skills/weekly-skill`，先 `ls /skills/` 确认）。

## 运行契约（平台约定，必须遵守）

- 输入：`/input/case.json` + `/input/task.md` + 材料文件；先读 `task.md` 与 case.json，
  再读材料实际内容（不许按文件名猜内容）。
- 工作目录 `/app/work`；交付 `/app/output`。
- `/app/output/result.json` 必须含 `case_id` 与 case.json `output_contract` 的**全部字段**，
  另有 `status`（complete/partial/failed）、`sources`、`changes`、`uncertainties`、
  `limits`、`artifacts`（带 sha256）。有未确认项就写 partial，不许写 complete。
- 预算约 900 秒：**第一步先落 partial result.json 骨架**（case_id + 空契约字段 +
  status=partial + limits=["run started"]），之后每完成一阶段就地更新。
- 可编辑 Office 产物须附真实渲染 PDF/PNG 预览；渲染工具缺失时在 limits 声明，不伪造。

## 流水线（五步，严格按序）

### 1. 取证：模板/稿件 DOCX → 实测规格
```bash
python3 $SK/scripts/docx_spec.py 模板.docx --out /app/work/template_spec.json --role template
```
抽取页面几何（尺寸/页边距/栏数/节数/页眉页脚）、样式表（字体/字号/行距/段距/
对齐/大纲层级）、题注线索，每项带 `word/styles.xml#style[...]` 级溯源，status=measured。

### 2. 取证：文字材料 → 明示规则
```bash
python3 $SK/scripts/rules_spec.py 须知.txt --out /app/work/rules_spec.json
# task.md 同样过一遍；PDF 须知先 pdftotext 再过本脚本
```
命中"上 3.17 cm / 正文五号 / 行距 1.5 倍 / 双栏 / GB/T 7714 / 图题注置于图下方"等
模式，带行号与原文，status=stated。识别不出的要求：阅读原文后在 spec.json 手工
补项并标 status=assumed——assumed 项只能进 uncertainties，不许当规格执行。

### 3. 合并裁决：唯一账本
```bash
python3 $SK/scripts/spec_merge.py 任务规则.json:100 须知.json:50 模板实测.json:10 --out /app/work/merged_spec.json
```
优先级：task.md 明示 > 须知/补充规定 > 模板实测。退出码 1 = 存在已裁决冲突，
落选值全记录；**每条冲突必须写进 result.json 的 uncertainties**（采用值+落选值+来源）。

### 4. 适配执行（Agent 主导，账本驱动）
按 merged_spec.json 逐项改造稿件：样式重绑、页面几何、题注位置、参考文献样式。
改动一处勾一处；每处改动进 `changes`（unit/before/after/spec_id）。样式名匹配
大小写不敏感；深层标题层级以模板 outlineLvl 为准，不许只改字号加粗冒充层级。

### 5. 机器验收 + 人工兜底
```bash
python3 $SK/scripts/spec_check.py /app/work/merged_spec.json /app/output/交付件.docx \
    --json /app/work/check.json --md /app/output/spec_check_report.md
```
- FAIL：修输出或修规格（规格抽错时），重跑至 0 FAIL。
- UNKNOWN：逐条凭渲染预览/原文人工核对，勾完的进 changes，未勾的进
  manual_confirm 且 status=partial。
- spec_check_report.md 作为交付证据之一进 /app/output。

## 异常处理

| 情况 | 处置 |
|---|---|
| case.json 损坏 | 第 0 步的 partial 骨架已落盘，limits 记录错误，照实结束 |
| 模板是 PDF 非 DOCX | docx_spec 退出码 2；改走 rules_spec(pdftotext) + 人工补项，limits 声明"无实测规格" |
| 须知与模板冲突 | spec_merge 已裁决；uncertainties 点名，不静默二选一 |
| 同来源自相矛盾 | 不自动裁决：两项并列标 assumed，进 manual_confirm |
| 输出打不开/损坏 | spec_check 退出码 2；重建产物后重验，不交付坏文件 |
| 时间不足 | 骨架 → template_spec → merged_spec → 适配核心样式 → spec_check，随时可 partial 交付 |

## 资源清单（均在 `$SK/` 下）

| 路径 | 作用 |
|---|---|
| `scripts/docx_spec.py` | DOCX → 实测规格（24+ 项，OOXML 溯源） |
| `scripts/rules_spec.py` | 文字材料 → 明示规则（行号溯源，中文字号表换算） |
| `scripts/spec_merge.py` | 多来源合并 + 优先级裁决 + 冲突全记录 |
| `scripts/spec_check.py` | 输出件逐项 PASS/FAIL/UNKNOWN + 证据报告 |
| `references/spec-schema.md` | 条目模式、status 语义、单位换算、冲突政策 |
| `examples/` | 合成示例：含真实冲突裁决与 FAIL→修复→PASS 闭环 |

## 自查清单（交付前）

1. /app/output 有 partial 起步、最终完整的 result.json（契约字段全填）。
2. merged_spec.json 的 conflicts 全部进了 uncertainties。
3. spec_check 0 FAIL；UNKNOWN 项全部有着落（changes 或 manual_confirm）。
4. spec_check_report.md、渲染预览（或缺失声明）在 /app/output。
