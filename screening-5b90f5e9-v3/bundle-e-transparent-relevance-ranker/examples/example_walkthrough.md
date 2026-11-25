# 合成示例走查（example walkthrough）

> **合成示例，非真实评测案例。** 全部题录、作者、期刊、数据库均为虚构，
> 仅用于演示 transparent-relevance-ranker 的端到端流水线。

## 1. 输入

- `example_case.json`：合成研究问题（虚构药物 NRC-9 / Neurocalm 用于化疗所致
  周围神经病变 CIPN），output_contract 共 12 个字段（故意放入
  `included_studies`——本 skill 不做纳排，演示"填不了置 null 并说明"）；
- `materials/records.jsonl`：11 条合成题录，覆盖高/中/低相关、两组并列、
  一条疑似重复导出（SYNB-0831 与 SYNM-1024 同文不同库）；
- `filled_facets.json`：演示 [模型] 步骤填写的 facet 词表；
- `filled_facets_bad.json`：负例词表（含语料中不存在的"吗啡缓释片"）。

## 2. 流水线与产物（run/ 目录均为真实跑出）

| 步骤 | 产物 | 结果 |
| --- | --- | --- |
| parse_case | run/work/case_summary.json、records.json | 11 条记录、12 个合同字段 |
| scaffold_result | run/output/result.json（骨架） | 合同字段占位，status=in_progress |
| build_facets --init | run/work/facets_skeleton.json | 5 个 facet 骨架 |
| build_facets --validate | — | 正例通过 |
| anchor_hits | run/work/anchors.json | 11 个词全部锚定，97 处命中留痕 |
| anchor_hits（负例） | run/work_neg/anchors.json | **exit 3**：吗啡缓释片零命中 |
| score_records | run/work/scores.json | 每记录完整分数分解单 |
| tier_and_ties | run/work/tiers.json | high 7 / medium 3 / low 1，并列组 2 |
| sensitivity | run/work/sensitivity.json | 10 个扰动方案，3 条换档记录 |
| fill_result | run/output/result.json、ranking_rationale.md | status=partial |
| selfcheck | stdout | ALL PASS + 1 WARN（included_studies 置 null） |

## 3. 排序结果（真实计算）

| 名次 | record_id | 总分 | 档位 | 并列 |
| --- | --- | --- | --- | --- |
| 1 | SYNB-0831 | 87.6667 | high | T1 |
| 1 | SYNM-1024 | 87.6667 | high | T1 |
| 3 | SYNM-2077 | 76.3333 | high | |
| 4 | SYNM-4150 | 62.3333 | high | |
| 5 | SYNM-3301 | 61.3333 | high | |
| 6 | SYNM-8201 | 60.8333 | high | T2 |
| 6 | SYNM-8202 | 60.8333 | high | T2 |
| 8 | SYNM-5288 | 51.8333 | medium | |
| 9 | SYNM-6023 | 47.5833 | medium | |
| 10 | SYNM-7190 | 32.5 | medium | |
| 11 | SYNM-9005 | 0.75 | low | |

## 4. 走查要点

1. **并列如实标注**：T1 是同一研究的跨库重复导出（同分必然并列，且本 skill 不去重，
   在 uncertainty 提示）；T2 两条不同研究命中结构完全相同，共享第 6 名，
   没有用伪精度小数强排。
2. **排序 ≠ 纳排**：SYNM-4150（电针，非 NRC-9）因 RCT+近期+安慰剂+结局命中而进
   high 档——它阅读优先级高，但很可能应被排除。档位不替代 eligibility 判定。
3. **稳定性检验**：SYNM-3301、SYNM-4150、SYNM-7190 在 ±20% 权重扰动下换档，
   进入 rank_instability 列表，提示人工核阅其档位边界。
4. **锚定门禁负例**：负例词表触发 exit 3，迫使模型把臆造词换成语料真实词，
   从机制上防止"编相关性"。
5. **合同字段诚实 null**：`included_studies` 属纳入/排除语义，本 skill 置 null
   并在 uncertainty 说明，status=partial。
6. **规范化生效证据**：SYNM-5288 摘要里的小写 `nrc-9` 与各条目的全角
   `（CIPN）` 均被 NFKC+casefold 正确命中（见 anchors.json 片段）。

## 5. 手工复算抽查

抽 SYNM-8201：覆盖 = 70×(0.3×2/3 + 0.3×1/2 + 0.1×1/1 + 0.2×1/2 + 0.1×1/3)
= 70×0.58333… = 40.8333；时效 10（2024 = 参考年）；类型 15×1.0（RCT）；
多样性罚 5（期刊键"支持治疗学报"出现 4 次，min(5, 2×3)）；
total = 40.8333 + 10 + 15 − 5 = **60.8333**，与 scores.json 逐位一致
（详细复核记录见 selftest_log.md）。
