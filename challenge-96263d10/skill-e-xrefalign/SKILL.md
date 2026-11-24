---
name: xref-reference-consistency
description: 学术格式与模板适配——图表交叉引用与参考文献一致性法（排得对的语义层）。版式对了不算完：题注编号重复/断档、正文悬空引用、表题注放错位置、参考文献缺类型标志/作者未截断/缺年份，这四类语义事故靠肉眼最容易漏。本 Skill 从 DOCX/Markdown/文本中抽取有序块流，机器检查题注-引用-对象三方一致性，GB/T 7714 形式初筛逐条过，重编号先生成全量方案（题注映射+全部正文引用点）再由 Agent 同事务执行，改完重扫验证留档。纯 Python 3 标准库。适用于"图表编号与交叉引用整理""参考文献格式规范化""适配后一致性回归"类任务。
---

# 图表·交叉引用·参考文献一致性（xref-align）

版本 1.0。重心：**语义一致性**。字号行距全对、正文却引用着不存在的"图3"，
是最典型的"外观相似、逐项不符"。规则口径（含通行惯例与任务优先声明）见
`references/xref-rules.md`。

以下 `$SK` 指本 SKILL.md 所在目录（平台安装为 `/skills/weekly-skill`，先 `ls /skills/` 确认）。

## 运行契约（平台约定，必须遵守）

- 输入 `/input/case.json` + `/input/task.md` + 材料；先读任务再读材料实际内容。
- 工作目录 `/app/work`，交付 `/app/output`。
- `/app/output/result.json`：`case_id` + `output_contract` **全部字段** + status/
  sources/changes/uncertainties/limits/artifacts（带 sha256）；
  有未裁定 WARNING 或人工未抽核项就 partial。
- 预算约 900 秒：**第一步先落 partial result.json 骨架**，之后每阶段就地更新。
- Office 产物附真实渲染 PDF/PNG；渲染不可用写 limits。

## 流水线（六步）

### 1. 规则就位
读 task.md 与模板/须知，确定题注位置规则（默认：图下表上，任务明示优先）、
编号体系（1..N 还是 3-1 式）、参考文献标准（GB/T 7714 / APA / 其他）。
非 GB/T 7714 时 refstyle_check 只做缺年份等通用项，其余进 manual_confirm。

### 2. 交叉引用扫描
```bash
python3 $SK/scripts/xref_scan.py 稿件.docx --out /app/work/xref_before.json \
    [--figure-caption below] [--table-caption above]
```
支持 .docx/.md/.txt/.tex。四类机器事故：编号重复、断档、悬空引用、题注错位。
退出码 1 = 有 ERROR。

### 3. 参考文献初筛
```bash
python3 $SK/scripts/refstyle_check.py 稿件.docx --out /app/work/refs_before.json
```
逐条 PASS/WARN/ERROR（缺年份=ERROR）。WARNING 逐条人工定夺：
确认无问题的在 changes 里注明"人工确认无需改"，确认要改的进第 4 步。

### 4. 修正（重编号必须先出方案）
```bash
python3 $SK/scripts/renumber_plan.py /app/work/xref_before.json --out /app/work/renumber_plan.json
```
方案含：题注 old→new 映射、每个正文引用点（块号+上下文）、必须人工裁定的
悬空引用与子编号清单。Agent 按方案**题注+引用点同事务修改**；
参考文献按 refs_before 报告逐条规范。每处修改进 changes（unit/before/after）。

### 5. 重扫验证（留档前后对照）
```bash
python3 $SK/scripts/xref_scan.py /app/output/交付件 --out /app/work/xref_after.json
python3 $SK/scripts/refstyle_check.py /app/output/交付件 --out /app/work/refs_after.json
```
ERROR 未清零不许交付；WARNING 须有逐条处置记录。

### 6. 交付
前后四份报告 + renumber_plan + 修正产物进 /app/output；
result.json 的 changes 引用方案条目，uncertainties 列出人工裁定项。

## 异常处理

| 情况 | 处置 |
|---|---|
| 题注用域代码（SEQ）而非纯文本 | DOCX 抽到的文本仍是渲染值，可扫；修改时按域处理，manual_confirm 声明 |
| 子编号体系（图3-1） | 不重排：renumber_plan 自动跳过并点名，人工核对连续性 |
| 非 GB/T 7714 参考文献（APA 等） | refstyle 降级为通用项检查，limits 声明"著录样式按任务规则人工核" |
| 参考文献节找不到 | refstyle 退化为全文 [n] 行扫描并在报告标注 reference_section_found=false |
| 图是整段图片无文字题注 | 该图无题注可言，进 manual_confirm 人工看图核对 |
| 时间不足 | 骨架 → xref_scan → 修 ERROR → 重扫，最小链先交付 |

## 资源清单（均在 `$SK/` 下）

| 路径 | 作用 |
|---|---|
| `scripts/xref_scan.py` | 题注/引用抽取 + 四类一致性事故检查（DOCX/MD/TXT/TeX） |
| `scripts/refstyle_check.py` | GB/T 7714 形式初筛（类型标志/著录骨架/作者截断/标点） |
| `scripts/renumber_plan.py` | 重编号全量方案（映射+引用点+人工裁定清单） |
| `references/xref-rules.md` | 题注位置惯例、重编号纪律、GB/T 7714 要点 |
| `examples/` | 合成示例：四类缺陷捕获→方案→修正→重扫清零实录 |

## 自查清单（交付前）

1. xref_after.json 0 ERROR；WARNING 逐条有处置记录。
2. refs_after.json 0 ERROR；WARNING 处置进 changes 或 manual_confirm。
3. renumber_plan 的 dangling_refs_manual 与子编号清单全部人工裁定。
4. 前后报告都在 /app/output，可复核"改了什么、为什么"。
