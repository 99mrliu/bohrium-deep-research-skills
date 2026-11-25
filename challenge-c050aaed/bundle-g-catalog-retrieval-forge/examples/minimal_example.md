# Minimal example (SYNTHETIC — 合成示例，非正式案例结果)

The fixture in `examples/fixture/` is **fabricated** for interface
demonstration: seven tiny UTF-8 text files, one administrative note, one
metadata CSV, three fixed questions. It is not an official challenge case
and contains no real research data.

Fixture profile, chosen to exercise every policy branch:

| file | role |
|-|-|
| `lit-notes-v1.md` / `lit-notes-v2.md` | version pair, different content; admin note says v2 替代 v1 |
| `meeting-notes.md` + `meeting-notes (copy).md` | byte-identical duplicate |
| `metadata.csv` | sidecar metadata keyed by filename |
| `incoming/webclip.md` | ordinary member |
| `questions.json` | q1 answerable from notes; q2 answerable from the version edge; q3 （光催化） has **no** supporting record → must be `unanswered` |

Run:

```bash
bash examples/run_example.sh
```

Expected shape of a successful run:

1. `catalog`: 7 records; edges include `duplicate_of` (meeting-notes pair,
   evidence = shared sha256) and `superseded_by` (v1 → v2, evidence =
   administrative-note line, overriding the heuristic edge).
2. `index`: SQLite built; FTS5 table present when the runtime's sqlite3
   supports it (the script prints which mode is active).
3. `query 单原子 稳定性`: hits `lit-notes-v1.md` / `lit-notes-v2.md` with
   snippets and hashes.
4. `answer`: q1 and q2 `answered` with cited id/path/sha256; q3
   `unanswered` with reason — abstention is the correct deliverable.
5. `contract`: `result.json` carries `case_id =
   synthetic-demo-catalog-forge`; `search_index` is intentionally left
   unmapped in this example to demonstrate the honest `not_produced`
   marker and the `contract_gaps` list (exit code 1).

Nothing under `examples/fixture/materials/` is ever modified; only
`examples/out/` is created (and deleted on re-run).
