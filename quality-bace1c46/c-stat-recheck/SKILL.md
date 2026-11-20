---
name: stat-recheck-evidence-auditor
description: 统计复核与审计级证据锚定 Skill。当任务要求对一批科学文献（PDF/文本/仅摘要条目/Crossref 或 EuropePMC JSON 快照）做研究质量评价、且需要核对统计口径并给出可复核证据定位时触发。核心机制：脚本化数字声明采集（n、百分比及其频数语境、p 值、置信区间、均值±SD、中位数(IQR)、t/χ²/F/z 检验统计量与自由度、OR/HR/RR、表格数字块，逐条带页锚与所在原句）；纯标准库一致性重算引擎（频数↔百分比重算、分层求和、摘要↔正文数值指纹配对、p 值近似重算、效应方向核对，三态 pass/discrepancy/not_recomputable）；按文献类型的报告完整性缺口表；归一化子串校验的审计级摘录锚定（含字符偏移）与明文阈值分级。模型仅对脚本标记 needs_semantic 的配对做语境裁决。适用于离线环境、约十篇以内文献的统计报告质量复核。注意：discrepancy 仅表示"报告内部不一致，需人工核对"，不代表论文错误或学术不端；p 值重算为近似实现，精度边界见 rules/recheck_rules.md。
---

# stat-recheck-evidence-auditor：统计复核 + 审计级证据锚定

## 解决的问题

文献质量评价中，"统计口径是否站得住"长期依赖评审经验判断，"证据出自何处"依赖人工标注，二者都难以被第二个人复核复现。本 Skill 把这两件事机械化：

1. **统计复核**：把论文中的数字声明（频数/百分比、样本量分层、p 值、置信区间、效应量方向）抽取出来，用确定性脚本**重算**，给出三态结论。
2. **审计级证据锚定**：每条结论必须挂 verbatim 摘录与页锚，并由脚本做归一化子串校验（报告字符偏移），校验失败整行降级；交付审计复现协议，第二个人可按命令序列逐条重跑复现同一判断。

## 适用条件与边界

- 输入为约十篇以内的科学文献，PDF 为主，允许 .txt/.md、仅摘要条目、Crossref/EuropePMC JSON 快照；全程离线。
- 脚本仅使用 Python 3 标准库（≥3.8）+ subprocess 调 `pdftotext`（带回退）。
- **discrepancy 的含义边界**：discrepancy 只表示"报告内部不一致，需人工核对"，例如频数与百分比不自洽、检验统计量与报告 p 值矛盾。它**不是**对论文正确性的判决，更不是学术不端指控；许多 discrepancy 源于四舍五入口径、笔误或语义配对误差。
- **近似重算的精度边界**：p 值由标准库近似实现重算（t/F 经不完全 β、χ² 经不完全 γ、z 经 erf），绝对误差一般 <1e-9，但报告值本身有舍入，故只在超出明文容差带时标 discrepancy；检验量或自由度缺失一律 `not_recomputable`，绝不硬算。
- 仅摘要文献只能做摘要内复核，汇总标 `limited`，不外推全文结论。

## 输入契约（防御式解析）

`scripts/extract_corpus.py` 按以下规则解析 `/input`，任何缺失都不 crash，只写 `uncertainties`：

- **case_id**：依次尝试 `case_id` / `id` / `caseId`（先顶层后递归）；都不存在用 `unknown_case`。
- **文献清单**：在 case.json 中递归查找 `documents` / `papers` / `references` / `files` / `literature` / `corpus` / `materials` 键下的列表；条目可以是路径字符串或含 path/file/filepath/file_path/filename/local_path/source 与 title/name/label 的对象；相对路径相对 `/input` 解析，失败时按 basename 在 `/input` 递归搜索。清单不命中或条目无路径时，回退扫描 `/input` 下全部 `*.pdf → *.txt → *.md → *.json`（排除 case.json/task.md）。
- **output_contract**：递归查找 `output_contract` / `contract` / `output_fields` / `required_fields`，**原样镜像**进 result.json 的 `output_contract` 字段，其字段名集合展开为 `contract_fields`（脚本可填充的填，不能填的置 null 并记 uncertainty），一个字段都不丢。
- **task.md**：存在则优先作为任务说明来源，复制到 work 目录留存。

## 运行方式总览

六个脚本串行执行，全部重活由脚本完成，不占模型预算：

```bash
python3 /skills/weekly-skill/scripts/extract_corpus.py  --input-dir /input --work-dir /app/work --output-dir /app/output
python3 /skills/weekly-skill/scripts/harvest_numbers.py --work-dir /app/work
python3 /skills/weekly-skill/scripts/recheck.py         --work-dir /app/work
python3 /skills/weekly-skill/scripts/verify_quotes.py   --work-dir /app/work
python3 /skills/weekly-skill/scripts/aggregate_grade.py --work-dir /app/work
python3 /skills/weekly-skill/scripts/build_result.py    --work-dir /app/work --input-dir /input --output-dir /app/output
```

