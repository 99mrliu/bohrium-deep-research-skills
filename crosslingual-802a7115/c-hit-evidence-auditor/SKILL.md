---
name: xlang-hit-evidence-auditor
description: 对跨语言文献检索的候选命中做逐条误译复核与证据对齐审计。当任务要求说明每条命中为什么相关、命中的是原文哪个用词（带文件＋字段/行号定位的原文引文）、识别"词面对应、语义不同"的机翻假阳性（译文用词与论文原文用词对不上）、或对高风险命中做回译复核并留下可人工复核的判定依据时使用；适用于 /input/case.json + task.md 的 Harbor 运行契约，也适用于任何"查询概念＋候选命中记录"的跨语言对齐审计。本 Skill 只管命中后的验证阶段，不做查询扩展、检索或版本归并。
---

# 命中级误译复核与证据对齐审计（xlang-hit-evidence-auditor）

## 用途与适用条件

对**已检索出的候选命中**逐条验证：把 case.json 中的查询概念对齐到每条命中记录的**原文实际用词**，引用原文片段并给出可回指的定位（文件＋字段/JSON 路径/行号/字符偏移）；用确定性启发式把命中分为 high/medium/low 三档假阳性风险；对高风险全检、中风险抽样、低风险记录免检理由，生成**回译复核任务清单**；读回复核结论时强制校验判定依据（凡 confirmed/false_positive 必须有非空 basis，否则报错拒绝落盘），最终产出逐命中证据台账与统计。

分工边界（必须知悉）：

- **脚本做**：异构文件发现与解析、表面匹配（变音/大小写折叠、中英混排边界）、引文截取与定位、wording_mismatch 等风险标记、风险分级、抽检分层、队列生成、判定依据完整性校验、台账汇总与统计。脚本**不做机器翻译**、不做语义判读、不替 Agent 下复核结论。
- **Agent 做**：按 `rules/audit_policy.md` 第 3 节检查清单对队列中的每条执行受控回译（把命中术语回译到查询语种、比对语义一致性），填写 `review` 块（verdict/basis/back_translation）。低预算下必须按分层抽检执行，**不得**对每条命中都发起一次模型调用。

不适用：从头检索、查询改写、跨库去重与版本归并（这些是其他方向的事）；本 Skill 的输入是"已有候选命中"的场景。

## 输入

- `/input/case.json`：案例文件，含 `case_id`、研究问题（`research_question`/`question`/`task`）、查询概念（`query_concepts`/`concepts`：字符串列表、按语种词形表 `{"pt": [...], "en": [...], "zh": [...]}`、或含 `forms` 与可选 `context_terms` 的对象列表）、`output_contract`。无结构化概念时回退提取研究问题中的引号短语并如实记入 uncertainty。
- 候选命中记录：自动发现 `/input`、`/app/work`、当前目录及 `--roots` 指定目录下的 `.json/.jsonl/.csv/.txt/.md`（异构容错：JSON 递归识别含 title/abstract/body/snippet 等键的记录；JSONL 逐行；CSV 按列名；TXT/MD 整文件为一条正文记录——pdf-text-tool 的解析文本即按此处理，**按实际内容判断、不按文件名标签假设**）。记录自带 `text_file`/`body_file` 指针时加载对应正文文件。
- 回译复核结论：Agent 填写后的 `/app/work/backtranslation_queue.json`（ingest 阶段输入）。

## 调用方式（按顺序执行）

```bash
# 1. 证据对齐：概念 → 原文实际用词，生成台账初稿
python3 scripts/evidence_align.py --case /input/case.json --workdir /app/work

# 2. 风险分级 + 生成回译复核任务清单（含空判定模板）
python3 scripts/risk_triage.py triage --ledger /app/work/evidence_ledger.json --workdir /app/work

# 3. Agent 按 rules/audit_policy.md 第 3 节清单逐条复核，填写 queue 中各 item 的 review 块
#    （高风险全检、中风险已抽样的条目；每条约 1 次模型请求，可多条合并一次请求）

# 4. 读回复核结论：校验依据完整性，合并台账，写 /app/output
python3 scripts/risk_triage.py ingest --ledger /app/work/evidence_ledger.json \
    --queue /app/work/backtranslation_queue.json --out /app/output --case /input/case.json
```

可选参数：evidence_align 的 `--roots dir1,dir2`（追加语料根）、`--hits file1,file2`（显式命中文件）；triage 的 `--rules rules.json`（覆盖风险规则）、`--medium-sample`（中风险抽样比例，默认 0.5）、`--max-queue`（队列上限，默认 20，适配 64 次模型请求预算）。

