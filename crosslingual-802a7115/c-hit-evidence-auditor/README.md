# xlang-hit-evidence-auditor

跨语言文献检索的**命中级误译复核与证据对齐审计** Skill：对每条候选命中，把查询概念对齐到论文原文实际用词（引用原文片段、带文件＋字段/行号定位），用确定性规则做假阳性风险分级，按分层抽检生成回译复核任务清单，并在读回复核结论时强制校验判定依据，产出可人工逐条复核的证据台账。对应赛题"跨语言文献检索"的**方向 C（命中级误译复核与证据对齐审计）**，与查询扩展、检索执行、版本归并等方向完全解耦——本 Skill 从"已有候选命中"开始工作。

## 文件清单

| 文件 | 作用 |
|-|-|
| `SKILL.md` | Skill 本体：用途、输入输出、调用方式、异常处理、自查 |
| `rules/audit_policy.md` | 风险分级判据、分层抽检比例与预算控制、回译执行检查清单、三值判定标准、依据必填项 |
| `scripts/evidence_align.py` | 第一阶段：证据对齐（Python ≥3.8，仅标准库，离线，无安装步骤） |
| `scripts/risk_triage.py` | 第二阶段：风险分级、回译复核队列管理、依据完整性校验与台账汇总 |
| `templates/result_fields.md` | result.json 字段契约 |
| `examples/example_walkthrough.md` | 合成数据最小示例（含葡语摘要与中英混排标题，示意，非正式案例结果） |

## 依赖与环境

- Python ≥ 3.8，仅标准库；无第三方依赖、无网络依赖。
- 输入契约：`/input/case.json`（case_id、研究问题、查询概念、output_contract）＋候选命中记录文件（.json/.jsonl/.csv/.txt/.md，自动发现）。
- 输出契约：`/app/output/result.json`（镜像 output_contract 全字段）＋ `audit_ledger.json` ＋ `audit_stats.json`。
- 预算适配：高风险全检、中风险抽样（默认 0.5）、`max_queue` 默认 20；复核由 Agent 按清单执行，每条 ≈1 次模型请求且可合并，64 次请求预算内可完成。**不要对每条命中都发起模型调用。**

## 一次完整使用

```bash
python3 scripts/evidence_align.py --case /input/case.json --workdir /app/work
python3 scripts/risk_triage.py triage --ledger /app/work/evidence_ledger.json --workdir /app/work
# Agent 按 rules/audit_policy.md 检查清单填写 /app/work/backtranslation_queue.json 中各 item 的 review 块
python3 scripts/risk_triage.py ingest --ledger /app/work/evidence_ledger.json \
    --queue /app/work/backtranslation_queue.json --out /app/output --case /input/case.json
```

## 方法与分工（如实说明）

- 脚本做**确定性**工作：异构解析；NFKD＋变音折叠＋casefold 的表面匹配（拉丁词形要求词边界，中英混排中 CJK 视为边界）；引文截取与文件＋字段/行号/偏移定位；`wording_mismatch`（译文词形命中但记录语种的原文词形缺位）等风险标记；风险分级；确定性等距抽样；队列生成；判定依据完整性校验（confirmed/false_positive 缺非空 basis → 报错、退出码 2、不写最终产物）。
- 脚本**不做机器翻译**，不做语义判读，不自动给任何命中下 confirmed/false_positive 结论。回译由 Agent 按 `rules/audit_policy.md` 第 3 节检查清单执行：把队列中每条的 matched_form 回译到查询语种（target_lang），与 quote_context 比对语义一致性，填写 verdict/back_translation/basis。
- 语种识别是字符级启发式（CJK→zh；ã/õ/ç 等葡语变音→pt；其余拉丁文本→en），与记录自报语种分列呈现、互不覆盖；启发式判错的可能性写入 uncertainty（language_uncertain 标记进中风险）。

## 适用场景与限制

- 适用：双向跨语言"已知文献"研究的命中验证；机翻假阳性（词面对应、语义不同）排查；需要"每条命中为什么相关、命中的是原文哪个用词"的可核对立卷；同一工作多语种版本视图（原文/官方译本/仅英文摘要/重复副本）的逐条归因审计。
- 限制：表面匹配不理解的词形（概念词形表未列出的原文表达）无法对齐，会表现为 no_surface_match 并进入人工复核而不是被断言为无关；context_terms 检验是精确子串判定，只是上下文语义存疑的**代理信号**；语种启发式可能误判无变音符号的葡语文本；不做跨库去重与版本归并（重复的版本视图各自保留台账条目，由归因字段区分）；PDF 只处理平台 pdf-text-tool 已解析出的文本（.txt/.md 形式），不自行解析二进制 PDF。

## 失败处置

- 任何文件解析失败：跳过、记日志与 uncertainty，不中断；失败比例高时 status 应降 partial。
- ingest 校验失败：退出码 2，逐条列出缺依据的 queue_id/hit_id；修复 review 块后重跑，/app/output 不会留下未过校验的产物。
- 复核项 pending：照常落盘，status=partial，pending 计数写入 uncertainty；**禁止**把 pending/not_reviewed 改写为 confirmed。

## 自查

按 SKILL.md "自查方法"五条执行：定位可回指、风险分布对账、ingest 退出码 0、status 与实际一致、判定计数守恒且 confirmed/false_positive 均可读到 basis。

## 维护信息

- 版本：1.0（challenge-802a7115 提交版，方向 C）。风险规则默认值在 `scripts/risk_triage.py` 的 `DEFAULT_RULES`，可用 `--rules` JSON 或 `--medium-sample/--max-queue` 覆盖，无需改代码。
