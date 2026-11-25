# Corpus authenticity audit (上游数据真实性核验)

- documents: 5; findings: 5; duplicate pairs: 1

| record | file | declared lang | detected lang | conf | DOI | body chars |
|-|-|-|-|-|-|-|
| copy_of_en003.txt | copy_of_en003.txt | — | en | 0.957 | — | 311 |
| rec-pt-001 | records.jsonl | pt | pt | 0.842 | 10.0000/synth.pt.001 | 0 |
| rec-mislabeled-002 | records.jsonl | en | pt | 0.7 | — | 0 |
| rec-en-003 | records.jsonl | en | en | 0.957 | 10.0000/synth.en.003 | 0 |
| short_note.txt | short_note.txt | — | und | 0.0 | — | 13 |

## Findings

- **missing_doi** `copy_of_en003.txt`:  → do not fabricate; mark DOI as unavailable
- **language_label_mismatch** `rec-mislabeled-002`: declared=en detected=pt confidence=0.7 → trust body text over label; record both
- **missing_doi** `rec-mislabeled-002`:  → do not fabricate; mark DOI as unavailable
- **missing_doi** `short_note.txt`:  → do not fabricate; mark DOI as unavailable
- **language_undetermined** `short_note.txt`:  → flag for manual inspection; exclude from per-language counts

## Duplicate / near-duplicate pairs

- `copy_of_en003.txt` ≡ `rec-en-003` (similarity 1.0) → count once; keep both attributions