## 输出

- `/app/work/evidence_ledger.json`：逐命中台账（命中 ID、语种〔自报/启发式识别分列〕、版本、DOI、来源、定位；逐概念的 matched_forms〔词形、词形语种、字段、原文引文 quote/quote_context、span、line、locator〕、wording_mismatch、flags）。triage 后追加 risk/risk_reasons/review。
- `/app/work/backtranslation_queue.json`：复核任务清单（每条的待回译术语、原文片段、target_lang、空 review 模板、budget 提示）。
- `/app/output/audit_ledger.json`（最终台账）、`audit_stats.json`（风险档分布＋复核统计）、`result.json`（case_id、status、hits、risk_distribution、review_stats、sources、uncertainty、change_records，并镜像 output_contract 全部字段）。
- 运行日志：`/app/work/evidence_align_log.json`、`/app/work/risk_triage_log.json`。

## 关键方法（详见 rules/audit_policy.md）

1. **证据对齐**：Unicode NFKD＋去组合符（变音折叠，如 ã→a）＋casefold 后做子串匹配；拉丁词形要求词边界，CJK 字符在中英混排中视为天然边界，CJK 词形不要求边界；命中跨度经归一化索引映射还原为原文偏移，截取引文（±80 字符上下文）并给出字段/行号定位。译文用词与原文用词不一致（记录语种在概念词形表中有对应词形但该语种词形零命中、仅靠其他语种词形命中）显式标注 `wording_mismatch`。
2. **风险分级**（确定性，规则可配置）：high = wording_mismatch / 仅缩写命中（跨语种缩写歧义）/ 全部概念无原文表面命中 / 仅二手转述；medium = context_terms 缺位（词面对应上下文存疑）/ 仅标题命中 / 词形过短 / 概念部分覆盖 / 译本记录 / 语种不确定；low = 原文语种词形直接命中且无风险标记。
3. **分层抽检与回译复核**：high 全检；medium 按 medium_sample 比例**确定性等距抽样**（可复现），未抽中与 low 均记录免检理由；复核判定 confirmed/false_positive/undetermined 三值，依据必填项由 ingest 强制校验。
4. **诚实性**：未复核命中保持 pending/not_reviewed，绝不标为 confirmed；原文不可得、证据不足、回译不一致 → undetermined 并写入 uncertainty；语种启发式识别与自报语种分列不互相覆盖；不补造文献、不推断缺失元数据。

## 异常处理

| 情况 | 处置 |
|-|-|
| case.json 不可读 | 记日志与 uncertainty，概念为空继续扫描记录；result 阶段 status 如实反映 |
| 无结构化查询概念 | 回退提取研究问题引号短语，标 `concepts_inferred`，写入 uncertainty |
| 命中记录文件损坏/格式不识 | 跳过并记日志与 uncertainty，不中断 |
| 正文文件指针（text_file）不可读 | 仅对现有字段对齐，记 WARNING 日志 |
| 命中无任何原文表面命中 | 记 no_surface_match → high 风险，进复核队列核对命中依据是否成立 |
| 记录未自报语种 | 启发式识别写入 language_detected，标 language_uncertain |
| ingest 校验失败（confirmed/false_positive 缺 basis、verdict 非法） | 退出码 2，逐条列出错误，**不写最终产物**，修复后重跑 |
| 复核项未填完（pending > 0） | 正常落盘，status=partial，pending 数写入 uncertainty |
| 队列超 max_queue | 高风险全检优先，裁减中风险抽样项并逐条记录 budget_cap 免检理由 |

## 自查方法

交付前逐项确认（可借助日志与统计）：

1. `evidence_align_log.json` 无 FATAL；台账每条命中都有 locator.file，每条 matched_form 都有 quote 与定位（span/line），可用 `sed -n` 或 JSON 路径回指原文。
2. 风险分布与命中数对账：high+medium+low == n_hits；queued+exempt 覆盖全部命中。
3. ingest 退出码为 0；若 2，逐条修复 review 块后重跑（校验失败时 /app/output 不会有半成品）。
4. result.json 的 status 与实际一致（pending>0 必须 partial）；confirmed+false_positive+undetermined+pending+exempt == n_hits；凡 confirmed/false_positive 都能在台账中读到 basis。
5. 没有任何命中的 verdict 来自脚本自动填写——confirmed/false_positive/undetermined 只应来自 Agent 复核。

## 最小调用示例

见 `examples/example_walkthrough.md`（合成玩具数据，含葡语摘要与中英混排标题样本，仅说明接口与输出形态，**非正式案例结果**）。
