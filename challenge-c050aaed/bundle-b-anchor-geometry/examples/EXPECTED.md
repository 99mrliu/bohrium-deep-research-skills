# EXPECTED — real observed results (Python 3.12.14, macOS arm64)

All numbers below were produced by actually running the commands in README.md
in a fresh `mktemp` directory. They are deterministic: same fixtures → same
bytes.

## 1. anchor_resolve → exit 0

```
anchor_resolve: 6 annotations -> .../resolved.jsonl
  status=resolved: 6
```

Per-anchor results (verbatim from resolved.jsonl):

| id | anchor_kind | column_count | coverage | page_origin | anchored_text |
|----|-------------|--------------|----------|-------------|---------------|
| ann-001 | quad | 1 | 0.605769 | text | `lazy dog` |
| ann-002 | quad | **2** (gutter x=277.0) | 0.58209 | text | `kilo lima mike november oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee zulu apple banana cherry date` |
| ann-003 | quad | 2 | 0.555556 | text | `elder fig grape hazel iris` |
| ann-004 | nearest_block | 1 | null | text | `the riverbank at dawn today` (distance 352.142 from rect [560,88,600,100] to block bbox [72,104,228,116]) |
| ann-005 | quad | 1 | 0.678179 | ocr | `all measured coastal stations` ← drifted quad lost the word "across" (exactly half its area covered → excluded by the strict >0.5 rule) |
| ann-006 | quad | 1 | 0.593284 | ocr | `during the last four decades` |

word_indices are recorded per anchor (e.g. ann-001: [7, 8]; ann-002:
[20,21,22,23,24, 30,31,32,33,34, 5,6,7,8,9, 15,16,17,18,19] — note the column
jump in the middle). All original metadata (type, category, color_rgb,
contents, author) is preserved verbatim on every record.

## 2. Two-column hand-check (the core claim)

ann-002 is one sentence flowing across the column break: end of column 1
("kilo … tango") continues at the top of column 2 ("uniform … date").

* **Column-aware result (ours):**
  `kilo lima mike november oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee zulu apple banana cherry date`
  — verified by hand against the fixture: this is exactly col-1 L3, col-1 L4,
  then col-2 R1, col-2 R2. Correct reading order. ✅
* **Naive serial join (same matched words, raw file order):**
  `uniform victor whiskey xray yankee zulu apple banana cherry date kilo lima mike november oscar papa quebec romeo sierra tango`
  — the column-2 head sorts BEFORE the column-1 tail. Garbled. ❌

ann-003 (single quad inside column 2) resolves to `elder fig grape hazel iris`
— the column-2 line, no column-1 words leaked in. ✅

## 3. anchor_verify on resolved.jsonl → exit 0

```
annotation   page   ratio    class
ann-001      1      1.0      exact
ann-002      2      1.0      exact
ann-003      2      1.0      exact
ann-004      1      1.0      exact
ann-005      3      0.892308 drifted
ann-006      3      1.0      exact
summary: {"classified": 6, "drifted": 1, "drifted_rate": 0.1667, "exact": 5,
          "exact_rate": 0.8333, "failed": 0, "failed_rate": 0.0,
          "normalized": 0, "skipped": 0, "total": 6}
```

ann-005 is independently caught: the center-inside re-clip includes "across"
(its center sits on the drifted quad's edge) while the recorded text lacks it →
ratio 0.892308 → **drifted**. ✅ (This is why the second pass uses a different
rule than the first.)

## 4. drift_correct → exit 3 (one unrecoverable remains, by design)

```
drift_correct: 6 records -> .../corrected.jsonl
  correction=corrected: 1
  correction=not_checked: 3
  correction=skipped: 1
  correction=unrecoverable: 1
  ann-005: corrected ratio=0.957746 old_bbox=[87, 88, 234, 101] new_bbox=[72.0, 88.0, 234.0, 100.0]
  ann-006: unrecoverable ratio=0.463768 old_bbox=[70, 102, 204, 118] new_bbox=None
```

* ann-005: target `contents` = "across all measured coestal station" (2 char
  errors vs the OCR words). Best window "across all measured coastal stations"
  scores 0.957746 ≥ 0.75 → **corrected**, bbox moves from the drifted
  [87,88,234,101] back to the true [72,88,234,100]. ✅
* ann-006: alien quote "Quantum bananas orbit the purple toaster"; best window
  scores 0.463768 < 0.75 → **unrecoverable**, record untouched, never
  guessed. ✅ Exit code 3 signals the leftover unrecoverable anchor.

## 5. anchor_verify on corrected.jsonl → exit 0

All 6 anchors classify **exact** (exact_rate 1.0, failed 0): the corrected
anchor now re-clips to its own recorded text, and the unrecoverable one was
geometrically consistent all along (its quad genuinely covers those words).

## 6. Negative tests

* **Seeded bad anchor:** ann-001 `anchored_text` overwritten with
  "zzz nonsense qqq garbage" → verify classifies it `failed` (ratio 0.25) and
  **exits 3**. ✅
* **--help:** all three scripts exit 0. ✅
* **Fatal inputs:** missing `--annotations`/`--resolved` file → exit 2 with
  `FATAL:` on stderr. ✅
