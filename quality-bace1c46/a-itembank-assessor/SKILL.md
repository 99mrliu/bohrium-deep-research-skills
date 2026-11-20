---
name: design-typed-itembank-assessor
description: 量表驱动的研究设计分型条目化文献质量评价。当任务要求对一批科学文献（PDF/文本/元数据快照）产出"维度—判断—证据—等级"的可复核评价表（而非摘要复述）时使用：脚本先离线抽取分页文本并用关键词启发式识别研究设计类型（RCT、队列、病例对照、横断面、诊断准确性、系统综述/Meta、其他），再按设计类型从内置条目库匹配检查条目（五大通用维度 + 类型特有检查点），按条目做 met/partial/not_met/not_assessable 四态判断并强制 verbatim 摘录与页码锚点，最后经归一化引用门控校验（失败自动降级）和明文阈值聚合出 high/moderate/low/ungradable 等级及推导链。适用于离线、有限模型预算下的多文献研究质量评价、偏倚风险初筛、报告完整性核查；不适用于单篇深度统计复算（数字重现、效应量重算）、需要全文图片/表格深度解读的场景，也不与"偏倚风险双评仲裁""统计数值复核"类 Skill 重叠。
---

# design-typed-itembank-assessor：量表驱动的研究设计分型条目化评价

## 一、解决什么问题

给定约 9 篇真实科学文献（PDF 为主，可能混有仅摘要条目、缺元数据条目、
Crossref/EuropePMC JSON 快照），在离线、64 次模型请求、900 秒的预算内，产出
**"维度—条目—判断—证据—等级"完整评价表**：每条判断附逐字摘录与页码锚点，
等级由明文阈值推导并给出推导链，使第二个人可以按记录逐条复核并复现同一判断。
本 Skill 不做摘要复述，不做统计数值重算，不做双人独立评价仲裁。

## 二、适用条件

- 输入目录（默认 `/input`）含 `case.json` 与 `task.md`，文献按 case 指定或在输入目录下。
- 环境有 `pdftotext`（无则自动回退 pypdf，再失败标记 failed，不崩溃）。
- 脚本仅用 Python 3 标准库（≥3.8），无网络。
- 不适用：需要阅读图表像素内容（OCR 不可用时对应条目弃权）、纯非中英文献
  的高置信判断（降级处理并注明）。

## 三、输入契约（防御式解析，extract_corpus.py 已实现）

1. `case_id`：在 case.json 中依次尝试 `case_id` / `id` / `caseId`（递归查找）。
2. 文献清单：递归查找 `documents` / `papers` / `references` / `files` /
   `literature` / `corpus` / `materials`；元素可以是路径字符串，也可以是含
   `path` / `file` / `pdf` / `url` / `title` 键的字典；URL 在离线环境不可达，
   若条目内联摘要则降级为 abstract_only，否则记入 uncertainties。
   清单缺失时：在输入目录按 `*.pdf → *.txt → *.md`（附 `*.json` 快照）收集。
3. `output_contract`：递归查找 `output_contract` / `contract` / `output_fields` /
   `required_fields`，**原样镜像**进 result.json；其字段名预置为顶层键，
   有产出填值、无产出填 null 并在 uncertainties 说明。
4. `task.md` 的具体要求**优先于**本通用流程：先读 task.md，若指定了
   额外维度、特定文献子集或输出字段，以 task.md 为准调整条目选择与结果组装。

## 四、运行方式（命令行总览）

所有路径参数化，默认值为评测环境路径（`/input`、`/app/work`、`/app/output`）：

```bash
# 阶段1 解析锚定（10 秒内先写部分 result.json）
python3 scripts/extract_corpus.py --case /input/case.json --task /input/task.md \
    --input-dir /input --work /app/work --output /app/output
# 阶段2 设计分型
python3 scripts/classify_design.py --work /app/work
# 阶段3 条目候选抽取
python3 scripts/match_evidence.py --work /app/work --top-n 5
# （模型批阅：读 candidates/*.json，回原文核对，写 assessments/<doc_id>.jsonl）
# 阶段4 门控校验 → 聚合分级 → 组装交付
python3 scripts/verify_quotes.py --work /app/work
python3 scripts/aggregate_grade.py --work /app/work
python3 scripts/build_result.py --case /input/case.json --work /app/work --output /app/output
```

## 五、四阶段工作流

### 阶段 1：解析锚定（脚本，0 次模型请求）
运行 extract_corpus.py。产出 `pages/<doc_id>.jsonl`（分页文本）、
`anchors/<doc_id>.json`（`p<页>.¶<段>` 锚点表）、`docs.jsonl`（doc_id、sha256、
词数、fulltext/abstract_only/failed 分级、解析方式）。**先在 /app/output 写入
status=in_progress 的部分 result.json**，任何后续失败都已有交付物。
随后快速浏览 docs.jsonl 与 task.md，确定每篇文献的层级与评价范围。

