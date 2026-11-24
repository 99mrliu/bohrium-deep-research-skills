---
name: material-forensics-registry
description: 文献证据驱动写作——上游材料取证与来源登记。当任务以 /input 下的科研材料（PDF/文本/case.json）为依据进行学术写作、改稿或证据表编制时使用。本 Skill 的重心在"写作开始之前"：用确定性脚本对全部输入材料做哈希登记、文本层提取质量探测、case.json 声明与实际文件对账，把每个来源分级为 OK/DEGRADED/UNUSABLE，并为后续引用提供逐字定位与真实页码回填能力。解决的问题：基础 Agent 常凭文件名推断材料内容、引用不存在的页码、把提取失败的 PDF 当成已读。本 Skill 保证只有经过取证登记、质量合格的来源才能进入证据链。
---

# 材料取证与来源登记（Material Forensics & Source Registry）

## 这个 Skill 解决什么问题

文献证据驱动写作的第一处失真发生在**读材料**这一步：PDF 文本层为空却被当成已读、扫描件被凭空"引用"、页码凭印象编、case.json 声明的材料与实际文件对不上。本 Skill 把写作前的材料处理变成一条可复现的取证流水线：每个文件留 SHA-256 指纹、提取质量分级、声明对账，任何来源的可用性都有据可查。后续所有论断只能建立在 OK 级来源上，DEGRADED 级来源必须带质量受限标注。

## 何时使用

- 输入为 `/input/case.json` + `/input/task.md` + 若干文献材料（PDF 为主），任务要求依据材料写作并保留来源；
- 材料数量多、格式杂，或存在扫描件/损坏文件的可能；
- 评分或任务要求"论断可回溯到具体文献具体段落（含页码）"。

不适用：无来源材料的纯创作；材料已全部是可信纯文本且无需页码定位（此时本 Skill 退化为一次快速登记，仍可运行）。

## 运行契约

- 输入：`/input/case.json`、`/input/task.md`、材料文件。先读实际文件内容，不得从文件名或标签推断内容。
- 工作区：`/app/work`（中间产物）；最终产物与 `result.json` 放 `/app/output`。
- `result.json` 必须含原样 `case_id` 与 `output_contract` 声明的全部键；材料缺失、质量降级、无法判断分别写入 `limits`/`uncertainty`，状态如实标 `partial`。
- 预算意识：先跑取证脚本（秒级、不耗模型请求），再按报告规划阅读；尽早保存可用的 partial 产物，再逐步完善。

## 依赖

- Python ≥3.9 标准库；PDF 提取用系统 `pdftotext`（poppler）。`pdftotext` 不可用时脚本将 PDF 标为 UNUSABLE 并继续，不中断流程。
- 脚本：`scripts/material_forensics.py`（取证+登记）、`scripts/locate_quote.py`（摘录逐字定位+页码回填）。

## 工作流（严格按序执行）

**步骤 0 — 读任务，建工作区**
```bash
mkdir -p /app/work /app/output
python3 -c "import json;d=json.load(open('/input/case.json'));print(sorted(d.keys()))"
cat /input/task.md
```
记录 `case_id`、`output_contract` 全部键名（原样照抄，后续 result.json 要用）、体裁与受众。

**步骤 1 — 材料取证（脚本，不用模型读文件）**
```bash
python3 /skills/weekly-skill/scripts/material_forensics.py /input /app/work --case /input/case.json
```
- 读 `/app/work/material_report.md`：确认每个来源的处置（OK/DEGRADED/UNUSABLE）与原因；
- 读 `/app/work/sources_registry.json` 的 `declared_hints`：把 case.json 声明而缺失、存在而未声明的材料写入 limits；
- 退出码为 1（零可用来源）时：停止写作，按 `references/forensics_policy.md` 第 4 节产出 honest-failed 的 result.json，说明原因与需要的人工处置。不得改用"按常识写作"。

