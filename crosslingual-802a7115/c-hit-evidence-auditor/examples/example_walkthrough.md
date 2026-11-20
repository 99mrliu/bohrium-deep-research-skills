# 最小调用示例（合成数据，示意，非正式案例结果）

以下使用**合成玩具数据**演示接口与输出形态。所有文献标识均为虚构，仅说明字段含义与判定流程。示例含一条葡语摘要、一条中英混排标题、一条 wording_mismatch 高风险命中。

## 输入

`/tmp/xlang_demo/case.json`：

```json
{
  "case_id": "demo-xlang-001",
  "research_question": "找出“梯度引导剪枝”工作的葡语原文论文，核对每条命中在原文中的实际用词。",
  "query_concepts": [
    {"id": "c1", "label": "梯度引导剪枝",
     "forms": {"zh": ["梯度引导剪枝"], "en": ["gradient-guided pruning"], "pt": ["poda guiada por gradiente"]},
     "context_terms": ["rede neural", "neural network", "神经网络"]},
    {"id": "c2", "label": "NBA 方法缩写", "forms": {"en": ["NBA"]}}
  ],
  "output_contract": {"hits": null, "evidence_ledger": null, "risk_distribution": null, "review_stats": null, "uncertainty": null}
}
```

`/tmp/xlang_demo/hits.jsonl`（四条合成候选命中）：

```json
{"hit_id": "h1", "title": "Poda guiada por gradiente para compressão de redes neurais", "abstract": "Neste artigo apresentamos a poda guiada por gradiente aplicada a cada rede neural convolucional.", "language": "pt", "doi": "10.0000/demo.pt.1", "version": "original"}
{"hit_id": "h2", "title": "Compressão de redes neurais profundas", "abstract": "Apresentamos uma abordagem baseada em gradient-guided pruning para compressão de modelos.", "language": "pt", "doi": "10.0000/demo.pt.2", "version": "original"}
{"hit_id": "h3", "title": "基于梯度引导剪枝的NBA模型压缩方法", "abstract": "本文提出基于梯度引导剪枝的压缩流程，记为 NBA，并在神经网络上验证。", "language": "zh", "doi": "10.0000/demo.zh.1"}
{"hit_id": "h4", "title": "A survey mention of gradient-guided pruning", "abstract": "Recent work on gradient-guided pruning has been cited widely.", "record_type": "citation_mention", "language": "en"}
```

## 调用

```bash
python3 scripts/evidence_align.py --case /tmp/xlang_demo/case.json --workdir /tmp/xlang_demo/work
python3 scripts/risk_triage.py triage --ledger /tmp/xlang_demo/work/evidence_ledger.json --workdir /tmp/xlang_demo/work
# Agent 填写 /tmp/xlang_demo/work/backtranslation_queue.json 各 item 的 review 块
python3 scripts/risk_triage.py ingest --ledger /tmp/xlang_demo/work/evidence_ledger.json \
    --queue /tmp/xlang_demo/work/backtranslation_queue.json \
    --out /tmp/xlang_demo/out --case /tmp/xlang_demo/case.json
```

## 各阶段要点（实际合成运行的预期行为）

**第 1 阶段 evidence_align**：

- h1（葡语摘要）：葡语词形 `poda guiada por gradiente` 在标题与摘要直接命中（变音折叠后匹配，引文还原为原文），context_terms 中 `rede neural` 在窗口内出现 → 无风险标记。
- h2（葡语记录但只有英文词形命中）：`gradient-guided pruning` 命中而葡语词形零命中 → `wording_mismatch=true`，detail 指明"仅通过 en 语词形命中（疑似译文词面命中）"。
- h3（中英混排标题）：`梯度引导剪枝` 直接命中；`NBA` 虽紧贴 CJK 字符（"…的NBA模型…"），因 CJK 视为天然边界而正确命中，同时被标记 `abbrev_form`。
- h4：`record_type=citation_mention` → 命中级标记 `secondary_source`。

**第 2 阶段 triage**：h2/h3/h4 判 high（分别因 wording_mismatch、abbrev_only、secondary_source）全检；h1 因概念部分覆盖（c2 未命中）判 medium，按 medium_sample 确定性抽样。queue 中每项带 terms_to_backtranslate（matched_form、target_lang=zh、quote/quote_context、locator/span/line）与空 review 模板。

**第 3 阶段 Agent 复核**（示例填写，节选 h2）：

```json
{"queue_id": "q002", "hit_id": "h2",
 "review": {"verdict": "false_positive",
            "back_translation": "基于 gradient-guided pruning 的方法",
            "semantic_consistent": false,
            "basis": "该记录语种为 pt，概念词形表提供葡语词形“poda guiada por gradiente”但原文未出现；摘要仅借用英文术语且无对应机制描述，属机翻词面命中导致的假阳性。",
            "reviewer": "agent", "reviewed_at": "2026-01-01T00:00:00Z"}}
```

若 confirmed/false_positive 漏填 basis，ingest 退出码 2 并逐条报错（例如 `q002 (h2): verdict=confirmed 必须填写非空 basis（判定依据），否则判定不可复核`），且不写 /app/output 产物。

**第 4 阶段 ingest**：校验通过后将 review 合并回台账，输出 `out/result.json`（status=ok 当 pending=0）、`out/audit_ledger.json`（逐命中含 risk/risk_reasons/review）、`out/audit_stats.json`（risk_distribution 与 review_stats 计数）。

## 复核方式

台账每条 matched_form 都可回指原文，例如：

```bash
python3 -c "import json; d=json.load(open('/tmp/xlang_demo/work/evidence_ledger.json')); \
print([m['quote_context'] for h in d['hits'] if h['hit_id']=='h2' for e in h['concept_evidence'] for m in e['matched_forms']])"
```

或直接 `sed -n '2p' /tmp/xlang_demo/hits.jsonl` 对照 locator（`{"file": ".../hits.jsonl", "pointer": "$/1"}`）核对 h2 摘要原文确实只有英文词形。
