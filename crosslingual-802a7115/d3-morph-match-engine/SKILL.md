---
name: xlang-morph-match-engine
description: 跨语言表面形式匹配引擎（cross-lingual morphological matching）。把多语种术语变体与真实语料做可归因匹配：NFKD 变音折叠（São/sao、ü/u、ß→ss）、德语变元音转写（ä→ae）与复合词包含匹配（compound_match 标记）、轻量词形还原（复数/动词词尾）、日文假名直接匹配加 Hepburn 罗马字交叉通道、CJK 直接子串、中英混排标题双通道。每条命中输出概念、语种、术语变体、归一化规则、偏移与上下文，供人工逐条核对术语对齐。当译文用词与论文原文用词不一致、变音字符或复合词导致召回失败、或必须说清"哪条变体在哪条规则下命中"时使用；适用于 /input/case.json + task.md 的 Harbor 运行契约。
---

# 跨语言形态匹配引擎（xlang-morph-match-engine）

## 用途与适用条件

跨语言检索的召回断点常在表面形式：变音字符（São vs Sao）、德语复合词
（Pyroptose 嵌在 Zellpyroptose 里）、词形变化（pyroptoses/pyroptótica）、
假名转写（パイロトーシス）、中英混排标题。本 Skill 的重心是**匹配本身**：
多通道归一化＋逐命中归因（哪个概念、哪个语种变体、哪条规则、原文偏移与上下文），
让术语对齐经得起人工逐条核对。

不做：术语表生产（变体必须由 Agent/上游供给，引擎**绝不**自造术语）、语种判定、
版本归并。unverified 变体照常参与匹配但逐条标记。

## 运行契约

- 输入：`/input/case.json`（含 `case_id`、`output_contract`）、`/input/task.md`、
  语料文件（JSON/JSONL/CSV/TSV/TXT/MD/PDF），以及一份术语表 JSON
  （`{"concepts":[{"concept_id","label","variants":[{"lang","term","verified"}]}]}`）。
- 工作目录 `/app/work`；最终交付 `/app/output/result.json`，含 `case_id` 与
  `output_contract` 全部字段；命中证据直接引自 `matches.json`，诚实 status。
- PDF 经 `pdftotext` 真实抽取；失败记入 parse_notes。

## 调用方式

```bash
# 1.（Agent）依据案例与语料编写本案例术语表 /app/work/case_terms.json
#    （格式见 examples/data/terms.json；脚本不生成、不翻译术语）

# 2. 多通道匹配
python3 scripts/xmatch.py --terms /app/work/case_terms.json \
    --roots /input /app/work --out /app/work/match --exclude examples

# 3. 人工抽查 /app/work/match/match_report.md：每条命中核对 context 中
#    原文片段，确认 matched_form 确实出现；compound_match 与 unverified
#    变体的命中重点复核。

# 4. result.json 的 hits 逐条转写：record_id、doi、declared_language、
#    概念→变体→规则→offset；coverage_by_lang 用于语种覆盖核算。
```

完全离线、仅标准库；典型语料数秒内完成。

## 输出

`/app/work/match/`：

- `matches.json`：`hits[]`（record_id、source_file、doi、declared_language、
  matched_fields、concepts[]，每概念 matches[] 含 lang/term/verified/rule/
  matched_form/offset/context）、`coverage_by_lang`、`parse_notes`。
- `match_report.md`：人读命中清单，unverified 变体带 [UNVERIFIED] 标记。

## 关键方法（详见 references/matching_rules.md）

1. **归一化通道**：NFKD 折叠（主通道）；ä→ae/ö→oe/ü→ue/ß→ss（德语转写通道）；
   假名→Hepburn 罗马字（交叉通道）；轻量词形还原（复数/-ed/-ing/-ções 等，主干≥4 字符）。
2. **匹配规则**：拉丁变体先词边界匹配；无词边界命中且变体为≥5 字符单词时，
   尝试复合词包含匹配并标 `compound_match`；CJK/假名直接子串。
3. **归因完整**：每条命中记 rule 与 matched_form——复核者可按规则重放匹配过程；
   context 为折叠后文本 ±60 字符窗口。
4. **诚实性**：verified=false 的变体命中照常输出但逐条标记；零命中语种在
   coverage_by_lang 中缺席，result.json 必须显式说明而非静默。

## 异常处理

| 情况 | 处置 |
|-|-|
| 术语表为空/不存在 | parse_notes 记录；hits 为空，status=ok 但 result.json 须降级 partial |
| 概念在某语种无变体 | 该语种本就不在 coverage_by_lang；由 result.json 覆盖核算显式化 |
| PDF 抽取失败 | 该记录无正文、无命中，parse_notes 记录 |
| 变体为空串 | 跳过该变体 |
| 复合词误命中风险 | compound_match 单独标规则名，人工复核清单优先处理 |

## 自查方法

1. 随机抽 3 条命中：用 offset/context 回指原文，确认 matched_form 真实出现；
2. 每条命中的 rule 都在 references/matching_rules.md 的规则清单内；
3. coverage_by_lang 与 result.json 的语种覆盖声明一致；缺席语种有显式说明；
4. unverified 变体的命中在 result.json 的 uncertainty 中有汇总计数。

## 最小调用示例

见 `examples/example_walkthrough.md`（**合成示例**，非正式案例结果）。
