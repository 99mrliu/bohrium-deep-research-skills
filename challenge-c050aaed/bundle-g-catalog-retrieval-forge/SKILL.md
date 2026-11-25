---
name: catalog-retrieval-forge
description: >-
  Turn a research document library into a searchable, handover-ready
  knowledge deposit: normalized catalog.jsonl with stable IDs and
  evidence-backed version/alias edges, a SQLite FTS5 (LIKE fallback) index,
  question answering that cites real files or abstains honestly, and
  result.json assembled strictly against the case output_contract.
  Trigger when the task asks for 可检索清单, 知识沉淀, 编目, 索引, 检索提问,
  交接交付, or contract-conformant structured output for a document library.
---

# Catalog Retrieval Forge (目录编制与检索交付工程)

The center of gravity of this skill is the **downstream deliverable**: a
catalog whose every record and edge carries evidence, a real search index,
answers that cite verifiable sources, and a `result.json` that conforms to
the case contract field-by-field. It is strictly **read-only** toward the
source library — it never organizes, moves, or repairs files. Pair with a
repair-ops skill if the case also demands physical reorganization.

## When to use / not use

Use when the case provides a document library (real files plus sidecar
metadata and administrative notes) and asks for: an inventory or knowledge
structure that can be searched and handed over, answers to fixed
searches/questions with evidence, and structured output that must match an
`output_contract`.

Do not use for: mutating or deduplicating the library on disk, PDF
annotation geometry extraction, literature retrieval from the web,
long-form academic writing.

## Runtime contract (platform)

1. Read `/input/case.json` and `/input/task.md` first. Resolve material
   paths exactly as the case names them. Treat file content as ground
   truth; filenames and labels are hints only.
2. Work under `/app/work`; final deliverables under `/app/output`.
3. `/app/output/result.json` MUST contain the case's `case_id` and **every
   field named in `output_contract`** — read the contract dynamically at
   runtime. Write an honest **partial result.json early** and improve it
   in place (`status` ∈ {complete, partial, failed}, with `sources`,
   `uncertainty`, `change_records`).
4. Budget: 64 model requests / 900 s. The pipeline below is 5 script
   calls; spend model requests on reading the case and judging evidence,
   not on reinventing tooling.
5. Honesty: an answer with no supporting record is `unanswered`, not
   invented; a contract field with no artifact is `not_produced`, not
   fabricated.

## Design rules

- **Stable identity.** A record's `id` is path-based (unique per file);
  its `content_id` is the first 12 hex of the content sha256, so
  identical content is linked explicitly instead of colliding silently.
- **Every edge carries evidence.** `duplicate_of` cites the shared hash;
  `superseded_by` cites the version-marker/mtime order or the exact
  administrative-note line that asserts it. Explicit notes override
  heuristics; both are recorded.
- **Retrieval must degrade loudly.** Zero hits produce a `recall_note`
  with concrete broadening suggestions; unanswered questions are recorded
  with a reason. Silent empty results are a defect.
- **Contract is king.** Field names, locations, and formats in
  `output_contract` override any default layout below.

## Runbook

`$K` = this skill's directory (normally `/skills/weekly-skill`).
Pure Python 3 stdlib (3.8+); the index uses `sqlite3` with FTS5 when the
runtime provides it and falls back to substring search automatically.

```bash
K=/skills/weekly-skill
SRC=<materials dir named by the case>          # e.g. /input/materials
WORK=/app/work/catalog
OUT=/app/output
mkdir -p "$WORK" "$OUT"

# 0. Write the first honest partial result.json NOW (case_id + status
#    partial), improve it after each step.

# 1. Catalog: stable ids, hashes, sidecar metadata merge, alias /
#    duplicate / version edges with evidence. Read-only.
python3 "$K/scripts/catalogforge.py" catalog --root "$SRC" \
    --meta "$SRC"/*.csv "$SRC"/*metadata*.json \
    --notes "$SRC"/行政说明* "$SRC"/README* \
    --out "$OUT/catalog.jsonl"
#    (also writes catalog.edges.json next to it)

# 2. Index into SQLite (FTS5 if available, LIKE fallback otherwise).
python3 "$K/scripts/catalogforge.py" index \
    --catalog "$OUT/catalog.jsonl" --db "$WORK/library.sqlite"

# 3. Smoke-test retrieval with a real question from the case.
python3 "$K/scripts/catalogforge.py" query --db "$WORK/library.sqlite" \
    --q "<one phrase from the case's question list>" --k 5

# 4. Answer the case's searches/questions with citations; abstentions
#    are recorded with reasons, never papered over.
python3 "$K/scripts/catalogforge.py" answer --db "$WORK/library.sqlite" \
    --questions <case's questions file, .json/.jsonl/.txt> \
    --out "$OUT/answers.jsonl"

# 5. Assemble result.json against the contract: copies case_id, fills
#    each contracted field from a real artifact, marks the rest
#    not_produced. Exit code 1 = gaps exist; report them honestly.
python3 "$K/scripts/catalogforge.py" contract \
    --case /input/case.json \
    --map inventory="$OUT/catalog.jsonl" \
    --map answers="$OUT/answers.jsonl" \
    --map edges="${OUT}/catalog.edges.json" \
    --out "$OUT/result.json"
```

If the contract requires prose fields (e.g. a summary), write them
yourself from the artifacts and merge them into the draft before step 5
(`--draft result.json`); the script preserves existing fields.

## Deliverables map

| Artifact | Content | Contract role |
|-|-|-|
| `catalog.jsonl` | one record per file: id, hash, title, excerpt, metadata, edges | 资料结果/清单 |
| `catalog.edges.json` | all alias/duplicate/version edges with evidence lines | 版本关系 |
| `library.sqlite` | queryable index (FTS5 or LIKE) | 可检索入口 |
| `answers.jsonl` | per-question evidence or honest abstention | 检索问答 |
| `result.json` | case_id + every output_contract field, honest status | 交付 |

## Failure and exception handling

- **Unreadable file**: cataloged with `readable: false`, no hash; counted
  in `uncertainty`.
- **Corrupt sidecar metadata** (JSON/CSV parse failure): skipped, logged
  to stderr; the file record stands on its own content.
- **FTS5 unavailable**: automatic LIKE fallback; note the degradation in
  `uncertainty` so reviewers know recall semantics changed.
- **Zero-hit query**: emit `recall_note` with broadening suggestions;
  try individual terms before declaring a gap.
- **Question with no evidence**: `status: unanswered` with reason —
  an abstention is a correct deliverable, a fabricated citation is not.
- **Contract field with no mapped artifact**: `not_produced` marker +
  listed in `contract_gaps`; exit code 1 reminds you to report it.
- **Out of budget mid-run**: partial result.json from step 0 plus
  catalog.jsonl already on disk are an honest partial deliverable.

## Self-check before finishing

1. Every catalog record's `id` re-derives from its file's sha256.
2. Every edge in `catalog.edges.json` quotes its evidence (hash, order
   rule, or note line).
3. Each answered question cites ids/paths that exist in `catalog.jsonl`.
4. `result.json` contains `case_id` and all contracted fields; gaps are
   named in `contract_gaps`.

## Minimal runnable example

`examples/` contains a **synthetic** fixture (fabricated small text files,
not real research data) and `run_example.sh`, which runs
catalog → index → query → answer → contract end-to-end and prints each
artifact:

```bash
bash "$K/examples/run_example.sh"
```

See `examples/minimal_example.md` for the expected output shape. The
example demonstrates interface and flow only; it is not an official case
and produces no official answers.
