# Identity adjudication reference

Rule catalog, key semantics and decision states used by
`scripts/identity_resolver.py`. Rule ids appear in `change_log.json`,
`duplicate_report.json`, `review_queue.json` and `audit.md`, so any output
value can be traced to the rule that produced it and to the input row.

## 1. Normalization philosophy

- Only lossless-ish surface transforms: NFKC unicode folding, subscript/
  superscript digit folding (TiO₂ -> TiO2), unicode-minus unification, case
  folding, whitespace and separator collapse.
- Alias resolution is **exact full-string lookup** in `references/synonyms.json`
  after normalization. There is no fuzzy/embedding similarity: the tool never
  decides that two names are "close enough".
- Consequently different salts, hydrates (Na2SO4 vs Na2SO4·10H2O),
  stoichiometries, dopants (TiO2 vs TiO2:N) and phases (rutile vs anatase)
  are always different identities unless a human lists them as aliases.
- Unknown names are not errors: the normalized token itself is the identity,
  logged as `N-006 lexicon_miss` (info level).

## 2. Identity keys

| key | built from | semantics |
|---|---|---|
| `source_key` | normalized DOI/title/source id | provenance boundary; merges NEVER cross it |
| `sample_key` | material canonical + phase + dopant + composition + morphology | the physical specimen identity |
| `metric_key` | canonical metric name | what was measured |
| `context_key` | normalized context fields (temperature in K, pressure in kPa, atmosphere, medium, method, substrate, pH); `context:unspecified` when all empty | experimental conditions; records in different contexts are never even compared |
| fingerprint | full normalized row incl. value, unit, locator, experiment label, extras | exact repeated-extraction detection |

`dedup_block = source_key | sample_key | metric_key | context_key`.
Pairwise comparison happens only inside a block, plus a second informational
block `sample | metric | context | value_token` used to *report* cross-source
corroborations (state `not_duplicate`, rule D-006).

## 3. Rule catalog

### Field mapping (F)
- **F-001** column-name aliases -> canonical fields (first hit wins; ties are
  impossible because aliases are unique in the lexicon). Failure mode: two
  input columns mapping to one field — the lexicographically first column
  wins, the other remains in `extra` and appears in F-002.
- **F-002** unmapped columns inventory (info): kept verbatim in record
  `extra`, listed in the review report so users can extend
  `field_aliases`.

### Names (N)
- **N-001/N-002** text normalization (unicode, case, separators).
- **N-003** exact full-string alias canonicalization (material/metric/phase).
  Fails safe: no alias -> token is its own identity.
- **N-004** phase word split from the material string (only standalone phase
  words from the lexicon, e.g. "rutile", "锐钛矿"). The phase becomes part of
  the sample identity; it is never discarded.
- **N-005** dopant split (`N-doped TiO2`, `TiO2:N`, `TiO2 doped with N`,
  `N-TiO2`). Dopant remains part of the sample identity: doped and undoped
  samples never merge.
- **N-006** lexicon miss (info anomaly).

### Values (V)
- **V-001** numeric formatting normalization (thousands separators, unicode
  minus). The numeric value itself is unchanged.
- **V-002** interval detection (`2.3-2.5`, `2.3~2.5`, `2.3 to 2.5`): kept as
  min/max; no midpoint is fabricated; intervals only equal intervals with
  identical bounds.
- **V-003** explicit missing tokens (`N/A`, `not reported`, `—`, …) -> null.
  Nulls stay null; missing values never equal other values.
- **V-004** reserved.
- **V-005** value-string split (`"3.2 eV"` -> value 3.2, unit eV) applied only
  when the unit field is empty and the pattern is unambiguous.
- **V-006** non-numeric values kept as text; text only equals identical
  normalized text; never merged numerically.

### Units (U)
- **U-001** unit alias/unicode normalization (°C, µm, Å, …).
- **U-002** conversion to the metric's canonical unit with recorded formula
  (`value = raw * factor + offset`), original raw value always retained.
  Conversions exist only for units whose dimension matches the metric
  expectation (eV/meV/kJ/mol for band gap; K/°C for temperature context;
  nm/µm/Å for lengths; Pa/kPa/MPa/bar for pressure).
- **U-003** unknown unit (review): no conversion; value compares raw only;
  can still be an exact duplicate when the whole row matches.
- **U-004** missing unit with present value (review): normalized value stays
  null.
