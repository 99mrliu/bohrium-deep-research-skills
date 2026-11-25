# Curation schema and graph semantics

## 1. Files

`prepare_case.py` creates:

- `sources.json`: `{schema_version, sources:[...]}`; every source has `source_id` and `paragraphs`. Paragraph records have `paragraph_id`, `page` (integer or null), and normalized `text`. Optional source metadata includes title, relative path, media type, and SHA-256.
- `curated.json`: agent-authored semantics. The builder never derives these meanings from target names.

Source evidence object used everywhere:

```json
{
  "source_id": "S1",
  "paragraph_id": "S1-P0007",
  "page": 3,
  "quote": "A verbatim substring of the registered paragraph."
}
```

If the registered paragraph has `page: null`, use `page: null` or omit page from evidence. Never estimate a page from paragraph order. Quotes may be short spans but must be long enough to preserve attribution, value, and modality in context. Additional evidence spans can supply conditions and comparators.

## 2. Top-level curation object

```json
{
  "schema_version": "claim-evidence-curation/1.0",
  "conditions": [],
  "observations": [],
  "claims": [],
  "field_results": [],
  "uncertainties": []
}
```

IDs must be nonempty and unique within each collection. References must point to existing IDs. Additional target-field IDs are rejected; missing target IDs become honest `extraction_failed` records.

## 3. Condition record

Required keys:

| Key | Type | Meaning |
|---|---|---|
| `condition_id` | string | Stable local ID |
| `description` | string | Complete applicable setting, with no unsupported additions |
| `evidence` | nonempty list | One or more exact spans supporting all components |

Examples of dimensions: sample/material identity, substrate/population, data source, dose, solvent, temperature, pressure, duration/time point, instrument/method, and scope qualifiers. Use multiple conditions when values differ by run; do not combine incompatible settings into one ambiguous string.

## 4. Observation record

```json
{
  "observation_id": "OBS-1",
  "kind": "quantitative_observation",
  "scalar": 82,
  "units": "% yield",
  "statistic": "mean of three independent runs; SD = 2 percentage points",
  "comparator": "Control B under COND-1",
  "condition_ids": ["COND-1"],
  "evidence": [{"source_id":"S1","paragraph_id":"S1-P0008","page":4,"quote":"..."}]
}
```

`kind` is `quantitative_observation`, `qualitative_observation`, or `method_observation`. All records explicitly contain `scalar`, `units`, `statistic`, and `comparator` (null permitted where genuinely inapplicable), plus condition IDs and evidence. Quantitative records require non-null scalar and units and at least one condition. No unit conversion or recomputation is performed.

A cited quantitative observation can be used, but its linked claim must remain `prior_work_cited_claim`, and field interpretation must be `reported_prior_work`. Notes must make its non-current status clear.

## 5. Claim record

Required keys:

| Key | Type/values |
|---|---|
| `claim_id` | Unique string |
| `kind` | One of the five discourse kinds |
| `text` | Faithful bounded paraphrase or proposition, not a fabricated quotation |
| `epistemic_status` | Explicit status such as `author_conclusion`, `untested_hypothesis`, `cited_hedged_claim`, `declared_limitation`, `directly_reported_method` |
| `modality` | `declarative`, `speculative`, `reported_and_speculative`, or another explicit non-empty source-faithful label |
| `hedges` | List of literal hedge/scope strings; each must appear in claim/evidence |
| `attribution` | Object with `speaker` and `origin: author_current_paper | cited_work`; optional citation string limited to supplied metadata |
| `condition_ids` | List, possibly empty where no experimental scope applies |
| `supporting_observation_ids` | List of observations the claim uses as support |
| `promotion_allowed` | Required `false` for hypothesis, cited claim, and limitation |
| `evidence` | Nonempty exact-span list including attribution/modality |

`author_conclusion` must be current-author and declarative, with status `author_conclusion` or `concluded_by_authors`. The negative guard is provenance-based, not a numeric keyword classifier. It deliberately rejects an “author conclusion” whose attribution remains cited even if the paraphrase deletes its hedge.

## 6. Field curation record and resolution

Minimal observation-backed field:

```json
{
  "field_id": "requested_id",
  "status": "reported",
  "observation_ids": ["OBS-1"],
  "claim_ids": ["CL-CONC"],
  "notes": "How the source answers the target."
}
```

For one observation-backed `reported` field, the builder copies `scalar`, `units`, `statistic`, and `comparator` from the observation and derives the condition from linked condition descriptions. Any explicit disagreement is rejected. Own `evidence` is optional; observation, claim, and condition evidence are merged and deduplicated. First evidence becomes primary unless `paragraph_id` and `quote` explicitly choose another merged item.

Claim-only qualitative reported field additionally supplies `scalar`, `units`, `statistic`, `experimental_condition`, and `comparator`. When linked to a guarded kind it also supplies the matching `interpretation`:

| Linked kind | Required reported interpretation |
|---|---|
| `hypothesis_speculation` | `reported_hypothesis` |
| `prior_work_cited_claim` | `reported_prior_work` |
| `limitation` | `reported_limitation` |

For a guarded claim attached to a `not_reported` target, use `interpretation: not_an_established_author_conclusion` and exact evidence explaining why no established answer exists.

Other field statuses:

- `not_reported`: scalar null; evidence and notes mandatory; no guessed value.
- `source_conflict`: scalar null; at least two linked observations and at least two source paragraph locations. Keep incompatible details in notes/uncertainties.
- `extraction_failed`: scalar null; evidence can be empty; notes identify handoff. Empty primary location is normalized to `paragraph_id: null`, `quote: ""`.

The public output removes internal `observation_ids`, `claim_ids`, and `interpretation` from each field (the graph preserves link edges), emits all required output keys, sets `condition` equal to `experimental_condition`, and mirrors the array to `field_results`.

## 7. Graph node and edge types

Node `type`:

- `case`
- `source`
- `paragraph`
- `experimental_condition`
- `observation`
- `claim`
- `target_field`

Directed edge `type`:

| Edge | Meaning |
|---|---|
| `grounded_in` | Condition/observation/claim → paragraph; edge carries the exact evidence object |
| `observed_under` | Observation → experimental condition |
| `supported_by` | Claim → observation offered as support; not proof |
| `scoped_by` | Claim → applicability condition |
| `realized_by` | Requested field → observation |
| `interpreted_with_epistemic_layer` | Requested field → claim without changing the claim kind |

Only cited paragraphs appear as paragraph nodes. Node payloads preserve IDs, claim classifications, values, conditions, and evidence for independent audit.

## 8. Build status aggregation

If every target has a completed adjudication (`reported`, scoped `not_reported`, or documented `source_conflict`) and at least one is reported, run status is `answered`. Any `extraction_failed` with at least one reported field gives `partial`; all non-reported or all failed is `insufficient_evidence`. Input structural errors are separately handled as `input_error` by initialization. The agent can retain an early partial instead of submitting an invalid graph.

## 9. Output keys checked by the independent validator

Top-level required: `case_id`, `status`, `result`, `claims`, `uncertainties`; this implementation also emits `sources` and `change_records`.

Every field in both mirrors has:

`field_id`, `status`, `scalar`, `units`, `statistic`, `experimental_condition`, `condition`, `comparator`, `paragraph_id`, `quote`, `evidence`, `notes`.

Every evidence item uses `source_id`, `paragraph_id`, `quote`, with page where known. Each public claim additionally receives a primary `source_id` and `location: {paragraph_id, page}` from its first evidence item. The validator also checks graph endpoints, graph case/status consistency, every target-field node, quote substrings, mirrors, and claim non-promotion guards.
