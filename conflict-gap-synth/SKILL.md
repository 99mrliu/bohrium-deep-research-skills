---
name: conflict-gap-synth
description: 深度研究的"冲突证据与研究空白"分析器——把各研究提取到统一比较矩阵（设计类型、样本量、人群/体系、指标、效应方向、量级、局限），自动检出效应方向相互冲突的研究对并生成冲突登记表（并置呈现双方证据，按设计层级/样本量/一致性给出裁定依据而非和稀泥）；结论按 A/B/C/D 证据强度分级；研究空白从覆盖矩阵导出（检索了未见=高置信缺口，未检索=不下结论），最终综合文本逐句标注[事实]/[推断]/[无法确定]。Use when a task asks to synthesize conflicting literature findings, grade evidence strength, analyze research gaps from coverage, or produce bounded conclusions in a literature review (冲突证据, 证据分级, 研究空白, 证据综合, bounded synthesis).
---

# 冲突证据与研究空白分析器（conflict-gap-synth）

## 何时使用

案例给出研究问题与若干文献/材料，要求形成综合结论、处理相互矛盾的研究结果、评估证据强度或指出研究空白时，使用本 Skill。典型平台场景：`/input/case.json` + `/input/task.md` + 材料文件，结果写入 `/app/output`（含遵守 `output_contract` 的 `result.json`）。本 Skill 的核心增益在综合侧：冲突不被"尚存争议"一句话抹平，空白不凭印象写，每条结论都有强度等级与边界。

## 运行方式（三步）

```bash
# 1) 生成比较矩阵、冲突登记、分级与空白的全套骨架（先产出 partial result.json）
python3 /skills/weekly-skill/scripts/run_case.py \
    --case /input/case.json --input-dir /input \
    --work /app/work --out /app/output

# 2) 逐篇录入研究字段（Agent 从检索结果/材料提取；脚本做模式校验）：
python3 /skills/weekly-skill/scripts/matrix.py add \
    --matrix /app/output/study_matrix.json \
    --study "Zhang et al. 2023" --design rct --n 128 \
    --population "II型糖尿病成人" --topic 运动干预 \
    --outcome HbA1c --direction positive --magnitude "-0.6%" \
    --limits "随访仅12周" --source "DOI:10.xxxx/yyyy"

# 3) 检出冲突、生成空白分析、分级并收尾：
python3 /skills/weekly-skill/scripts/conflicts.py \
    --matrix /app/output/study_matrix.json \
    --out /app/output
python3 /skills/weekly-skill/scripts/finalize.py \
    --case /input/case.json --work /app/work --out /app/output
```

## 流水线做了什么（每步都可重跑）

1. **比较矩阵（matrix.py）**：每篇研究一行，字段固定为 design（rct/meta/cohort/review/opinion/n/a）、n、population、topic、outcome、direction（positive/negative/mixed/none）、magnitude、limits、source。录入即做模式校验：design 必须是枚举值，direction 必须是四值之一，缺 source 拒绝入库——不允许"某文献说"式的无源行。
2. **冲突检出（conflicts.py）**：在同一 (topic, outcome) 单元内，direction 互斥（positive vs negative、或 positive/negative vs none 且双方均声称有效检验）的研究对进入 `conflict_register.json`。每对冲突必须填写 `adjudication`：依据设计层级、样本量与方向一致性给出"当前证据更支持哪方/仍无法裁定"，禁止输出"双方都有道理"式空话；无法裁定时写明还缺什么证据。
3. **证据分级（finalize.py）**：综合结论自动携带 A/B/C/D 等级——A：≥2 项原始数据研究且方向一致；B：1 项原始数据研究，或仅综述但多篇一致；C：仅综述/观点或单项小样本；D：无法确定。等级与理由写入 `evidence_grades.json`。
4. **空白导出（finalize.py）**：任务拆解出的子问题 × 比较矩阵的覆盖情况生成 `gap_analysis.json`。某子问题方向有检索动作但矩阵中无任何研究 = `searched_but_absent`（高置信缺口）；只有部分子问题有研究 = `partially_covered`；完全未检索 = `not_searched`（不下结论）。空白句必须引用该字段，否则按 D 级处理。
5. **边界综合文本**：`bounded_synthesis.md` 骨架要求逐句前缀 `[事实]/[推断]/[无法确定]`；冲突对并置两段并给出裁定依据；结论段每条末尾带等级（A/B/C/D）与矩阵行号引用。

## 输入 / 输出

- 输入：`case.json`（含 `case_id`、`output_contract`）、`task.md`、材料文件。
- 输出（`/app/output`）：`result.json`（遵守 `output_contract` + 原始 `case_id`，含诚实 `status`/`sources`/`uncertainty`）、`study_matrix.json`、`conflict_register.json`、`evidence_grades.json`、`gap_analysis.json`、`bounded_synthesis.md`、`run_manifest.json`。

## 依赖与异常处理

- 仅依赖 Python 3 标准库；全部确定性脚本。
- 检索为空导致矩阵无行：finalize 产出全缺口分析并标 `partial`，不虚构研究行。
- 录入行校验失败：拒绝入库并逐字段报告错误；Agent 修正后重试。
- 冲突对 adjudication 为空：finalize 拒绝写 success，强制先补裁定依据。
- 矩阵中同一 (study, topic, outcome) 重复录入：拒绝并提示去重。
- result.json 从第 1 步起存在；任何中断都留下矩阵与部分分析。

## 不适用边界

- 不做检索本身与单篇精读（相邻环节）；本 Skill 消费检索产物并强制结构化。
- 不对材料未覆盖的主题下任何结论；未覆盖一律 D 级 + not_searched。
- 不预制答案；矩阵行必须由本次检索/材料实际提取。

## 复跑方法

保留 study_matrix.json 与任务文本，重跑 conflicts.py + finalize.py，冲突对、等级与缺口分类完全确定地复现；他人可在自己的检索结果上复用同一矩阵模式与分级规则。

## 最小调用示例（示意输出，非正式案例结果）

```bash
python3 /skills/weekly-skill/scripts/run_case.py --case /input/case.json \
  --input-dir /input --work /app/work --out /app/output
# {"ok": true, "scaffold": ["study_matrix", "conflict_register", ...], "studies": 0}
python3 /skills/weekly-skill/scripts/matrix.py add --matrix /app/output/study_matrix.json \
  --study "Zhang et al. 2023" --design rct --n 128 --population "T2DM成人" \
  --topic 运动干预 --outcome HbA1c --direction positive --magnitude "-0.6%" \
  --limits "随访12周" --source "DOI:10.xxxx/yyyy"
# {"ok": true, "row": 1}    ← 示例值
python3 /skills/weekly-skill/scripts/conflicts.py --matrix /app/output/study_matrix.json \
  --out /app/output
# {"ok": true, "conflict_pairs": 0, "topics": 1}   ← 示例值
python3 /skills/weekly-skill/scripts/finalize.py --case /input/case.json \
  --work /app/work --out /app/output
# {"ok": true, "status": "partial", "gaps": {...}, "grades": {...}}   ← 示例值
```

以上输出为接口示意；正式运行以平台 3 个固定案例的实际矩阵与冲突为准。
