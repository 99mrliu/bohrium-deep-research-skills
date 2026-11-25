# Methodology — incremental-import-reconciler

Every rule the engine applies is written down here so a reviewer can re-derive
each classification without trusting the code.

## 1. Prior-state discovery (deterministic order)

1. **Embedded in the case file.** If `case.json` contains any of
   `import_state`, `already_imported`, `existing_library`, that value is parsed
   as the state (first matching key wins).
2. **Filename scan.** All `.json` files under `--input` (and `--corpus`) whose
   lowercased name contains `import_state`, `imported`, `state` or `library`
   are tried in sorted path order. The first file that (a) parses as JSON and
   (b) holds a recognized state key wins.
3. **Nothing found → initial import mode.** The run proceeds with an empty
   state, says so in the digest (`"mode": "initial"`), the manifest and the
   report, and every candidate classifies as NEW. This is the only case where
   an empty state is legitimate, and it is never silent.

Recognized state keys (top level): `imported`, `records`, `state`, `entries`,
`library`. The value may be an object keyed by DOI/title or a list of entry
objects. Entry fields read: `doi`, `title`, `year`, `venue` (or `journal`),
`authors` (or `author`, string or list), `abstract`, `imported_at`, `source`,
`provenance`. A stored fingerprint/`hash`/`version` is treated as advisory
only — fingerprints are always recomputed with the current definition so both
sides of a comparison use identical normalization.

**Corrupt-state policy.** A file that matches the state-name pattern but fails
JSON parsing, or whose recognized state key holds malformed data (non-object
entries, non-object/non-list state value), aborts the run with exit code 3 and
a FATAL message. Falling back to an empty state would re-import the entire
library and is therefore treated as the worst possible outcome — strictly
worse than delivering partial. A name-matching file that parses cleanly but
holds no recognized state key is simply not a state file: it is skipped with a
note, not fatal.

## 2. Candidate pool extraction

All `.json` files under `--input` and `--corpus` are walked, excluding
`case.json`, `result.json` and the discovered state file(s). Recognized
snapshot shapes:

| shape | payload |
|-|-|
| `crossref` | `{"message": {"items": [...]}}` |
| `crossref-single` | `{"message": {"DOI": ...}}` |
| `europepmc` | `{"resultList": {"result": [...]}}` |
| `openalex` | `{"results": [...]}` |
| `generic-records` | `{"records": [...]}` |

Files that fail to parse or match no shape are skipped and ledgered in the
report (`PARSE_ERROR` / `SCHEMA_UNRECOGNIZED`) — they are pool defects, not
state corruption, so they are non-fatal. Every consulted file is hashed into
`evidence/evidence_index.json` with its role (`case` / `state` / `pool`).

Per-record normalization: title (first element if list), authors (Crossref
given+family joined; EuropePMC `authorString` split on commas; OpenAlex
`authorships[].author.display_name`), year (Crossref `issued.date-parts[0][0]`,
EuropePMC `pubYear`, OpenAlex `publication_year`), venue (`container-title[0]`
/ `journalTitle` / `primary_location.source.display_name`), DOI (lowercased,
`https://doi.org/` and `doi:` prefixes stripped, trailing dot removed),
abstract (HTML tags stripped; OpenAlex inverted index reconstructed).

## 3. Content fingerprint

```
fingerprint = sha256( "|".join([
    norm(title), str(year or ""), norm(venue),
    ";".join(norm(a) for a in authors), norm(abstract)
]) ).hexdigest()[:12]
```

where `norm(x)` = lowercase, all whitespace runs collapsed to one space,
stripped. The same function is applied to state entries and candidates, so a
fingerprint equality means "the five core fields agree after normalization",
nothing more, nothing less.

## 4. Classification precedence (per candidate, in this exact order)

1. **SUSPECT — `NO_IDENTIFIER`**: neither DOI nor title present. The record
   cannot be matched or imported safely; excluded with reason.
2. **SUSPECT — `YEAR_IMPLAUSIBLE`**: year present but outside 1450–2100.
   Excluded with reason (missing year is *not* suspect — metadata is often
   incomplete; an absurd year is a defect).
