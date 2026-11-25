# Minimal example (SYNTHETIC — 合成示例，非正式案例结果)

The fixture in `examples/fixture/` is **fabricated** for interface
demonstration: seven tiny UTF-8 text files (one is a truncated fake PDF
kept as text), one administrative note, one metadata CSV. It is not an
official challenge case and contains no real research data.

Fixture profile, chosen to exercise every policy branch:

| file | role |
|-|-|
| `催化剂综述-final.txt` + `催化剂综述-final (1).txt` | byte-identical duplicate download |
| `实验记录 v1.txt` / `实验记录 v2.txt` | version suspects, different content |
| `行政说明.txt` | explicit statements: v2 替代 v1; the two 综述 files are duplicates; also names a nonexistent `原始数据.csv` (unmatched rule → conflict) |
| `scan-手写批注.pdf` | truncated/corrupt; copied as-is and flagged |
| `incoming/webclip.md`, `metadata.csv` | ordinary members |

Run:

```bash
bash examples/run_example.sh
```

Expected shape of a successful run (hashes/timestamps differ per machine):

1. `survey`: 8 files, 1 duplicate group, 2 version-suspect clusters
   (the identical 综述 pair plus `实验记录`), 0 errors; the fake PDF
   sniffs as `pdf` (magic) — its truncation is a content fact recorded
   from the file itself.
2. `plan`: 1 `register_duplicate_group` (canonical `催化剂综述-final.txt`),
   1 `register_version_chain` (v1 → v2, basis = explicit administrative
   note), 1 unmatched admin rule (`原始数据.csv` — reported, not dropped).
3. `apply`: copies canonical members into `organized_library/canonical/`,
   the older version into `organized_library/versions/实验记录/`; writes
   `ALIASES.json` and `VERSIONS.json`; journals every action.
4. `verify`: `ok: true`, all copies re-hashed, journal chain intact, no
   source unrepresented.
5. `rollback` drill removes all copies (originals untouched), then the
   script re-applies so the example ends in a complete state.

Nothing under `examples/fixture/materials/` is ever modified; only
`examples/out/` is created (and deleted on re-run).
