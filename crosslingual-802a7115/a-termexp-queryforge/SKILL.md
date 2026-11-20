---
name: xlang-termexpansion-queryforge
description: 术语表驱动的多语种受控查询扩展（terminology-driven multilingual query expansion）：从研究问题抽取概念、建立带来源标注的多语种术语表，对未覆盖概念做受控翻译并回译校验，逐语种生成布尔查询式，再把命中结果对齐回术语变体并输出语种覆盖统计。当任务要求跨语言检索文献（尤其需要找回葡萄牙语/西班牙语/日语/德语/中文等非英语论文）、且必须说清每条命中由哪个语种的哪个术语召回时使用；适用于 /input/case.json + task.md 的 Harbor 运行契约，也适用于任何需要可核对术语对齐的跨语种已知文献检索。
---

# 术语表驱动的多语种受控查询扩展（xlang-termexpansion-queryforge）

## 用途与适用条件

解决跨语言文献检索的**查询生成阶段**问题：用户只用母语提问，检索系统只返回单一语种论文；简单机翻查询会把术语译成字面同义词而非学科用词、或与论文原文用词不一致导致召回骤降。本 Skill 的做法是先建术语表（每个概念对应各目标语种的学科用词，区分 preferred/synonym/abbreviation/上下位/音译，每条变体带来源与置信），再逐语种生成独立布尔查询，最后把命中逐条对回术语变体，供人工核对术语对齐质量。

本 Skill 只负责**检索前的查询生成与检索后的命中-术语对齐、语种覆盖核算**；不做版本归并/去重、不做误译内容复核（与其他方向解耦），但命中记录的 source/DOI/version/正文语种/translation_of 等归因字段一律原样转写保留，供下游使用。

不适用：全文语义理解、实时网络检索（脚本完全离线；本地语料即全部证据）、自动生成翻译（脚本**绝不**自行造译名，翻译只能由 Agent 以受控翻译条目形式供给并附回译证据）。

## 输入

- `/input/case.json`：案例文件，含 `case_id`、研究问题文本、`output_contract`。
- `/input/task.md` 或 `task.md`：任务说明；其文本参与候选概念抽取。
- 本地语料：组织方提供的检索结果记录（可能位于 `/input`、`/app/work` 或当前目录），支持 `.json/.jsonl/.csv/.tsv/.txt/.md` 异构格式，脚本自动发现并解析 title/abstract/keywords（含 resumo/resumen 字段名）。
- 术语表来源（按优先级合并，均可选）：
  1. 案例自带术语表：任何含 `concepts` 键的 JSON，自动合并；
  2. `--seed`：Agent 依据 `resources/term_table_seed.json` 的格式为本案例编写的术语表（内置示范表**不会**自动加载，其演示概念会污染查询）；
  3. `--translations`：Agent 供给的受控翻译条目（需 `concept_id/lang/term`，强烈建议附 `back_translation` 以供回译校验）。

## 调用方式（按顺序执行）

```bash
# 0.（Agent 手工步骤）读 case.json/task.md 与本地语料，编写本案例术语表
#    格式照抄 resources/term_table_seed.json；未覆盖概念的译名写入
#    translations.json（每条附 back_translation）。

# 1. 术语表构建：抽取候选概念、合并各来源、回译校验、输出 to_translate 清单
python3 scripts/term_table.py --case /input/case.json \
    --out /app/work/term_table.json --workdir /app/work \
    --seed /app/work/case_terms.json --translations /app/work/translations.json \
    --langs en,zh,pt,es,ja,de

# 2. 逐语种查询生成 + 命中对齐 + 语种覆盖核算 + 组装 result.json
python3 scripts/query_build.py --case /input/case.json \
    --term-table /app/work/term_table.json \
    --out /app/output --workdir /app/work
```

可选参数：`--roots`（追加语料根目录）、`--max-candidates`（候选概念上限，默认 60）。900 秒预算下两个脚本通常在数秒内完成；模型请求只花在 Agent 编写术语表与受控翻译上，64 次预算充裕。

## 输出

`/app/work`：
- `term_table.json`：合并后的术语表（含每个变体的 source/confidence/verified/verification）、`to_translate`（缺失的 概念×语种 清单）、`candidate_concepts`（启发式抽取的候选概念，仅供参考，不自动入表）、`roundtrip` 统计、`parse_notes`、`run_log`。
- `term_table_runlog.json` / `run_log.json`：两个脚本的运行日志。

