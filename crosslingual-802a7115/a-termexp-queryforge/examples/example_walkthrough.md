# 最小调用示例（示意，非正式案例结果）

以下使用**合成玩具数据**演示接口与输出形态。所有文献标识、翻译条目均为虚构，仅说明字段含义；本示例不构成任何真实案例的检索结果。

## 输入

`/tmp/demo/case.json`：

```json
{
  "case_id": "demo-case-001",
  "question": "查找关于细胞焦亡 (pyroptosis) 与大豆 (soybean) 的多语种研究",
  "output_contract": {"answer_language": null, "retrieval_notes": null}
}
```

`/tmp/demo/records.jsonl`（每行一条检索结果记录，含版本/语种归因）：

```json
{"DOI": "10.0000/demo.en.1", "title": "Pyroptosis modulates soybean root signaling", "abstract": "pyroptosis in Glycine max roots ...", "language": "en", "version": "original"}
{"DOI": "10.0000/demo.pt.1", "title": "Piroptose na soja", "abstract": "A piroptose em raízes de soja.", "language": "pt", "version": "original"}
{"DOI": "10.0000/demo.zh.1", "title": "大豆根中细胞焦亡的调控", "abstract": "大豆根部的细胞焦亡。", "language": "zh", "version": "publisher-translation", "translation_of": "10.0000/demo.en.1"}
```

`/tmp/demo/case_terms.json`（Agent 照 `resources/term_table_seed.json` 格式编写的本案例术语表，2 概念 × 多语种变体，每条变体带 source/confidence/verified；节选）：

```json
{"term_table_format": "1.0", "languages_declared": ["en", "zh", "pt"],
 "concepts": [
  {"concept_id": "c1", "label_en": "pyroptosis", "variants": [
    {"lang": "en", "term": "pyroptosis", "type": "preferred", "source": "MeSH:D000080634", "confidence": 0.99, "verified": true},
    {"lang": "zh", "term": "细胞焦亡", "type": "preferred", "source": "seed-paper-keywords", "confidence": 0.95, "verified": true},
    {"lang": "pt", "term": "piroptose", "type": "preferred", "source": "DeCS:000080634", "confidence": 0.95, "verified": true}]},
  {"concept_id": "c2", "label_en": "soybean", "variants": [
    {"lang": "en", "term": "soybean", "type": "preferred", "source": "AGROVOC:35782", "confidence": 0.99, "verified": true},
    {"lang": "zh", "term": "大豆", "type": "preferred", "source": "seed-paper-keywords", "confidence": 0.95, "verified": true},
    {"lang": "pt", "term": "soja", "type": "preferred", "source": "AGROVOC:35782", "confidence": 0.95, "verified": true}]}
 ]}
```

`/tmp/demo/translations.json`（Agent 受控翻译条目；第二条**故意写错**回译以演示降级）：

```json
{"translations": [
  {"concept_id": "c1", "lang": "fr", "term": "pyroptose", "back_translation": "pyroptosis", "translation_basis": "Agent controlled translation (demo)"},
  {"concept_id": "c2", "lang": "fr", "term": "soja", "back_translation": "sugar", "translation_basis": "Agent controlled translation (demo, deliberately wrong)"}
]}
```

## 调用

```bash
python3 scripts/term_table.py --case /tmp/demo/case.json \
    --out /tmp/demo/work/term_table.json --workdir /tmp/demo/work \
    --roots /tmp/demo --translations /tmp/demo/translations.json \
    --langs en,zh,pt,fr
python3 scripts/query_build.py --case /tmp/demo/case.json \
    --term-table /tmp/demo/work/term_table.json \
    --out /tmp/demo/out --workdir /tmp/demo/work --roots /tmp/demo
```

第一步 stdout（实际冒烟运行形态）：

```json
{"term_table": "/tmp/demo/work/term_table.json", "concepts": 2, "variants": 8,
 "to_translate": 0, "roundtrip": {"checked": 2, "passed": 1, "downgraded": 1},
 "candidates": 12}
```

注意 `roundtrip.downgraded=1`：法语 "soja" 的回译 "sugar" 与概念英文 label "soybean" 不一致，该变体被标 `unverified`、置信减半，但**保留**在法语查询中并被显式标记。

## 示意输出（节选，标明为示例）

`/tmp/demo/out/result.json`：

```json
{
  "case_id": "demo-case-001",
  "skill": "xlang-termexpansion-queryforge",
  "status": "partial",
  "queries": {
    "en": {"query": "(\"pyroptosis\") AND (\"soybean\")", "completeness": "full", "...": "..."},
    "pt": {"query": "(\"piroptose\") AND (\"soja\")", "completeness": "full", "...": "..."},
    "zh": {"query": "(\"细胞焦亡\") AND (\"大豆\")", "completeness": "full", "...": "..."},
    "fr": {"query": "(\"pyroptose\") AND (\"soja\")", "completeness": "full",
           "generation_basis": {"n_unverified_variants": 1}}
  },
  "hits": [
    {"hit_id": "h0003", "title": "大豆根中细胞焦亡的调控",
     "attribution": {"doi": "10.0000/demo.zh.1", "language": "zh",
                     "version": "publisher-translation",
                     "translation_of": "10.0000/demo.en.1"},
     "recalled_by": [{"lang": "zh", "completeness": "full",
                      "matched_concepts": [
                        {"concept_id": "c1", "matched_variants": [{"term": "细胞焦亡", "verified": true}]},
                        {"concept_id": "c2", "matched_variants": [{"term": "大豆", "verified": true}]}]}],
     "locator": {"file": "/tmp/demo/records.jsonl", "pointer": "$/2"}}
  ],
  "coverage": {
    "en": {"n_hits": 1, "status": "ok"},
    "pt": {"n_hits": 1, "status": "ok"},
    "zh": {"n_hits": 1, "status": "ok"},
    "fr": {"n_hits": 0, "status": "missing",
           "explanation": "query emitted (completeness=full) but no local record surface-matched all covered concepts"}
  },
  "uncertainty": [
    "1 controlled translations failed round-trip verification and were downgraded (kept, flagged UNVERIFIED)",
    "language fr has no valid hits: query emitted (completeness=full) but no local record surface-matched all covered concepts"
  ],
  "output_contract_fields": ["answer_language", "retrieval_notes"]
}
```

要点：
- `status=partial`：fr 查询生成了但本地语料无法语记录 → 零命中并给出证据化说明，而非静默缺失；
- 中文命中的 `version=publisher-translation`、`translation_of=10.0000/demo.en.1` 原样转写——同一工作的多语种视图是否重复计入由下游版本归并处理，本 Skill 保证归因不丢；
- 每条命中可用 `locator` 回指原始记录行，术语对齐可逐变体人工核对。

## 复核方式

```bash
# 回指命中原始记录
sed -n '3p' /tmp/demo/records.jsonl
# 人工核对法语降级变体的校验记录
python3 -c "import json; t=json.load(open('/tmp/demo/work/term_table.json'));
[print(v) for c in t['concepts'] for v in c['variants'] if v.get('verification','').startswith('round-trip:failed')]"
```