3. **State match**: DOI match first (exact, normalized); if the candidate has
   no DOI or no DOI match exists, normalized-title match
   (`title_key` = lowercase with all non-word characters removed, CJK kept).
   No match at all → **NEW** (`NO_STATE_MATCH`) → imported.
4. On a **DOI match**, if both sides have titles and their `title_key`s
   disagree → **CONFLICT** (`DOI_MATCH_TITLE_MISMATCH`). Same identifier,
   contradictory core identity: queued for human resolution, state untouched.
5. On a **title match**, if both sides have DOIs and they differ →
   **CONFLICT** (`TITLE_MATCH_DOI_MISMATCH`). Same identity, contradictory
   identifier: queued, state untouched.
6. Otherwise, fingerprint equal → **ALREADY_IMPORTED**
   (`DOI_MATCH_IDENTICAL` / `TITLE_MATCH_IDENTICAL`) → skipped, ledgered.
7. Otherwise → **UPDATED** (`DOI_MATCH_CONTENT_CHANGED` /
   `TITLE_MATCH_CONTENT_CHANGED`): a field-level diff over
   `title, year, venue, authors, abstract` (old → new) is computed, the state
   entry is updated in place (original `imported_at` kept, `updated_at` and
   `previous_fingerprint` set) and a change record is appended.

Only NEW and UPDATED mutate the state. CONFLICT, ALREADY_IMPORTED and SUSPECT
never do.

## 5. Conflict policy

Conflicts are the one classification where automation is *wrong by design*: a
DOI with two titles means either a source error or a genuinely reassigned
identifier, and only a human with case context can tell which. The engine
therefore (a) imports nothing for the conflicted candidate, (b) leaves the
state entry untouched, (c) renders both records side by side in the report,
and (d) expects the resolution to be documented (in `result.json`
`uncertainty`, or by fixing the defective pool file and re-running once).
Hand-editing `updated_state.json` to force an outcome breaks the audit chain
and voids the idempotency proof.

## 6. Idempotency semantics

`--verify-idempotent` performs a **real second execution**, not a comparison
of claims: it reloads the just-written `updated_state.json` from disk through
the same state loader (corrupt file → exit 3), re-walks `--input`/`--corpus`
to rebuild the pool, and re-classifies every candidate. The run is idempotent
iff the second pass yields **0 NEW and 0 UPDATED**; the engine prints
`IDEMPOTENT: second pass = 0 adds, 0 updates` and exits 0, otherwise it exits
1 and prints the offending decisions. CONFLICTs are *expected* to recur in the
second pass — they were never applied, so the state still contradicts them;
recurring conflicts are queued items, not state changes, and are reported as
such. The property proven is: **applying the same pool twice changes the state
exactly once.**

## 7. Known limits (state them, do not patch around them)

- **Title-only matching is lexical, not semantic.** When either side lacks a
  DOI, identity reduces to normalized-string equality of titles; paraphrases,
  translations and subtitle variants will classify as NEW (duplicate risk) or
  occasionally CONFLICT. Say so in `uncertainty` when title-only matches
  decided a classification.
- **State schema is assumed, not validated.** The documented entry fields
  (Section 1) are what the engine can read; organizer states with other
  schemas parse as far as possible, and fields that cannot be read normalize
  to empty — which makes fingerprints differ and can surface as UPDATED.
  Check the report's diffs before accepting bulk updates on a real case.
- **No pool-internal dedup.** Two identical records inside the same new pool
  are classified independently; the second one will classify against the
  *original* state (NEW twice) and the later add overwrites the earlier under
  the same state key. The change ledger still shows both. If a case ships
  heavily duplicated pools, note it; do not silently collapse.
- **Fingerprint scope is the five core fields.** References, license, PDF
  links etc. are not part of the fingerprint; changes confined to those fields
  classify as ALREADY_IMPORTED. This is deliberate (import stability) and
  documented here so it is not mistaken for an omission.
- **Fully offline.** The engine never fetches; coverage is bounded by the
  local pool, and that bound belongs in `uncertainty`.