**步骤 2 — 针对性阅读（模型）**
只读 OK 级来源的提取文本（`/app/work/text/<stem>.txt`）。用 `grep -n` 定位关键词、`sed -n` 取段，不要整篇塞入上下文。DEGRADED 来源仅用于了解大意，其支撑的事实句必须标注〔材料质量受限〕。

**步骤 3 — 证据摘录与定位（模型摘录 + 脚本核验）**
每条证据必须是一段**连续原文摘录**（quote，25–300 字符）。把 quote 存入临时文件后核验：
```bash
printf '%s' '摘录原文' > /app/work/q.tmp
python3 /skills/weekly-skill/scripts/locate_quote.py /app/work /app/work/q.tmp --source <stem>
```
- `found=true`：采用返回的真实 `page` 回填证据表；
- `found=false`：按 `references/forensics_policy.md` 第 3 节修正摘录（常见原因：跨页断行、pdftotext 的 -layout 空格、Unicode 全半角）后重试；仍失败则该证据只能以〔转述未锚定〕形式进入 change_log，不得作为逐字证据。

**步骤 4 — 证据表与成稿（模型）**
- `/app/output/evidence_table.md`：证据编号｜论断｜来源（registry 中的 file + sha256 前 8 位）｜页码｜摘录｜材料质量（OK/DEGRADED）；
- `/app/output/deliverable.md`：按 task.md 体裁写作。只有定位核验通过（found=true）的证据才能支撑事实句；来自 DEGRADED 来源的句子带〔材料质量受限〕；UNUSABLE 来源的内容不得出现。

**步骤 5 — 组装 result.json**
按 `output_contract` 的键逐一填充；另附：`status`（complete/partial/failed）、`sources`（抄 sources_registry.json 的记录，含 sha256）、`uncertainty`、`change_log`、`limits`（材料缺口、降级、声明对账差异）。每个键的值指向 /app/output 下真实存在的文件或内联文本，不引用不存在的文件。

**步骤 6 — 自查（最后一步）**
逐项核对：①每个来源的 sha256 已登记；②每条证据的页码来自 locate_quote.py 输出而非估计；③DEGRADED/UNUSABLE 处置与报告一致；④声明对账差异已写入 limits；⑤case_id 与 output_contract 键名原样。

## 异常处理

完整异常矩阵见 `references/forensics_policy.md` 第 4 节。要点：pdftotext 缺失 → 该 PDF 标 UNUSABLE 并在 limits 说明，不中断其他材料；case.json 缺 `case_id` → result.json 中填 `"unknown"` 并在 limits 记录；材料零可用 → honest-failed，不编造内容。

## 最小调用示例（合成示例，非正式案例结果）

`examples/` 下含 3 份合成来源文本（含 1 份刻意损坏编码的文件）与合成 case.json。执行：
```bash
python3 scripts/material_forensics.py examples/input /tmp/mf-work --case examples/input/case.json
printf '%s' '治疗后 8 周，试验组空腹血糖较基线下降 1.8 mmol/L' > /tmp/q.tmp
python3 scripts/locate_quote.py /tmp/mf-work /tmp/q.tmp --source sources_paper_a
```
第一条命令输出 2 OK / 1 DEGRADED 的登记摘要；第二条命中 sources_paper_a 第 1 页。完整输入、命令与真实输出见 `examples/minimal_example.md` 与 `examples/output/`。

## 限制与维护

- 本 Skill 保证"来源真实、提取质量已知、摘录逐字可定位"，不判断语义上是否真正支持论断——支撑关系由模型在证据表中判定并给理由。
- 扫描件无文本层时需要 OCR；OCR 结果按 DEGRADED 处理并注明。
- 规范化规则集中在 `locate_quote.py` 的 normalize()；新增材料格式在 `material_forensics.py` 的 TEXT_EXTS 与提取分支中扩展；分级口径集中在 `references/forensics_policy.md`。
