---
name: rob-signal-dual-adjudicator
description: 文献偏倚风险（Risk of Bias）量表化评价 Skill，适用于对一批科学文献（RCT、观察性研究、诊断准确性研究、系统综述及其他类型）做可复核的方法学质量评价。当任务要求"按文献类型选择偏倚领域、给出四级判定（明确存在/可能存在/未见迹象/证据不足）、附逐字证据与页锚、保留分歧裁决记录、支持人工复核改判"时触发。核心机制：内置偏倚领域集与信号问题树 → 双通道独立初评（通道 P 正向取证 / 通道 N 反向查漏）→ 明文仲裁规则裁决分歧（裁决台账逐条落盘）→ 人工复核改判合并与量表改进建议沉淀 → 领域到整体风险等级的显式映射推导 → 脚本逐字校验全部引用。全程脚本承担解析、候选句召回与引用门控，模型只做判断，适配低模型预算、离线环境。
---

# rob-signal-dual-adjudicator：偏倚风险信号问题双通道裁决评价器

## 解决什么问题

对给定的一批真实科学文献，产出一份**可复核、可复现**的偏倚风险评价表：
每篇文献 × 每个偏倚领域 = 判断（present / likely / no_indication / insufficient）+ 证据（逐字摘录 + 页锚 `p<页>.¶<段>`）+ 推理 + 来源通道 + 裁决记录。
区别于单次通读打分，本 Skill 把偏倚评价拆解为**信号问题树**，用**双通道独立初评 + 明文仲裁**降低单视角漏判，用**引用门控**保证证据真实，用**人工复核入口 + 量表改进建议**让评价系统可持续改进。

## 适用条件

- 输入为 1 篇以上科学文献（PDF / TXT / MD / Crossref 或 EuropePMC JSON 快照）。
- 全程离线；脚本仅使用 Python 3 标准库（≥3.8）+ 外部命令 `pdftotext`（有回退）。
- 模型预算有限（总模型请求 ≤60），重活全部交给脚本。
- 文献类型包括：随机对照试验（RCT）、观察性研究、诊断准确性研究、系统综述/Meta 分析，以及无法归入以上四类的"其他"。

## 输入契约（防御式解析）

`scripts/extract_corpus.py` 按以下顺序解析 `/input/case.json`（任何一步失败都降级而非崩溃）：

1. **case_id**：依次尝试 `case_id` → `id` → `caseId`；都不存在则记 `unknown_case` 并写入 uncertainties。
2. **文献清单**：在 case.json 中**递归查找**键名 `documents` / `papers` / `references` / `files` / `literature` / `corpus` / `materials`；找到的第一个列表（或映射）作为文献清单。每个条目可以是：路径字符串、含 `path`/`file`/`pdf`/`filename` 的对象、含 Crossref/EuropePMC 风格字段（`title`+`abstract`/`abstractText`/`DOI`）的元数据对象（作为 abstract_only 文献落盘为 JSON 快照后处理）。
3. **不命中清单时**：在 `/input` 下按 `*.pdf` → `*.txt` → `*.md` → `*.json`（仅接受含 title/abstract 的快照）顺序收集。
4. **output_contract**：递归查找 `output_contract` / `contract` / `output_fields` / `required_fields`；找到的结构（列表或对象）**全部原样镜像**进 `result.json` 的 `output_contract` 字段，并尽力对每个声明的字段给出真实值（填不出时给 `null` 并在 uncertainties 中说明）。
5. **task.md**：`/input/task.md` 的具体要求优先于本文件默认流程（例如指定了特定领域、特定输出键名时以其为准）；task.md 原文摘要写入 `result.json.task_summary`。

## 运行方式（命令行总览）

所有脚本均为 argparse 入口，路径全参数化。建议按以下顺序执行（工作目录 `/app/work`）：

