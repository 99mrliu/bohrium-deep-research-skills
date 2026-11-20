# 最小调用示例（合成语料，示意，非正式案例结果）

以下用**合成玩具语料**演示两阶段接口与输出形态。所有文献标识（DOI、刊名、人名）均为虚构，仅说明字段含义与判定/归并行为。

## 输入

`/tmp/xlang_demo/input/records.jsonl`（7 条异构记录；另有一个 `duplicate_copy.json` 含第 1 条的完全重复副本，`case.json` 含 output_contract）：

```json
{"DOI": "10.1590/demo.2024.001", "title": "Estudo sobre os efeitos da irrigação na produtividade do milho em regiões semiáridas", "language": "pt", "volume": "12", "issue": "2", "page": "101-110", "issued": {"date-parts": [[2024]]}, "author": [{"family": "Silva", "given": "Ana"}, {"family": "Souza", "given": "Carlos"}], "fulltext": "Este estudo analisa os efeitos da irrigação ... （葡语正文，约 600 字符）"}
{"DOI": "10.1590/demo.2024.001.en", "title": "Study on the effects of irrigation on maize productivity in semi-arid regions", "language": "en", "volume": "12", "issue": "2", "page": "101-110", "issued": {"date-parts": [[2024]]}, "author": [{"family": "Silva", "given": "Ana"}, {"family": "Souza", "given": "Carlos"}], "translation_of": "10.1590/demo.2024.001", "fulltext": "This study analyzes the effects of irrigation ... （英语正文）"}
{"DOI": "10.2222/demo.abs.9", "title": "Mecanismos de resistência bacteriana a antimicrobianos em hospitais universitários", "language": "por", "abstract": "This review describes the main mechanisms of bacterial resistance ... （仅英文摘要，无正文）"}
{"DOI": "10.3333/demo.ja.005", "title": "半導体デバイスにおける熱伝導の解析", "volume": "8", "issue": "3", "page": "201-209", "issued": {"date-parts": [[2022]]}, "author": [{"family": "Tanaka"}, {"family": "Yamada"}], "fulltext": "本研究では、半導体デバイスにおける熱伝導の解析を行った。…（日语正文，无语言元数据）"}
{"DOI": "10.3333/demo.ja.005e", "title": "Analysis of heat conduction in semiconductor devices", "language": "en", "volume": "8", "issue": "3", "page": "201-209", "issued": {"date-parts": [[2022]]}, "author": [{"family": "Tanaka"}, {"family": "Yamada"}], "fulltext": "In this study, the heat conduction in semiconductor devices was analyzed. ... （英语正文，无显式译本字段）"}
{"DOI": "10.4444/demo.zh.002", "title": "城市绿地对热岛效应的缓解作用研究", "language": "zh", "fulltext": "本文研究了城市绿地对热岛效应的缓解作用。…（中文正文）"}
{"DOI": "10.5555/demo.en.100", "title": "A randomized trial of remote monitoring for heart failure patients", "language": "en", "fulltext": "This randomized trial evaluated ... （英语正文）"}
```

## 调用

```bash
python3 scripts/langid_version.py --roots /tmp/xlang_demo/input \
    --out /tmp/xlang_demo/work/langid_report.json --workdir /tmp/xlang_demo/work
python3 scripts/reconcile_works.py --report /tmp/xlang_demo/work/langid_report.json \
    --roots /tmp/xlang_demo/input \
    --case /tmp/xlang_demo/input/case.json --out /tmp/xlang_demo/output \
    --workdir /tmp/xlang_demo/work
```

## 实际运行结果（本仓库提交前实测，摘要）

阶段 1 输出一行汇总：

```json
{"records": 8, "by_body_language": {"pt": 3, "en": 3, "ja": 1, "zh": 1},
 "by_version_type": {"original": 5, "publisher-translation": 1,
                     "abstract-only-english": 1, "exact-duplicate": 1}}
```

逐条判定（标题截短；规则编号见 rules/version_policy.md）：

| 记录 | 版本类型 | 正文语种 | 判定规则 |
|-|-|-|-|
| 葡语正文记录 | original | pt (high) | R5c |
| 出版方英译记录 | publisher-translation | en (high) | R2（显式 translation_of） |
| 仅英文摘要记录 | abstract-only-english | pt (medium，据元数据推断) | R4a |
| 日语正文记录 | original | ja (high，假名证据) | R5c |
| 英语正文记录（日文工作之英译，无声明） | original | en (high) | R5c |
| 中文正文记录 | original | zh (high) | R5c |
| 英语 RCT 记录 | original | en (high) | R5c |
| 完全重复副本 | exact-duplicate | pt | R0（同指纹＋同文本哈希） |

阶段 2 输出一行汇总：

```json
{"status": "ok", "works": 5, "versions": 7, "raw_records": 8,
 "merges": 4, "orphans": 3}
```

关键归并决策（均可在 merge_decisions 中复算）：

- 葡语原文 × 出版方英译：score 2.0（high）—— explicit_relation(+1.00)＋doi_prefix_suffix_relation(+0.35)＋first_author_and_surname_set(+0.30)＋biblio_fingerprint_full(+0.35) → 并入同一 work，两个 version 视图（pt original / en publisher-translation）。
- 完全重复副本：score 3.05（high，explicit_duplicate＋same_doi）→ 吸收进原文 version，不单独计数（`duplicate_locators_absorbed=1`）。
- 日语原文 × 无声明英译：score 1.0（medium）—— doi_prefix_suffix_relation(+0.35，后缀 `demo.ja.005` vs `demo.ja.005e` 相似度 0.96)＋first_author_and_surname_set(+0.30)＋biblio_fingerprint_full(+0.35) → 归并。注意：跨语种译名标题 token 零重叠，归并由 DOI 关系＋作者序列＋书目指纹完成。
- 三条孤儿（仅英文摘要记录、中文记录、英语 RCT 记录）：无候选对越过 0.55，保持分列并给出原因。

去重计数对照：`raw_records=8 → distinct_versions=7（exact-duplicate 吸收）→ distinct_works=5`。若误按记录级统计会得到 8 条"命中"，其中 3 条是多语版本/副本造成的虚高——本对照表使虚高可见。

## 复核方式

用 locator 回指原始记录，例如核对"仅英文摘要记录"的判定依据：

```bash
python3 - <<'PY'
import json
rep = json.load(open('/tmp/xlang_demo/work/langid_report.json', encoding='utf-8'))
r = [x for x in rep['records'] if x['version_type'] == 'abstract-only-english'][0]
print(r['locator'])                 # {"file": ".../records.jsonl", "pointer": "$/2"}
print(r['evidence']['decision_rule'])            # R4a-english-abstract-nonenglish-metadata
print(r['evidence']['abstract_detection']['code'])  # en
print(r['metadata_languages'])      # ["pt"]  -> 正文语种据此推断，basis=metadata
PY
```
