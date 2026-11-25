# Methodology — retrieval-run-warden

Every check the warden performs is listed here so a reviewer can re-derive each
verdict by hand. The warden trusts nothing the run says about itself; its only
ground truth is the **evidence pool** (`<run>/evidence/`), which it re-hashes
and re-scans on every audit.

## 0. The run-directory layout contract

Any run — produced by `lite_search.py` or by the agent's own search — is
auditable iff it provides:

```
<run>/
  candidates.json   JSON object with "candidates": [ {doi, title,
                      evidence:{copy_name, sha256_12, json_index},
                      dedup_key, ...} ]
  candidates.md     human-readable rendering of the same claims (DOIs in text)
  run_log.jsonl     one JSON object per line; required steps:
                      "prisma"     counts {identified, after_dedup, included}
                      "exclusions" notes.items[] each with {key, reason}
  evidence/         byte-identical copies of every consulted source file,
                    named <sha256_12>__<original-basename>
```

## 1. lite_search.py — the honest baseline run

Deliberately simple, deterministic, stdlib-only:

1. **discover** — walk `--input` (and optional `--corpus`) for `.json` files,
   skipping `case.json`, `result.json` and the run's own artifacts.
2. **evidence_copy** — SHA-256 each snapshot, copy it byte-identically to
   `evidence/<sha256_12>__<basename>` (first 12 hex chars).
3. **ingest** — classify payload shape and normalize records:

   | shape | source_type |
   |-|-|
   | `{"message": {"items": [...]}}` | crossref |
   | `{"resultList": {"result": [...]}}` | europepmc |
   | `{"results": [...]}` | openalex |
   | `{"records": [...]}` | generic-records |

   Per record: `doi` (lower-cased, `https://doi.org/` prefix stripped), `title`
   (first element if list; OpenAlex `display_name`), `abstract` (HTML tags
   stripped; OpenAlex inverted index reconstructed), `year`, plus an evidence
   pointer `{original_path, copy_name, sha256_12, json_index}`. Missing
   metadata stays empty — never invented.
4. **dedup** — key = `doi:<doi>` when present, else `title:<lowercase alnum
   title>`; first record wins, later copies are appended to `also_in` and
   logged as exclusions with reason `DUPLICATE_OF`.
5. **score** — query terms = lowercase alnum tokens (len > 2,
   stopword-filtered) + CJK bigrams. Per term: **+2** if literally present in
   the title, **+1** in the abstract. Score 0 ⇒ exclusion with reason
   `NO_TERM_MATCH`. `zero_hit_terms` = terms matched by no record.
6. **artifacts** — `candidates.json`/`candidates.md` (ranked, provenance
   bearing) and `run_log.jsonl` with the steps above plus `prisma`
   (identified → after-dedup → scored → included).

Exit codes: 0 = run completed, 2 = zero records identified.

## 2. Gate ANTI-FABRICATION (ERROR on any miss)

- **Evidence integrity:** every file in `evidence/` is re-hashed; the first 12
  hex chars must match its filename prefix → else `EVIDENCE_HASH_MISMATCH`.
  Missing evidence dir → `EVIDENCE_DIR_MISSING`.
- **Identifier presence:** the warden collects claimed identifiers —
  - every `doi` and `title` in `candidates.json`,
  - every DOI matching `10\.\d{4,9}/\S+` in the raw text of `candidates.md`,
  - every DOI matching the same regex in the raw text of `result.json`.

  Each DOI is normalized (lower-case, prefix stripped, then squashed to
  alnum-only) and each title is squashed (lower-case, alnum + CJK only); the
  probe must be a substring of the identically squashed content of at least
  one evidence copy. Any miss → `FABRICATION_SUSPECT` naming the identifier
  and its origin. Re-check by hand: `grep -riF '<doi>' <run>/evidence`.
- **Provenance consistency:** each candidate's `evidence.copy_name` must exist
  (`EVIDENCE_COPY_MISSING`/`PROVENANCE_MISSING`) and its claimed `sha256_12`
  must equal the re-hash (`HASH_CLAIM_MISMATCH`).

## 3. Gate FLOW (ERROR on any mismatch)

