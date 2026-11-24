# EXPECTED — real observed results

Recorded from an actual run of the commands in `README.md`
(Python 3.12.14, macOS arm64, 2026-11-24). The pipeline is deterministic;
identical inputs reproduce these byte-for-byte.

## 1. build_index.py

```
documents: annotations=6 notes=4 files=2 total=12 terms=135
wrote /tmp/work_index.json
exit: 0
```

`cmp /tmp/work_index.json output/index.json` → **IDENTICAL** (the shipped
prebuilt index is exactly what the builder produces from the fixtures).

## 2. Queries

### `--q "sparse attention"` → 7 hits, max_score 7

```
rank id       kind        file                                    page score
1    note-001 note        papers/efficient_transformers_survey.pdf 3    7
2    ann-001  annotation  papers/efficient_transformers_survey.pdf 3    4
3    ann-003  annotation  papers/efficient_transformers_survey.pdf 7    4
4    note-004 note        papers/efficient_transformers_survey.pdf 9    4
5    ann-002  annotation  papers/efficient_transformers_survey.pdf 5    3
6    ann-006  annotation  papers/efficient_transformers_survey.pdf 9    2
7    note-003 note        papers/efficient_transformers_survey.pdf 5    2
```

### `--q "增量学习"` → 3 hits, CJK matched via bigrams (增量/量学/学习)

```
rank id       kind        page score snippet
1    note-002 note        1    9     增量学习方法必须在遗忘与可塑性之间取得权衡。…
2    ann-004  annotation  1    7     增量学习的核心挑战是灾难性遗忘 …
3    ann-005  annotation  2    3     回放缓冲区可以显著缓解遗忘问题 …
```

note-002 (the correct note) is rank 1; ann-005 matches through its
`增量学习` tag even though its anchored text does not contain the phrase.

### `--q "quantum zebra teleportation"` → 0 hits, structured no-hit report

```json
"no_hit": {
  "eliminating_facets": [],
  "combination_eliminated": false,
  "text_terms_matched_nothing": true,
  "suggestions": [
    "no document contains the query terms — check spelling variants, synonyms, or broader terms (remember CJK text is matched by bigrams)",
    "inspect what the index actually holds with a broad query, a known tag, or a bare --file filter"
  ]
}
```

exit 0 — a no-hit answer is a normal answer.

### `--q "sparse" --file "notes/continual_learning_zh.txt"` → 0 hits, facet-elimination diagnosis

```json
"no_hit": {
  "eliminating_facets": ["file"],
  "combination_eliminated": false,
  "text_terms_matched_nothing": false,
  "suggestions": [
    "relax or remove facet(s) file — each one single-handedly eliminated every hit",
    "inspect what the index actually holds with a broad query, a known tag, or a bare --file filter"
  ]
}
```

### `--q "softmax"` → low-recall marking

```
low_confidence: true   max_score: 1   (threshold 2.0)
rank 1 ann-002 score 1
rank 2 note-003 score 1
```

### Filters

- `--tag "增量学习"` → hits: `ann-004`, `ann-005`, `note-002`
- `--since 2026-11-21` → hits: `note-003`, `note-004`

### Query log (`query_log.jsonl`, wall-clock-free, seq-numbered)

```
{"args": {"file": null, "q": "sparse attention", ...}, "hits": 7, "low_confidence": false, "seq": 1}
{"args": {"file": null, "q": "增量学习", ...}, "hits": 3, "low_confidence": false, "seq": 2}
{"args": {"file": null, "q": "quantum zebra teleportation", ...}, "hits": 0, "low_confidence": false, "seq": 3}
{"args": {"file": "notes/continual_learning_zh.txt", "q": "sparse", ...}, "hits": 0, "low_confidence": false, "seq": 4}
```

## 3. Gate — pass case → exit 0

```
[PASS] contract_completeness: all 4 output_contract field(s) present: inventory, notes, index, verification
[PASS] artifact_integrity: verified 4 artifact(s): index, inventory, notes, verification
[PASS] verification_rates: verification.json: anchors 6/6 = 1.000, failed=0; verification.json: note claims 4/4 = 1.0
[PASS] retrieval_smoke: smoke[1] q='sparse attention': ann-001 found at rank 2; smoke[2] q='增量学习': note-002 found at rank 1; smoke[3] q='quantum zebra teleportation': negative control ok (zero hits)
[PASS] replay_determinism: rebuilt index is byte-identical (replayed from …/examples)
verdict: pass -> output/gate_report.json
exit: 0
```

`output/result.json` keeps `status: "complete"`.

## 4. Seeded contract violation (deleted field `index`) → exit 3

```
[FAIL] contract_completeness: missing output_contract field(s): index
[PASS] artifact_integrity: verified 4 artifact(s): index, inventory, notes, verification
[PASS] verification_rates: verification.json: anchors 6/6 = 1.000, failed=0; verification.json: note claims 4/4 = 1.0
[PASS] retrieval_smoke: smoke[1] q='sparse attention': ann-001 found at rank 2; smoke[2] q='增量学习': note-002 found at rank 1; smoke[3] q='quantum zebra teleportation': negative control ok (zero hits)
[PASS] replay_determinism: rebuilt index is byte-identical (replayed from …/examples)
verdict: fail -> /tmp/out_bad/gate_report.json
result.json rewritten: status=partial, failed checks appended to uncertainty/limitations
exit: 3
```

Rewritten `/tmp/out_bad/result.json` (inspected after the run):

```
status:      partial
uncertainty: ["gate failed checks: contract_completeness"]
preserved:   artifacts, case_id, change_records, inventory, notes, sources,
             synthetic, verification   (all other fields untouched)
```

## 5. Tampered index.json (one tf digit flipped, JSON still valid) → exit 3

Caught by **two** independent checks:

```
[FAIL] artifact_integrity: verified 3 artifact(s): inventory, notes, verification; index: sha256 mismatch for index.json (recorded 46a51fe5ea5a…, actual 29bd6d8fdc11…)
[FAIL] replay_determinism: rebuilt index differs byte-for-byte from shipped index.json (index is stale, hand-edited, or tampered)
verdict: fail -> /tmp/out_tamper/gate_report.json
exit: 3
```

Rewritten result: `status: partial`,
`uncertainty: ["gate failed checks: artifact_integrity, replay_determinism"]`.

## Additional negative tests run during development

- Structural corruption (one doc key renamed, JSON valid): smoke check reports
  `ann-001 not in top-5`, replay_determinism fails, exit 3 (a crashed check is
  a failed check — the gate never crashes itself).
- Low verification rates (`anchors 5/6 failed=1`, claims `3/4`):
  `[FAIL] verification_rates: anchor rate 0.833 (need >= 0.95), failed=1
  (need 0); note claims 3/4 verified (need 1.0)`, exit 3.
- Missing `--case` file: `error: --case: file not found`, exit 2.
- `build_index.py` with no inputs: exit 2 with a usage error.
- All three scripts `--help`: exit 0.
