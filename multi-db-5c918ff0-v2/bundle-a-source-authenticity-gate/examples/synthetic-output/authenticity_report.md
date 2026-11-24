# 上游数据真实性门控报告 (Source Authenticity Report)

- case_id: `synthetic-source-gate-001`
- run_id: `gate-f14deb7e8fdd0c95` (derived from input content hashes)
- gate version: `1.0.0`
- status: **partial**

> 本报告由 scripts/source_gate.py 确定性生成；不含时间戳，重跑同一输入应得到字节级一致的输出。

## 1. 工件级判定 (Per-artifact verdicts)

| artifact | path | classification | verdict | records | gated | reason codes |
|---|---|---|---|---|---|---|
| art-001 | materials/crossref_response.json | crossref | **trusted** | 2 | 2 | - |
| art-002 | materials/europepmc_response.json | europepmc | **trusted_with_warnings** | 2 | 2 | COUNT_MISMATCH |
| art-003 | materials/import_state.json | import_state | **trusted_with_warnings** | 4 | 0 | IMPORT_INCONSISTENT |
| art-004 | materials/publisher_records.json | publisher | **trusted** | 3 | 3 | - |
| art-005 | materials/reference_graph.json | reference_graph | **trusted_with_warnings** | 3 | 0 | DANGLING_EDGE |

## 2. 检查明细 (Check details)

### art-002 — `materials/europepmc_response.json` (sha256 `a25e11df6a4f…`)

- **COUNT_MISMATCH** [warning] — hitCount=3 but resultList contains 2 results; payload may be truncated or inconsistent

### art-003 — `materials/import_state.json` (sha256 `834df48d4455…`)

- **IMPORT_INCONSISTENT** [warning] `records[3]` — entry claims import from db 'europepmc' id '33000099' but that identifier is absent from art-002; entry quarantined

### art-005 — `materials/reference_graph.json` (sha256 `401f7d5a3441…`)

- **DANGLING_EDGE** [warning] `edges[2]` — edge endpoint(s) 10.99999/synth.077 do not resolve to any identifier present in the gated materials

## 3. 跨工件一致性 (Cross-artifact consistency)

- 引用图边检查: 3 条边, 1 条悬挂 (dangling)
- 导入状态条目: verified=3, not_verifiable=0, inconsistent=1

## 4. 门控结论 (Gate outcome)

- trusted: 2; trusted_with_warnings: 3; quarantined: 0
- 进入 gated_records.json 的记录数: **7**
- 无法诚实填写的契约字段 (null): curator_comment

## 5. 不确定性声明 (Uncertainty)

- 1 reference-graph edge(s) dangle outside the gated identifier universe; reported, not fatal
- 1 import_state entrie(s) are inconsistent with the source responses and were quarantined
- contract field(s) curator_comment could not be filled honestly and are null (see unresolved_contract_fields)