```bash
# 0. 解析输入、抽取全文（10 秒内先写部分 result.json）
python3 scripts/extract_corpus.py --case /input/case.json --task /input/task.md \
    --input-dir /input --workdir /app/work --output-dir /app/output

# 1. 文献类型判定与领域集选择（纯启发式，不耗模型预算）
python3 scripts/select_domains.py --workdir /app/work

# 2. 信号问题候选句召回（脚本完成，通道 P/N 标签已预打）
python3 scripts/collect_signals.py --workdir /app/work

# 3. 模型双通道初评（人工/模型把判断写入 channel_p 与 channel_n）
#    输入材料：signals/<doc_id>.json + pages/<doc_id>.jsonl（按预算截取）
#    输出格式：见 templates/channel_row.md，每行一个 JSON：
#    {"doc_id":..., "domain":..., "judgment":..., "quote":..., "locator":"p3.¶2", "rationale":...}

# 4. 裁决：合并双通道，分歧按 rules/adjudication.md 明文仲裁
python3 scripts/adjudicate.py --workdir /app/work

# 5. 引用门控：逐字校验所有摘录，失败降级为 insufficient
python3 scripts/verify_quotes.py --workdir /app/work

# 6. 人工复核合并：若 /app/work/review_overrides.jsonl 存在则应用改判
python3 scripts/apply_overrides.py --workdir /app/work

# 7. 组装终版 result.json + 人读版 rob_report.md
python3 scripts/build_result.py --workdir /app/work --output-dir /app/output
```

## 工作流（模型侧操作说明）

### 第 1 步：解析锚定（0 次模型请求）
运行 `extract_corpus.py`。产物：
- `/app/output/result.json`（部分版，`status="in_progress"`，保证任何失败点前已有交付）；
- `docs.jsonl`（每行：doc_id、路径、sha256、词数、分级 `fulltext`/`abstract_only`/`failed`）；
- `pages/<doc_id>.jsonl`（每行 `{"page": n, "text": ...}`，PDF 按 `\f` 分页）；
- `anchors/<doc_id>.json`（每页的段落锚点列表：`p<页>.¶<段>` → 段落文本前 80 字）。

### 第 2 步：类型与领域集选择（0~1 次模型请求/批）
运行 `select_domains.py`，产出 `domain_plan.json`：每篇文献的类型（`rct`/`observational`/`diagnostic`/`systematic_review`/`other`）、命中信号词、置信度（低置信标 `uncertain: true`）、选定领域集。
- 启发式高置信时直接采用；`uncertain` 的文献可花 1 次模型请求批量确认（把多篇的标题+摘要前 200 词放进同一次请求）。
- 领域集定义见 `domains/`：common 为所有类型共用（结果选择性报告、统计方法适用性、资助与利益冲突），类型特有领域见各自文件。

### 第 3 步：双通道独立初评（核心模型预算）
运行 `collect_signals.py` 得到 `signals/<doc_id>.json`：每个领域 × 信号问题召回的候选句（含页锚、命中关键词、预打通道标签 P/N）。
- **通道 P（正向取证）**：从方法/结果章节的候选句出发，对每个领域判断偏倚是否**有明文证据**，产出领域级判断 + 逐字摘录 + 页锚。
- **通道 N（反向查漏）**：从局限段、表格注释、摘要与正文差异、候选句中的"未报告/not reported/缺失"线索出发，专找未报告项与矛盾，**独立**产出判断。
- 两通道输出分别写入 `channel_p/<doc_id>.jsonl` 与 `channel_n/<doc_id>.jsonl`（格式见 `templates/channel_row.md`）。
- 模型每次只判断脚本召回的候选句窗口，不做全文漫游。

### 第 4 步：裁决（0 次模型请求）
运行 `adjudicate.py`：
- 两通道一致 → 直接定级，记 `agreement`；
- 分歧 → 按 `rules/adjudication.md` 仲裁：方法学明文描述 > 结果/表格暗示 > 无报告即 `insufficient`；无法裁决取**较高风险级**并标 `adjudicated_conservative`；
- **全部分歧与裁决理由写入 `adjudication_ledger.jsonl`，永不静默抹平**。

