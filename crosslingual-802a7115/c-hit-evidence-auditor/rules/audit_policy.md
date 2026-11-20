# 复核规则（audit policy）

本文件是命中级误译复核的判据与操作规范。脚本中的确定性部分由 `scripts/risk_triage.py` 的 `DEFAULT_RULES` 实现（可用 `--rules` JSON 覆盖键值、或 `--medium-sample`/`--max-queue` 命令行覆盖）；回译执行由 Agent 按第 3 节清单人工完成。

## 1. 风险分级判据（确定性，全部留痕 risk_reasons）

命中级与概念级标记由 `evidence_align.py` 产生；分级取 high > medium > low 的最高档。

### high（假阳性高风险，全部进入回译复核）

| 标记 | 含义 |
|-|-|
| `wording_mismatch` | 命中记录语种在概念词形表中有对应词形，但该语种词形零命中，仅靠其他语种（译文）词形命中——译文用词与原文用词对不上 |
| `abbrev_only` | 概念仅由缩写词形命中（ASCII 全大写、2–6 字符）；同一缩写在不同语种/学科可指不同概念，须回译核对上下文定义 |
| `no_surface_match` | 所有查询概念在该记录的标题/摘要/正文中均无原文表面命中，命中依据不明（疑似仅靠二手元数据或机翻词面） |
| `secondary_source` | 记录类型为 citation_mention/review/news 等二手转述，概念未在一次文献原文中出现 |

### medium（中风险，按比例抽样复核）

| 标记 | 含义 |
|-|-|
| `context_terms_absent` | 概念定义了 context_terms，但命中点 ±300 字符窗口内均未出现——词面对应而上下文语义存疑（如方法名被译成普通名词） |
| `title_only` | 概念仅在标题命中，无摘要/正文佐证 |
| `short_form` | 命中词形归一化后 ≤3 字符（非 CJK），子串误配风险 |
| `partial_coverage` | 仅部分查询概念有表面命中 |
| `translation_record` | 记录为译本视图，译本用词与原文用词的一致性需抽样核对 |
| `language_uncertain` | 记录未自报语种，语种为启发式识别（可能误判） |

### low（低风险，免检但记录理由）

原文语种词形直接命中且无任何上述标记。免检理由 `low_risk: 原文语种词形直接命中且无风险标记` 写入台账 review.exempt_reason。

注意：`no_concepts`（case 未给出概念）按 low 记录但不进队列，并在 uncertainty 说明概念缺位。

## 2. 分层抽检比例与预算控制

- **high：全检**（不设上限内裁剪）；**medium：确定性等距抽样**，比例 `medium_sample`（默认 0.5），对按 hit_id 排序的列表等距选取 `round(n×frac)` 条——同一输入必得同一样本，可复现；**low：免检**，理由落台账。
- `max_queue` 默认 20：64 次模型请求预算下，每复核项 ≈1 次请求（可多条合并进一次请求进一步省预算）。队列超上限时**高风险全检优先**，裁减中风险抽样项，被裁条目逐条记录 `budget_cap` 免检理由，不得静默丢弃。
- 未抽中的 medium 记 `medium_risk_sampling` 免检理由；凡 `not_reviewed` 必须带 exempt_reason。
- 900 秒预算：两个脚本均为秒级；时间主要花在 Agent 复核上，队列规模即时间上限的代理。

## 3. 回译执行检查清单（Agent 人工执行，脚本不做机器翻译）

对 `backtranslation_queue.json` 中每个 item：

1. **定位原文**：按 item 中 terms_to_backtranslate 的 locator（file＋JSON 路径/行号）与 span/line 回指原文，通读 quote_context（不足时打开原文件读上下文）。
2. **回译**：把 matched_form（及其所在原文表达）回译到 target_lang（查询语种），写入 review.back_translation，保留原样备查。
3. **语义比对**：回译结果与查询概念的语义是否一致？重点排查：译文词形与原文用词不对应（wording_mismatch 项）、缩写在该文内的实际定义（abbrev_only 项）、词面对应但上下文是普通名词/另一概念（context_terms_absent 项）、概念仅出现在转述中（secondary_source 项）。结论写入 review.semantic_consistent（true/false/null）。
4. **判定与依据**：填 review.verdict（三值见第 4 节）与 review.basis（**必填**，写清：核对了哪个文件哪一段、原文实际用词是什么、与回译是否一致、结论如何得出）；填 reviewer 与 reviewed_at。
5. **证据不足不硬判**：原文不可得、片段过短、回译不一致且无法归因 → undetermined 并在 basis 说明缺什么证据。

## 4. 判定标准（三值）

| verdict | 标准 |
|-|-|
| `confirmed` | 原文（或该版本视图）中实际用词与查询概念语义一致，回译吻合，相关性可由引文直接支撑 |
| `false_positive` | 命中由误译/词面错配/缩写歧义/二手转述造成，原文语义不支持相关性；basis 必须指明错配类型 |
| `undetermined` | 原文不可得、证据不足或回译不一致且无法归因；保留为未决，不计入 confirmed 也不计为假阳性定论 |

## 5. 依据必填项与校验（ingest 强制）

- `confirmed` / `false_positive`：**必须有非空 basis**，缺失即校验错误（退出码 2，不写最终产物）；建议同时保留非空 back_translation（缺失给警告）。
- `undetermined`：basis 强烈建议（说明证据缺口），缺失给警告不阻断。
- verdict 取值非法（非三值之一）即校验错误。
- 未填写的 item 按 pending 处理：不报错，但 result status=partial 且 pending 计数写入 uncertainty。
- 脚本不自动产生任何 verdict；台账中 confirmed/false_positive/undetermined 只应来自 Agent 填写的 queue。凡发现无 queue 来源的判定，视为台账被污染，应重跑 ingest。