`extract_corpus.py` 在解析完 case.json 后、PDF 抽取前先写部分 result.json（status="in_progress"），保证任何失败点之前已有部分交付。

## 工作流

1. **解析锚定**（extract_corpus.py，0 次模型请求）：防御式解析 → 写部分 result.json → 逐篇抽取分页全文（PDF 用 `pdftotext -layout`，按换页符分页；失败回退 pypdf，再失败标 failed 并继续）→ `pages/<doc_id>.jsonl`、`anchors/<doc_id>.json`、`docs.jsonl`。
2. **数字采集**（harvest_numbers.py，0 次）：正则采集全部数字声明 → `numbers/<doc_id>.jsonl`，每条含 kind、value_fields、所在句（verbatim）、页码、字符 span、匹配片段。
3. **一致性重算**（recheck.py，0 次）：执行 `rules/recheck_rules.md` 全部规则 → `recheck/<doc_id>.jsonl`（三态结论 + 双侧摘录 + computed/reported/tolerance/note）；需要语境确认的配对写入 `semantic_queue/<doc_id>.jsonl`。同时产出报告完整性缺口行（check_type=completeness:*，清单见 `rules/completeness_checklist.md`）。
4. **模型语义裁决**（仅对 needs_semantic 配对）：批处理阅读 semantic_queue 每条的两个摘录，确认"两个数字是否同一指标""两处 n 是否同一总体"等语境问题；把裁决结果追加到对应 recheck 行的 note（并记入 change_log）。**不要**用模型重做机械计算。
5. **缺口表**：completeness 行即缺口表，`absent` 是缺口不是过失，渲染进 recheck_report.md。
6. **门控校验**（verify_quotes.py，0 次）：每条摘录归一化后在所标页做子串匹配并报告偏移；失败整行降级（downgraded=true），写 `verify_report.json`。
7. **分级组装**（aggregate_grade.py + build_result.py，0 次）：按明文阈值映射等级并输出推导；组装终版 result.json，渲染 `/app/output/recheck_report.md`（复核行表+缺口表+等级推导）与 `/app/output/audit_trail.md`（sha256、命令序列、逐行定位）。

## 预算分配（≤60 次模型请求，总预算 64）

- 步骤 1–3、5–7：0 次（纯脚本）。
- 语义裁决：≤20 次。批处理：每条请求打包 ≤10 个 needs_semantic 配对，要求模型逐条给出 confirmed/rejected/unclear 三态。
- 缺口表补充语义判断（如 unclear 项的语境确认）：≤6 次。
- 终稿撰写与自查：≤4 次。
- 余量 ≥30 次留给异常重试。若 semantic_queue 超过预算，按 discrepancy 相关优先、其余保持 pending 并记入 uncertainties。

## 异常处理

- case.json 缺失/损坏：按空配置继续，case_id=unknown_case，记 uncertainty。
- 单篇文献抽取失败：标 failed，继续其余文献；终版 result.json status=partial_failure。
- pdftotext 不可用：回退 pypdf；再失败标 failed。
- 无任何可重算数字：等级 ungradable，仍交付缺口表与审计文件。
- 摘录校验失败：整行降级，discrepancy 按未验证降权计入分级（单独 1 条未验证 discrepancy 不足以升级 concerns，但列入 uncertainties）。
- 任何脚本异常：已写出的部分 result.json 仍在 /app/output，不至于零交付。

## 输出契约

`/app/output/` 下：

- `result.json`：case_id、status、output_contract（原样镜像）、contract_fields（逐字段填充或 null）、statistics_grade（等级+推导+计数）、verification_summary、sources（含 sha256）、uncertainties、change_log、semantic_queue_pending。
- `recheck_report.md`：复核行表（维度—判断—证据—页锚—容差—说明）、完整性缺口表、待裁决队列、等级推导。
- `audit_trail.md`：复现协议——命令序列、输入与中间产物 sha256、每行结论的页码+归一化偏移定位。

## 自查方法

1. `python3 -m py_compile scripts/*.py` 全部通过。
2. 全链路在合成 fixture 上跑通，且至少识别出 1 个 pass、1 个 discrepancy、1 个 not_recomputable（见 examples/example_walkthrough.md）。
3. `verify_report.json` 中 verified_rows == total_rows（除无摘录的缺口行）；否则检查降级行。
4. result.json 含 case_id、output_contract 原样镜像、status、uncertainties、change_log；`python3 -c "import json;json.load(open('/app/output/result.json'))"` 可解析。
5. 抽 3 行 discrepancy/pass，按 audit_trail.md 第 4 节的页码与偏移人工对照原文，确认摘录真实存在于所标位置。
