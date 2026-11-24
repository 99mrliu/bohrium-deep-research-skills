---
name: archetype-interpreter
description: 面向「实验结果解释与异常分析」评测的案例原型适配判读 Skill。先识别输入属于哪类案例原型（197 条弯曲力学原始 traces + 工作簿/MATLAB；5 split × 2 estimator 的 Iris 计算实验；Cefixime 12-sheet 主工作簿 + 论文 PDF；或通用兜底），再运行该原型专属的确定性检查，产出数值锚点与契约驱动的 result.json。当任务要求解释实验趋势、定位异常并交付可复核结果时触发。
---

# archetype-interpreter：案例原型适配判读

## 用途与重心

本 Skill 的重心是**案例内容适配**：通用统计管线在真实案例上最常见的失败不是算错，而是「认不出面前是哪种数据」——把 197 条原始曲线当成一张表、把 split×estimator 矩阵当成读数复述、把 12-sheet 工作簿只读第一个 sheet。本 Skill 先做**原型识别**（文件形态 + 关键词 + 结构证据），再运行该原型专属的确定性检查，把判读锚定在脚本可复算的数值上。

**边界**：
- 脚本只做确定性计算与识别；趋势语义、原因推断、后续实验设计由 Agent 在锚点之上完成，且每个数值必须回指 `archetype_findings.json` 或原始文件位置。
- 禁止编造湿实验测量值、重复次数、设备型号或机理原因；观测不到就写 `unknown`。
- 单位/方法/阈值歧义**保留并显式标注**，不静默择一。
- 脚本纯 Python stdlib（xlsx 用 zipfile+xml 只读盘点；PDF 用系统 `pdftotext`，缺失时降级并在 limitations 说明）。

## 运行时契约

- 输入：`/input/case.json`（含 `case_id` 与 `output_contract`）、`/input/task.md`、案例材料；必须读真实文件，不假设预提取答案层。
- 工作目录 `/app/work`；成果目录 `/app/output`，必须含 `result.json`。
- `result.json` 硬性要求：原始 `case_id`、`output_contract` 要求的**全部字段**、诚实 `status`（success/partial/unable_to_determine/refused）、`sources`、`uncertainty`、`change_records`。partial 时 `limitations` 必须精确说明缺哪些字段、为什么。
- 预算：约 64 次模型请求 / 900 秒 / 每响应 16384 tokens。**partial-first**：一键管线的第一步就是落 result.json 骨架，任何时刻中断都有诚实交付。
- 脚本路径以 `/skills/weekly-skill/scripts/` 书写；若安装路径不同，逐字替换前缀。全部脚本 `python3` 直接运行，`--help` 可查。

## 一键管线（推荐主路径）

```bash
python3 /skills/weekly-skill/scripts/run_all.py --input /input --work /app/work --output /app/output
```

产出：
1. `/app/output/result.json` — 契约字段已按脚本可负责部分预填，待撰写字段为 null 并在 limitations 点名；
2. `/app/work/archetype_findings.json` — 原型识别证据 + 全部确定性检查结果（含判定阈值声明）；
3. `/app/work/analysis_anchors.md` — 人读数值锚点，撰写五段结论时直接引用；
4. `/app/output/report.md` — 结构化运行报告。

**Agent 随后必须做的事**（这是质量来源，不可跳过）：
1. 读 `analysis_anchors.md` 与 `task.md`，对锚点中每个离群/饱和/重复对象回原始文件抽查至少 1 例；
2. 撰写脚本标注为待完成的契约字段（趋势语义、可能原因、后续实验建议等）：原因必须给出支持/排除证据与证据强度，复核步骤必须写成第二人可执行的动作（回查哪个文件哪个字段、加做哪组对照）；
3. 用下面的 update 命令填写字段并调整 status；

```bash
python3 /skills/weekly-skill/scripts/result_contract.py update \
  --out /app/output/result.json --status success \
  --set '趋势="...(含数值与定位)..."' --source "traces/S07.txt 峰值行"
python3 /skills/weekly-skill/scripts/result_contract.py check \
  --case /input/case.json --out /app/output/result.json   # 交付前必须通过
```

## 原型与专属检查

| 原型 | 识别依据 | 确定性检查 |
|-|-|-|
| `bending_traces` | ≥30 个两列数值 trace（或 ≥10 且有 .m） | 逐 trace 峰值/峰位/末值/平台段；峰值 IQR×1.5 离群；相同读数连续段≥5 判饱和；内容 sha256 分组判重复曲线 |
| `iris_computational` | 文本含 iris 或 split+estimator | 重构 5×2 数值矩阵；每 estimator 的 mean/std/min/max；逐 split 差与符号一致性 |
| `cefixime_workbook` | 含 cefixime/头孢克肟 关键词，或 xlsx≥8 sheet 且有 PDF | 逐 sheet 盘点（数值/文本单元格数）；PDF 文本与工作簿数值交叉命中；单位记号计数（歧义登记） |
| `generic` | 以上皆非 | 表格列级描述统计；判读主要由 Agent 完成 |

阈值集中声明在 findings JSON 的 `thresholds` 字段，结论中引用阈值时必须带上该定位。

## 异常与失败处理

- 脚本失败：读 stderr → 多为编码/分隔符/表头问题 → 修正对输入的理解后重跑；**不要跳过脚本手算关键数值**。
- 原型识别拿不准：在 `uncertainty` 中写明两个候选原型及各自证据，按证据更强的跑，并对另一原型补做盘点。
- 数据缺失/重复数不足/对照缺失/读数超量程：逐项登记 `limitations`，status 保持 partial，不得把缺口写成结论。
- `pdftotext` 不可用：cefixime 交叉命中自动跳过，limitations 点名。

## 最小示例

`examples/` 内含**合成示例**（非正式案例、非预写答案）：合成 40 条弯曲 trace（含 2 条离群、1 条饱和、1 组重复）+ case.json + task.md，一条命令跑通完整管线。见 `examples/README.md`。