### 第 5 步：引用门控（0 次模型请求）
运行 `verify_quotes.py`：归一化（去空白换行、去连字符断行、全半角折叠）后做子串匹配；所标页找不到则全文找并在 `verify_report.json` 报告实际页；仍找不到 → 该条判断降级为 `insufficient` 并记录 `quote_verification_failed`。

### 第 6 步：人工复核合并
若 `/app/work/review_overrides.jsonl` 存在（格式见 `templates/override_format.md`），运行 `apply_overrides.py`：合并改判、在 result.json 记录 `overrides_applied`，并生成 `scale_revision_suggestions.md`——统计哪些信号问题反复分歧/被人工改判，给出量表措辞或阈值的修订建议（沉淀机制，非一次性修补）。

### 第 7 步：分级组装
运行 `build_result.py`：按 `rules/judgment_levels.md` 的领域→整体映射表显式推导整体风险等级（写入推导过程，禁止孤立等级），输出终版 `result.json` 与人读版 `/app/output/rob_report.md`。

## 预算分配（总模型请求 ≤60，以 9 篇文献为例）

| 用途 | 请求数 |
|---|---|
| 类型确认（仅 uncertain 文献，批量） | 0–2 |
| 通道 P 初评：每篇 1 次（fulltext）/ 摘要级文献两篇合并 1 次 | 6–9 |
| 通道 N 初评：同上 | 6–9 |
| 裁决后仍存疑领域的补充判断（少量） | 0–3 |
| 备用（重试、task.md 附加要求） | 5 |
| **合计** | **≤30**，留足余量 |

- 单次响应 ≤16384 token：每篇文献的通道请求只放该篇 signals 候选句（通常 <40 条）+ 必要页文本截段，输出 JSONL 控制在 4000 token 内。
- 摘要级（abstract_only）文献：两通道可在同一请求内完成，且多数领域只能判 `insufficient`——这是诚实结论而非缺陷。

## 异常处理

- **零文献**：`docs.jsonl` 为空 → result.json 写 `status="completed_with_warnings"`、`documents: []`、uncertainties 说明，正常结束。
- **case.json 解析失败**：按无清单模式扫 /input；仍无文献则同上。
- **PDF 提取失败**：先 `pdftotext -layout`，失败回退 Python 内 pypdf（若可导入），再失败标 `failed` 并继续下一篇。
- **仅摘要条目**：分级 `abstract_only`，领域判断默认 `insufficient`（除非摘要明文给出证据），整体等级至多 `some_concerns` 的推导被禁止——无全文时整体等级输出 `insufficient_evidence`。
- **图表不可解析**：pdftotext 不提取图像；涉及纯图表证据的领域按"证据不足"处理并写入 uncertainties。
- **预印本/缺元数据**：正常评价，在 `documents[].notes` 标注"预印本未经同行评审"或"元数据缺失"。
- **关键证据缺失**：判 `insufficient`（弃权），绝不默认 `no_indication`。

## 输出契约

`/app/output/result.json` 必含：
- `case_id`（防御式解析所得）；
- `output_contract`：镜像 case.json 中声明的全部原始字段；
- `status`：`in_progress` / `completed` / `completed_with_warnings` / `failed`；
- `documents[]`：每篇含 doc_id、类型、领域评价（判断/证据/页锚/通道/裁决标记）、领域级等级、整体等级与映射推导；
- `adjudication_summary`、`quote_verification`、`overrides_applied`、`uncertainties`、`change_log`；
- 全部日期、脚本版本、文档 sha256 可溯源。

## 自查方法

1. `python3 -m py_compile scripts/*.py` 全过；
2. 用合成 fixture 跑通 extract → select → collect → adjudicate → verify → overrides → build 全链路（见 README.md 自测节）；
3. 抽查 `verify_report.json`：`failed` 必须为 0 或每条失败均已降级；
4. 抽查 `adjudication_ledger.jsonl`：每条分歧有 `rule_applied`；
5. 随机抽 3 条判断，按页锚回到 `pages/*.jsonl` 人工核对摘录逐字一致。