### 阶段 2：分型与条目匹配（脚本 + 少量模型确认）
运行 classify_design.py 得 design.json（design_type、confidence、matched_signals）。
- `uncertain=true` 的文献：由模型读摘要/方法段开头裁决类型；若修正脚本结论，
  写 `/app/work/design_overrides.json`（留痕进 change_records）。
运行 match_evidence.py 得 `candidates/<doc_id>.json`：每个适用条目
（通用 10 条 + 类型特有 4–7 条）附 top-5 候选段落（页锚 + 命中词）。
**候选仅用于定位，判断必须回到 pages 原文核对。**

### 阶段 3：条目判断与摘录（模型主战场）
按 `templates/assessment_row.md` 格式为每个条目写一行 JSON 到
`/app/work/assessments/<doc_id>.jsonl`：
- 四态判断（定义见 `rules/evidence_rules.md`）；met/partial/not_met 必须附
  **逐字摘录 + 页锚**；not_assessable 可无摘录但须一句话说明弃权理由。
- 摘录从 pages/<doc_id>.jsonl 逐字复制（允许去换行/连字符断词/多余空白）。
- 理由一句话，禁止长段复述。

### 阶段 4：门控校验与分级组装（脚本，0 次模型请求）
verify_quotes.py 归一化校验每条摘录是否真实出现在所标页（失败尝试全文定位并
报告实际页），失败者就地降级为 not_assessable，输出 verify_report.json 与
assessments_verified/。aggregate_grade.py 按 `rules/grading_thresholds.md`
明文阈值输出等级与推导链（哪些条目触发哪条规则）。build_result.py 组装终版
`/app/output/result.json`（case_id、镜像契约字段、status、sources、uncertainties、
change_records、评价表、校验摘要）并渲染人读版 `/app/output/assessment_table.md`。

## 六、预算分配建议（总量 ≤60 次模型请求，留 4 次余量）

| 阶段 | 用途 | 请求上限 |
|---|---|---|
| 0 | 读 task.md + docs.jsonl + 本 SKILL 流程规划 | 2 |
| 2 | 低置信分型裁决（每篇 ≤1 次，可多篇合并） | 4 |
| 3 | 条目判断：每篇文献 2–3 次（通用条目 1 次 + 类型条目 1 次 + 补查 1 次），9 篇 | 40 |
| 3.5 | 门控失败后的补救重判（如需） | 6 |
| 4 | 终版 result.json 复查与 uncertainties 补记 | 4 |

技巧：单篇文献的通用条目判断可合并在一次请求内完成（候选句已由脚本预筛）；
不要逐条摘录原文长段——只复制支撑句。

## 七、异常处理（全部写入 status/uncertainties，不编造）

| 异常 | 处置 |
|---|---|
| 零文献 | status=failed；result.json 仍落盘，uncertainties 记录"未发现文献材料" |
| 全部解析失败 | status=failed 或 partial；每篇记 failed 原因（pdftotext/pypdf 均失败等） |
| 仅摘要可得 | tier=abstract_only；方法学条目判 not_assessable 并注明；等级封顶 moderate（规则 R5） |
| 图表不可解析 | 依赖该图表的条目判 not_assessable，注明"图表内容不可解析" |
| 非中英文献 | 照常分型与判断，置信降低，uncertainties 注明语言限制 |
| 预印本 | 照常评价，uncertainties 注明"未经同行评审" |
| 关键证据缺失 | 区分 not_met（有证据表明未做到）与 not_assessable（无证据可判断），不混用 |
| URL 条目离线不可达 | 有内联摘要则 abstract_only；否则记 uncertainties 并跳过 |

## 八、输出契约

`/app/output/` 下：
- **result.json**（必须）：字段见 `templates/result_fields.md`——case_id、status、
  output_contract 原文镜像及其字段顶层键、documents（每篇：分型+置信+信号、
  等级+推导链+统计、条目判断数组含 quote/locator/rationale/verification）、
  sources、uncertainties、change_records、verification_summary、artifacts。
- **assessment_table.md**：人读评价表（维度—条目—判断—证据（摘录+页锚）—等级—推导）。
- **verify_report.json**：门控校验报告（随交付）。

## 九、自查方法（提交前必做）

1. `python3 -m py_compile scripts/*.py` 全部通过。
2. 全链路冒烟：用合成 fixture（1 个 case.json + 1 个 txt + 1 个 Crossref 风格
   JSON + 手写 assessments jsonl）跑 extract→classify→match→verify→aggregate→build，
   确认 result.json 与 assessment_table.md 生成、status 合理。
3. 抽查 2 条 met 判断：把 quote 归一化后与所标页文本比对（verify_report 中
   status=ok 即已自动完成）。
4. 核对每篇文献的 derivation：等级必须由 R0–R6 规则推出，无孤立标签。
5. 确认 output_contract 字段全部镜像；无产出字段为 null 且 uncertainties 有说明。