- **U-005** unit/metric dimension mismatch (review): left unconverted.

### Consistency (C, A)
- **C-001** missing material or metric (review): record is kept, flagged,
  and excluded from duplicate blocking.
- **C-002** missing source (review): records share `source:unspecified`;
  within it only exact fingerprint duplicates merge (likely-duplicate is
  downgraded by lack of provenance evidence).
- **C-003** non-object input row skipped (review).
- **C-004** duplicated input record id gets a deterministic suffix so lineage
  stays unambiguous.
- **A-001** plausible-range check per metric (e.g. band gap 0–15 eV): out-of
  range values are kept unchanged and flagged for review, never "corrected".

### Duplicate adjudication (D)

Evidence per pair: same source / sample / metric / context / locator /
experiment label, full-fingerprint equality, and value relation
(`equal` — raw-identical or identical after conversion; `different`;
`unknown` — missing, incomparable kinds or unresolved units). The numeric
`score` (weights in `scripts/identity.py:WEIGHTS`) only orders the review
queue; decisions are rule-driven:

- **D-001 exact_duplicate** — same block, identical full fingerprint:
  repeated extraction of the same row. Merge.
- **D-002 likely_duplicate** — same block, equal values, only surface
  differences (alias wording, unit re-expression like 3000 meV vs 3.0 eV,
  one side missing locator). Merge, logged.
- **D-003 conflict** — same identity, different measured values. **Never
  merged, never averaged.** Both rows stay in separate clusters; queued.
- **D-004 review** — insufficient or ambiguous evidence (missing value,
  unresolved units with differing raw values, same identity+value but
  different locators: possible replicate vs repeat). Kept separate; queued.
- **D-005 not_duplicate / independent replicate** — distinct experiment
  labels within one study = independent repeated experiments. Both kept,
  each retains a distinct output `experiment_id`, even when values coincide.
- **D-006 not_duplicate / cross-source** — same measurement in different
  papers: corroboration, reported only, never merged.
- **D-007 not_duplicate** — different sample, metric or context (blocked
  apart; only reachable in the informational cross-source pass).
- **D-008 representative selection** — deterministic: most non-null identity
  fields, then converted value present, then smallest record id. The
  representative is always a real member row; no value is ever mixed across
  members.
- **D-009 conflict retention** — conflict members keep their own clusters and
  original values; logged so the non-merge is itself traceable.

Precedence when several rules match: D-006 > D-007 > D-005 > D-001 >
D-002/D-003/D-004 (the last three are mutually exclusive by value relation
and fingerprint).

## 4. Clustering and lineage

- Union-Find over D-001/D-002 pairs only; clusters are id-sorted
  (`cl-0001…`) and every cluster receives a stable `experiment_id`
  (`exp-0001…`); the original experiment label is preserved.
- `cleaned_records.json` keeps `members[]` with each member's original raw
  row, source, locator and role — nothing is deleted, only grouped.
- Cluster ids link conflicts (`conflict_cluster_ids`) so reviewers see both
  sides of every disagreement.

## 5. Boundaries and known limits

- Blocking is exact: two records that should merge but differ in a context
  field that one extractor omitted will land in `review` or separate clusters
  rather than being force-merged. This asymmetry (false separation over false
  merge) is intentional for scientific data.
- The unit table is deliberately small; extend `references/synonyms.json`
  rather than accepting unverified conversions.
- Alias lexicons cannot cover all chemistry; unknown names stay distinct
  (safe direction) and surface as `lexicon_miss` info entries for lexicon
  maintenance.
- Determinism: outputs contain no timestamps, absolute paths or randomness;
  rerunning on identical input is byte-identical (checked by
  `scripts/selfcheck.py`).
- Status semantics: `success` = pipeline completed (review items may still
  exist); `partial` = empty/unusable input or failed self-check invariant;
  `input_error` = unreadable/malformed input (exit code 2).

## 6. Maintaining the lexicon

1. Copy `references/synonyms.json`, edit, pass `--lexicon PATH`.
2. Add aliases as *strings normalized the same way the tool normalizes*
   (lowercase, collapsed spaces). Full-string matches only.
3. Never add aliases that collapse distinct species (no hydrate->anhydrous,
   no doped->undoped, no polymorph->polymorph).
4. Keep `metric_specs.plausible_range` conservative; A-001 flags but never
   rewrites.
