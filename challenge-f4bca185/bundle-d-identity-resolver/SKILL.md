---
name: bundle-d-identity-resolver
description: Identity-first cleaning and standardization for literature-extracted data tables. Resolves material/sample/experiment identity with cautious, lexicon-driven name canonicalization (aliases like TiO2/titanium dioxide merge; different salts, phases, dopants, compositions and contexts never do), distinguishes repeated extractions from independent repeated experiments, adjudicates duplicate candidates with explainable evidence and decision states (exact_duplicate / likely_duplicate / conflict / review / not_duplicate), merges conservatively with deterministic representatives and full member lineage, never averages conflicting values, and emits cleaned records, a duplicate report, a review queue, a rule-coded change log, an audit and result.json. Use when a batch of JSON/CSV records extracted from papers must be deduplicated and standardized without silently mixing sources, contexts or specimens.
---

# Identity Resolver — literature data cleaning with explainable duplicate adjudication

## What this skill is for

You have a batch of records extracted from scientific papers (JSON or CSV,
possibly nested per study) and you must produce a clean, statistics-ready
table **without** the classic failure modes of naive dedup:

- merging "TiO2 rutile" with "TiO2 anatase" (different samples),
- merging a repeated *extraction* of one row with an independent repeated
  *experiment* (different evidence),
- merging corroborating values from two different papers (different sources),
- averaging away a genuine measurement conflict,
- losing track of which rule changed which value.

This skill resolves **identity first** (material/sample/metric/context/source
keys), adjudicates duplicate candidates pair by pair with explicit evidence,
and only merges what the rules approve. Everything it refuses to decide goes
to a review queue; every change carries a rule id.

It is deliberately **not** a units-first converter and not a renderer: unit
handling exists only to make identity comparison safe and the data table
complete. Unknown or missing units/values stay null and are flagged.

## Inputs

- `--case` (default `/input/case.json`): JSON (flat list, `{"records": [...]}`,
  nested `studies -> records`, or embedded `{"columns": [...], "rows": [[...]]}`
  tables) or a CSV file. JSON may carry `case_id`, `synthetic`,
  `output_contract`.
- `--task` (default `/input/task.md`): task text, recorded in the audit.
- `--lexicon` (optional): customized copy of `references/synonyms.json`.
- `--work` (default `/app/work`), `--out` (default `/app/output`).

Missing values (`"N/A"`, `"not reported"`, `"—"`, `""`, …) become JSON null
and stay null. Records with no material or no metric are kept but excluded
from duplicate blocking and queued for review.

## Invocation

```bash
python3 scripts/identity_resolver.py \
    --case /input/case.json --task /input/task.md \
    --work /app/work --out /app/output
```

Python 3.10+, standard library only. All flags are overridable. The script
writes an honest partial `result.json` immediately after start and upgrades it
stage by stage; unreadable/malformed input exits with code 2 and
`status=input_error` plus a partial result naming the failing stage.

## Pipeline

1. **Ingest** — flatten nested JSON (inheriting study-level source/context
   into rows), read CSV, keep original raw rows.
2. **Normalize (rules N/V/U/F)** — unicode/case/whitespace folding; *exact
   full-string* lexicon alias lookup for materials/metrics/phases; dopant and
   phase split out of name strings but kept as identity; value parsing
   (scalar / range / missing / text); unit normalization and conversion to
   canonical units with recorded formulas; context normalization
   (e.g. 25 °C -> 298.15 K). No fuzzy matching: different salts, hydrates,
   stoichiometries, dopants and phases stay distinct.
3. **Identity keys** — `sample_key` (material+phase+dopant+composition+
  morphology), `metric_key`, `context_key`, `source_key`; full-row
  fingerprint for exact-repeat detection.
4. **Adjudication (rules D)** — deterministic blocking; pairwise evidence
   (same source/sample/metric/context/locator/experiment label, value
   relation, fingerprint) with a transparent score and a rule-coded state:
   `exact_duplicate`, `likely_duplicate`, `conflict`, `review`,
   `not_duplicate` (incl. `D-005` independent replicate and `D-006`
   cross-source corroboration).
5. **Conservative clustering** — union only exact/likely duplicates; the
   representative is a real member row chosen deterministically (most complete,
   then smallest record id); members and lineage are retained; each retained
   experiment gets a distinct `experiment_id`; conflicts stay in separate
   clusters and are never averaged.
6. **Self-check invariants** — every run verifies: no cross-source merge, no
   cross-context merge, conflicts never merged, representative is a member
   row, no member rows lost. A failure degrades status to `partial`.

## Outputs (under `--out`)

| file | content |
|---|---|
| `cleaned_records.csv` / `.json` | one row per cluster with representative values, member ids, lineage (`members[]` in JSON) |
| `duplicate_report.json` | every candidate pair: evidence, score, rule, state; cluster inventory |
| `review_queue.json` | conflicts, ambiguous pairs and anomalies needing a human; nothing here was merged silently |
| `change_log.json` | every automated change with rule id, before/after, record id |
| `audit.md` | status, counts, sources, invariants, rule counts, unresolved items, contract coverage |
| `result.json` | `case_id`, `status` (`success`/`partial`/`input_error`), `summary`, `counts`, `sources`, `uncertainty`, `unresolved`, `change_records`, `invariants`, `artifacts`, plus every `output_contract` field from the case (dict/list/string; unfillable fields stay null and are listed in `unresolved`) |

## Customization

- `references/synonyms.json` — edit field aliases, material/metric/phase
  aliases, unit table, plausible ranges. Matching is always full-string after
  normalization; add aliases, do not loosen the matcher.
- `references/identity-adjudication.md` — full rule catalog (ids used in the
  change log), key semantics, decision-state definitions, precedence and
  boundaries.

## Self-check

```bash
python3 scripts/selfcheck.py                    # runs all checks
python3 scripts/selfcheck.py --refresh-examples # regenerate examples/synthetic-output
```

Verifies: deterministic byte-identical repeat runs; aliases merge; phases /
dopants / hydrates / contexts / sources never merge; independent replicates
stay distinct; conflicts are kept separate and never averaged; missing and
unknown units stay null; ranges stay intervals; out-of-range is flagged, not
altered; CSV ingestion works; malformed JSON and missing files produce honest
`input_error` partials with exit code 2.

## Boundaries and failure handling

- Cross-source pairs are only ever *reported* (corroboration), never merged.
- Records lacking material or metric cannot be blocked; they pass through
  flagged, never force-matched.
- Non-numeric and interval values are kept as-is; no midpoint is fabricated.
- A value with an unknown unit is compared raw only; it can be an exact
  duplicate but never a converted match, and it is flagged.
- Same identity + different value = `conflict`: both rows survive, the
  representative value of each cluster is one real member's value.
- Large inputs: blocking keeps comparisons quadratic only inside blocks;
  beyond ~50k rows per block, split the input by study first.
- The lexicon ships common aliases; unknown names are stable identities of
  their own (logged as `lexicon_miss`), never auto-merged by similarity.

## Example

`examples/` contains a **synthetic, clearly marked** case (aliases, rutile vs
anatase, N-doping, exact repeat, independent replicate, cross-source
corroboration, identity conflict, unknown/missing units, missing value, range
value, hydrate vs anhydrous salts), its task file, a CSV variant, and the
actual deterministic outputs under `examples/synthetic-output/` with a
run record in `examples/run-record.md`. It demonstrates the interface only;
it is not an official case result.