- The warden independently re-parses every evidence copy and recomputes:
  `identified` = all records; `after_dedup` = unique dedup keys (DOI first,
  else normalized title); `included` = number of candidates. Each is compared
  with the `prisma` step of `run_log.jsonl` → `COUNT_MISMATCH` (or
  `PRISMA_MISSING` if absent).
- **Exclusion ledger:** every identified key that is not included must appear
  in the `exclusions` step with a non-empty `reason` → otherwise
  `EXCLUSION_LEDGER_GAP` / `EXCLUSION_WITHOUT_REASON`. Ledger keys matching no
  identified record → `EXCLUSION_LEDGER_PHANTOM`.

## 4. Gate CONTRACT (ERROR on any violation)

Against `<out>/result.json` and `case.json`:

- file exists and parses → else `RESULT_MISSING` / `RESULT_UNPARSEABLE`;
- `case_id` equals the case's → else `CASE_ID_MISMATCH`;
- every `output_contract` field is present and non-empty
  (`CONTRACT_FIELD_EMPTY`); string values starting with `/` must be existing
  files (`CONTRACT_PATH_DANGLING`) located under the output dir
  (`CONTRACT_PATH_OUTSIDE_OUTPUT`);
- `status` ∈ {success, partial, failed} (`STATUS_INVALID`);
- `success` requires empty `uncertainty` (`SUCCESS_WITH_UNCERTAINTY`);
- `partial` requires non-empty `uncertainty` (`PARTIAL_WITHOUT_UNCERTAINTY`)
  — an honest partial must say what is missing.

## 5. Gate ANOMALY (WARN only — never blocks)

| code | trigger | meaning |
|-|-|-|
| `ZERO_HIT_TERMS` | query terms matched by no record (from the `score` step) | honest coverage gap; belongs in `uncertainty` |
| `EMPTY_SNAPSHOT` | an evidence file parsed to zero records | legitimate empty page or failed query — check |
| `HIGH_DEDUP_RATIO` | duplicates > 50% of identified records | pool may be near-duplicate snapshots |
| `SINGLE_SOURCE_POOL` | ≤1 evidence file or ≤1 source type | results rest on a single source |

## 6. Severity policy and overall verdict

- `ERROR` = blocks success: any ERROR flips the overall GATE to **FAIL**,
  exit code 1. Zero ERRORs ⇒ **PASS**, exit code 0 (WARNs may remain).
- A FAIL report is a deliverable, not an accident: it tells the reviewer
  exactly what could not be verified.
- `--fix-result` rewrites **only** `<out>/result.json`: fills contract fields
  from existing artifacts (staging byte-identical copies of `candidates.md`
  and `run_log.jsonl` into the output dir if absent), sets `status=success`
  only when zero ERRORs and zero prior uncertainty exist, otherwise
  `status=partial` with every ERROR and WARN finding listed in `uncertainty`,
  and refreshes `sources` with the evidence hashes. It never edits
  `candidates.*`, `run_log.jsonl`, or `evidence/` — repairing those would be
  laundering, so fabrication findings survive the repair by design.

## 7. Known limits (state them, do not patch around them)

- The warden verifies **presence-in-evidence**, not the truth of the source
  itself: a fabricated *snapshot* copied into `evidence/` passes the
  anti-fabrication gate. Pair with snapshot verification (schema checks,
  trust gating) when organizer inputs cannot be taken at face value.
- Presence checking is literal (squashed substring). A candidate whose title
  was paraphrased rather than copied from the snapshot will be flagged — that
  is intentional: candidates must quote their evidence.
- The DOI regex `10\.\d{4,9}/\S+` covers standard DOIs; exotic identifier
  schemes (handles, PMIDs) are not extracted from free text — keep them in
  structured fields if they matter.
- FLOW recomputation re-implements parsing independently of lite_search but
  assumes the same snapshot shapes; unrecognized shapes count as zero records
  and surface as `EMPTY_SNAPSHOT` warnings plus likely `COUNT_MISMATCH` errors.
- lite_search ranking is literal term presence: no synonym expansion, no
  semantic matching. It is a floor, not a ceiling — the warden audits
  whatever better run the agent produces, as long as the layout contract is met.
