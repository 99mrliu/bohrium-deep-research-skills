# Synthetic example library (text fixtures only, no binaries)

A mini library exercising every feature of the skill:

| file                    | role                                                        |
|-------------------------|-------------------------------------------------------------|
| `report.pdf`            | UTF-8 text placeholder for a PDF                            |
| `downloads/report.pdf`  | same bytes, same basename → `byte_duplicate`                |
| `report_copy.pdf`       | same bytes, different basename → `renamed_copy`             |
| `notes_v1.txt`          | old version of the reading notes                            |
| `notes_v2.txt`          | new version: paragraph C moved up, sentence B reworded, paragraph D deleted → `version_of` |
| `unrelated.md`          | shares nothing with the others                              |
| `annotations.jsonl`     | 4 annotations (see below)                                   |
| `manifest.json`         | inventory; sha256/size are the real values of these files, mtimes are fictional |
| `texts/<filekey>/page-001.txt` | extracted "page texts" (copies of the text sources)  |

Annotations (all on page 1):

- `a-001` on `notes_v1.txt`, anchored to paragraph C (moved in v2) → **migrated**, ratio 1.0
- `a-002` on `notes_v1.txt`, anchored to the sentence that was reworded in v2 → **shifted**, ratio ≈ 0.75
- `a-003` on `notes_v1.txt`, anchored to paragraph D (deleted in v2) → **orphaned**
- `a-004` on `notes_v2.txt` (the canonical member) → **native**; its contents
  disagree with `a-002` on the same sentence → conflict queue entry

## Commands

From this directory (replace `<SKILL>` with the installed skill path,
e.g. `/skills/weekly-skill`):

```bash
python3 <SKILL>/scripts/version_graph.py \
  --manifest manifest.json --texts-dir texts --out version_graph.json
python3 <SKILL>/scripts/migrate_annotations.py \
  --annotations annotations.jsonl --texts-dir texts \
  --graph version_graph.json --out migration_report.jsonl
python3 <SKILL>/scripts/merge_plan.py \
  --graph version_graph.json --migration migration_report.jsonl \
  --out merge_plan.json \
  --read-only report.pdf --read-only downloads/report.pdf \
  --read-only report_copy.pdf
```

`EXPECTED.md` records the real observed output of these commands (edge
types, similarity ratio, per-annotation statuses, conflict queue, exit
codes) plus hand-checks and negative tests.
