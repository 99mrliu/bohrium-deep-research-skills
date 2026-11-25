# Minimal example (SYNTHETIC — 合成示例，非正式案例结果)

The fixture in `examples/fixture/` is **fabricated** for interface
demonstration: seven tiny UTF-8 text files (one is a truncated fake PDF
kept as text), one administrative note, one metadata CSV. It is not an
official challenge case and contains no real research data.

Fixture profile, chosen to exercise every policy branch:

| file | role |
|-|-|
| `review-final.txt` + `review-final (1).txt` | byte-identical duplicate download |
| `exp-record v1.txt` / `exp-record v2.txt` | version suspects, different content |
| `ADMIN_NOTES.txt` | explicit statements: v2 替代 v1; the two 综述 files are duplicates; also names a nonexistent `raw-data.csv` (unmatched rule → conflict) |
| `scan-handwritten.pdf` | truncated/corrupt; copied as-is and flagged |
| `incoming/webclip.md`, `metadata.csv` | ordinary members |

Run:

```bash
bash examples/run_example.sh
```

Expected shape of a successful run (hashes/timestamps differ per machine):

1. `survey`: 8 files, 1 duplicate group, 2 version-suspect clusters
   (the identical review pair plus `exp-record`), 0 errors; the fake PDF
   sniffs as `pdf` (magic) — its truncation is a content fact recorded
   from the file itself.
2. `plan`: 1 `register_duplicate_group` (canonical `review-final.txt`),
   1 `register_version_chain` (v1 → v2, basis = explicit administrative
   note), 1 unmatched admin rule (`raw-data.csv` — reported, not dropped).
3. `apply`: copies canonical members into `organized_library/canonical/`,
   the older version into `organized_library/versions/exp-record/`; writes
   `ALIASES.json` and `VERSIONS.json`; journals every action.
4. `verify`: `ok: true`, all copies re-hashed, journal chain intact, no
   source unrepresented.
5. `rollback` drill removes all copies (originals untouched), then the
   script re-applies so the example ends in a complete state.

Nothing under `examples/fixture/materials/` is ever modified; only
`examples/out/` is created (and deleted on re-run).
