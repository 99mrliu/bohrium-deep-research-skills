# 最小调用示例（示意输出，非正式案例结果）

输入（示意）：`/input/case.json`（research_question + output_contract）、`/input/task.md`、
`/input/search09_export.json`（15 条记录，其中 2 条标注 synthetic_duplicate、2 条标注 conflicting_opinion）、
`/input/reference_papers.json`（9 篇署名文献）。

```bash
python3 /skills/weekly-skill/scripts/run_all.py \
  --case /input/case.json --input-dir /input --work /app/work --out /app/output
# [ingest.py] rc=0 {"ok": true, "records": 15, "failures": 0}
# [dedupe.py] rc=0 {"in": 15, "kept": 13, "duplicates_removed": 2, "synthetic_flagged": 2}
# [screen.py] rc=0 {"ok": true, "screened": 13, "included": 7, "excluded": 4, "uncertain": 2, ...}
# [attest.py] rc=0 {"ok": true, "total": 9, "matched": 8, "ambiguous": 0, "missing": 1}

# 核对 criteria.auto.json -> 修订 -> 另存 criteria.json -> 重跑:
python3 /skills/weekly-skill/scripts/screen.py \
  --work /app/work --criteria /app/work/criteria.json --out /app/output
python3 /skills/weekly-skill/scripts/finalize.py \
  --case /input/case.json --input-dir /input --work /app/work --out /app/output
# {"ok": true, "status": "partial", "contract_fields": 7, "uncertainty_items": 2}
```

产物：`result.json`（含 case_id、summary、candidates、screening_ledger、evidence_log、sources、status=partial、uncertainty）、
`ledger.jsonl`（13 行，逐条 disposition+reason_codes）、`attribution.json`（9 篇：8 matched / 1 missing 已写入 uncertainty）。