`/app/output`：
- `result.json`：`case_id`、`status`（ok/partial/failed）、`term_table_summary`、`queries`（每语种一条布尔查询式，含生成依据、unverified 变体计数、uncovered 概念）、`hits`（每条命中的归因转写＋逐概念术语对齐＋locator）、`coverage`（每声明语种的有效结果数；零命中语种给出显式证据化说明）、`sources`、`evidence_records`、`uncertainty`、`change_records`，并镜像 `output_contract` 的全部字段。
- `query_log.json`：全部语种查询式。
- `hit_alignment.md`：人读的命中—术语对齐表，供人工核对术语对齐质量。

## 关键方法（详见 rules/term_expansion_policy.md）

1. **候选概念抽取（双语种启发式）**：从案例与语料文本中抽取拉丁字母术语与多词词组（1–3 词、含变音字符）、全大写缩写（如 DENV、GSDMD）、CJK 连续串（中文/日文表面形式，按"的/与/和"等助词切分）。候选只列出来供 Agent 判断，**不自动**成为概念。
2. **受控翻译与回译校验**：脚本不翻译。Agent 以 `--translations` 供给译名，必须附 `back_translation`；回译规范化后与概念英文 label 或既有 en 变体一致 → `verified=true`；不一致 → 标 `unverified`、置信减半、降级使用（保留在查询中但在对齐表与 uncertainty 中显式标记）；无回译证据 → 维持来源声明的 verified 标志并标注 `round-trip:no-evidence`。
3. **逐语种查询**：每语种一条布尔查询，概念内 OR、概念间 AND；unverified 变体参与查询但逐条标记；某概念在该语种无变体 → 该概念从查询中剔除，查询标 `completeness=partial` 并列出 uncovered 概念。
4. **命中对齐**：对每条本地记录（title/abstract/keywords）做表面形式匹配——拉丁文先做 NFKD 变音折叠（pt/es/fr 重音、de 变元音、ß→ss）加词边界子串匹配，CJK/假名做直接子串匹配；某语种查询的全部已覆盖概念均命中 → 该命中记为由该语种查询召回，逐概念记录命中的术语变体（含 verified 状态）。一条命中可被多个语种查询召回，全部记录。
5. **语种覆盖核算**：每个声明语种必须有有效命中，或在 `coverage` 中给出证据化缺失说明（query-not-emittable / query-partial / no-record-matched 三种之一），写入 `uncertainty`。
6. **诚实性**：命中的 doi/language/version/translation_of/source 等归因字段原样转写，记录未声明的字段绝不推断；无结果、术语无对应译法、翻译依据不确定全部写入 `uncertainty`；不补造任何文献。

## 异常处理

| 情况 | 处置 |
|-|-|
| case.json 不可读 | `status=failed`，写最小 result.json（含 uncertainty），退出码仍为 0 |
| 术语表为空/不可读 | query_build `status=failed` 或空查询；uncertainty 提示先运行 term_table.py |
| 概念在某语种无变体 | 写入 `to_translate`；该语种查询降级为 partial 并列 uncovered 概念 |
| 受控翻译回译不一致 | 变体标 `unverified`、置信减半；保留使用并在对齐表与 uncertainty 中标记，绝不删除 |
| 某声明语种零命中 | `coverage[lang].status=missing`＋证据化说明；整体 `status` 降为 partial |
| 记录缺 language/version 归因 | 归因字段留空并附 `attribution_note`，不推断；记入 uncertainty 可选项 |
| 文件损坏/格式不识 | 跳过并记入 `sources` 的 parse notes；不中断运行 |
| 缩写跨语种歧义（如 DENV vs 血清型） | 在变体 `ambiguity_note` 中声明；查询中缩写与全称同概念内 OR 联用消歧（见 rules） |

## 自查方法

交付前逐项确认（可借助 hit_alignment.md 人工核对）：
1. `result.json.status` 与实际完成情况一致；每个声明语种在 `coverage` 中要么有命中要么有显式说明；
2. 每条命中的每个召回语种都列出逐概念命中的术语变体，且变体都能在 term_table.json 中找到；
3. `uncertainty` 覆盖了：to_translate 缺失数、回译降级数、零命中语种、参与查询的 unverified 变体数；
4. 没有任何命中的归因字段是脚本推断的（归因均来自记录原文）；
5. 抽查 2–3 条命中：用 locator 回指原始记录，确认匹配术语确实出现在 title/abstract/keywords 中。

## 最小调用示例

见 `examples/example_walkthrough.md`（合成玩具数据，仅说明接口，**非正式案例结果**）。
