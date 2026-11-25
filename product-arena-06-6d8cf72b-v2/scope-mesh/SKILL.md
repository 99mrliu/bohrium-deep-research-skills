---
name: scope-mesh
description: Audit scientific claim scope and extrapolation by linking bounded conclusions to anchored evidence, testing universal claims, and separating demonstrated, inferred, conflicting, and unreported findings.
---

# Scope Mesh

Use this skill to decide **where a scientific claim holds**, not merely whether a number or quotation appears. A claim is incomplete until each key conclusion has a scope record covering subject/population/material, intervention or method, comparator, dataset/sample, experimental conditions, metric/unit, direction/effect, and limitations. Preserve those restrictions in the final wording.

This is not a PDF-extraction substitute, a numerical-recomputation workflow, or a generic JSON pipeline. Use platform extraction only to obtain readable evidence; the scientific work is scope closure, exception searching, and calibrated generalization.

## Runtime contract

1. Inspect the real `/input/case.json`, `/input/task.md`, and every actual supplied paper/source file before drafting. Do not assume the synthetic example's files are runtime inputs.
2. Use `/app/work` for scratch and `/app/output` for deliverables. Create an honest early draft at `/app/output/result.json` within **64 model calls and 900 seconds**, then refine it. Never wait for a perfect mesh before saving a usable partial result.
3. `/app/output/result.json` must contain the real `case_id` and **every top-level property declared by the exact original `case.output_contract`**, even if its `required` list accidentally omits that property. Preserve exact names, nesting, JSON types, required items, array item counts, and `additionalProperties: false`. Validate against that case schema; do not replace it with the example contract, a looser schema, or a CLI case-ID override.
4. Keep `sources`, `uncertainty`, and `change_records` in `result.json` when the contract permits. If it does not, write them as clearly named sidecars in `/app/output` and record only contract-permitted pointers. Never add unlisted keys to a closed result object.
5. Use only platform-provided PDF tools such as `pdftotext`, `pdftoppm`, and platform OCR when needed. Do not use personal paths, network access, package installation, or non-platform PDF dependencies. Read tables visually with `pdftoppm`/OCR when extraction disrupts columns; report unreadable regions rather than guessing.
6. Scripts use Python standard library only and explicit CLI paths. They perform deterministic structural checks, not semantic validation. A clean report never establishes scientific truth, complete literature coverage, or causal validity.

### Status and evidence states

Set `status` honestly according to the contract:

- `success`: requested bounded answers are supported and required scope closure is complete; an excluded universal claim may still be reported as unsupported.
- `partial`: some requested conclusions remain under-scoped, sources are partly unreadable/missing, or material conflicts prevent closure.
- `failed`: the task cannot be meaningfully answered or mandatory inputs/contract requirements cannot be satisfied.

Never collapse these states: **missing file** (path absent), **unreadable source** (present but unusable), **not reported** (searched source does not provide the dimension), and **conflicting evidence** (anchored findings disagree). `NR` means not reported after a targeted search; `NA` means inapplicable, and both require a reason. Empty strings are not substitutes.

## Task-adaptive response

- For a direct QA task, lead with the direct bounded answer. Include a scope mesh only when it helps qualify the answer or is requested.
- For a scope/extrapolation audit, provide the mesh, universal-claim decisions, counterexamples, and section-aligned notes.
- For other tasks, retain the contract's requested shape. Do not force a large mesh, generic review, or section-aligned notes onto a simple answer.
- Put detailed section notes in sidecars when the result contract has no place for them.

## Workload discipline

- Define a **key conclusion** only by decision impact: a conclusion is key when changing its direction, scope, evidence state, or uncertainty would change the requested answer, status, recommendation, or adjudication. Routine background, definitions, duplicate restatements, and non-decisive supporting observations are not key merely because they appear in an abstract.
- Every key conclusion receives a scope record. In a **scope/extrapolation audit**, every scope or extrapolation note included in the deliverable must complete the full eight-dimensional closure procedure below, including all relevant methods, results, tables/figures, discussion, and exception-search steps. Do not emit a supposedly closed scope note with only the dimensions that are easy to find; omit non-decision-critical notes rather than leaving under-scoped audit entries.
- For ordinary direct QA, lead with the answer and open only the records and dimensions needed to preserve that answer's actual population/material, intervention, comparator, sample, conditions, metric, direction, and limitations. Reuse a record shared by conclusions. Do not manufacture eight-dimensional records for background facts or run a universal-style four-section and exception audit when scope is not decision-critical.
- Save the honest contract-valid early draft first, then prioritize unresolved decision-critical dimensions and contrary evidence. Stop expanding the mesh when further records cannot change the requested answer; this keeps the work within the 64-call/900-second ceiling without weakening required closure.

## Evidence anchors and verbatim quotes

Every demonstrated or inferred key conclusion needs at least one source anchor and a contiguous verbatim quote. Use stable anchors in this preference order:

1. PDF: `filename.pdf#page=N` plus table/figure/section label where available; quote from platform text/OCR and visually check the page.
2. Converted text: `source_id:section-or-line-range`; line numbers refer to the retained converted text in `/app/work`.
3. Supplied plain text: an explicit anchor such as `[S3]`, used by the deterministic checker.

Quotes must be exact contiguous substrings of the anchored source region, including meaningful signs, units, qualifiers, and negation. No ellipsis-only stitching, paraphrase presented as quotation, or quote moved from another section. A quotation proves presence, not interpretation; record the inference separately. Multiple disjoint passages require separate evidence objects. If a table cannot be quoted linearly, use a short exact row caption/value sequence and a visual anchor, and disclose extraction limitations.

See `references/scope_fields.md` and `references/adjudication.md` for the field dictionary and decision rules.

## Required scope-closure procedure

For each key conclusion, open a scope record and complete all eight dimensions. Then close scope only after all steps below:

1. **Locate the actual claim.** Distinguish the authors' claim from your response and from a reviewer's paraphrase. Record whether it is demonstrated, inferred, not reported, or conflicting.
2. **Methods closure.** Read the methods for subject/population/material, intervention/method, comparator, dataset/sample, conditions, and metric/unit. Follow referenced supplements when supplied. Mark absent dimensions `NR` with the search location, or `NA` with a scientific reason.
3. **Results closure.** Read primary and secondary results relevant to direction/effect. Preserve endpoint, unit, subgroup, time point, and uncertainty. Do not turn association into causation or non-significance into equivalence.
4. **Tables/figures closure.** Inspect every relevant table/figure, including footnotes and supplementary tables actually supplied. Check whether overall effects hide an opposite subgroup or condition. Do not infer values from an unreadable cell.
5. **Discussion closure.** Read limitations, caveats, authors' generalizations, and proposed mechanisms. A mechanism is an inference unless directly tested. Preserve restrictions even if the abstract omits them.
6. **Exception search.** Search supplied sources for exceptions and contrary strata using claim-specific synonyms and antonyms: subgroup names, materials, doses, conditions, datasets, endpoints, `no difference`, `worse`, `increased`, `decreased`, `failed`, `heterogeneity`, and corresponding Chinese terms when relevant. Inspect null effects and limitations, not only confirming passages. Record search terms and locations.
7. **Scope reconciliation.** Link every exception to a scope record. Narrow the claim, identify a conflict, or explain why it is out of scope with evidence. Silence is not evidence of no exceptions.
8. **Closure decision.** A demonstrated bounded claim closes only when required dimensions are filled or explicitly `NR`/`NA`, supporting quotes/anchors verify, and contrary evidence is reconciled. Otherwise keep it open and downgrade status.

## Universal-claim test

Treat `always`, bare word-boundary `all` (including `All samples improved`), `every`, `all datasets`, `state of the art`, `best`, `universally`, `no exceptions`, Chinese `所有`/`全部`, and equivalent wording in any language as triggers, not as acceptable shorthand. Word boundaries prevent substrings such as `overall`, `small`, and `alloy` from triggering `all`. Also catch implicit universals created by deleting population, material, condition, endpoint, or dataset limits.

For each triggered claim:

1. Write the smallest defensible bounded alternative before assessing support.
2. Require explicit checked evidence entries for **methods, results, tables, and discussion**. Abstract-only support cannot close a universal.
3. Search for counterexamples across all arms, subgroups, materials, datasets, conditions, endpoints, and supplied external comparisons. Record terms and locations.
4. Classify each counterexample as `bounded_restatement`, `conflicting_evidence`, or `explained_out_of_scope`, with an anchor and reason. A single demonstrated contrary in-scope case defeats `always`/`all`.
5. For `state of the art`/`best`, require a defined comparison set, date, metric, conditions, and fair comparator evidence. Without them label the ranking `not_reported` or `unsupported_generalization`; a strong single-paper result is insufficient.
6. Replace the universal with the bounded alternative or reject it. Do not average away a contrary subgroup. Report untested populations/materials as untested, not as future certain benefits.

`scripts/scope_mesh.py check-claims` flags missing section coverage, missing exception searches, possible undeclared universals, unresolved counterexamples, and unsupported generalization. These are audit flags requiring human adjudication.

## Deterministic checks and example

```sh
K=/skills/weekly-skill  # 若实际安装路径不同，设为本 SKILL.md 所在目录
python3 "$K/scripts/scope_mesh.py" validate-scope \
  --records /app/work/scope_records.json \
  --source-root /app/work/source \
  --output /app/work/scope_validation.json
python3 "$K/scripts/scope_mesh.py" check-claims \
  --claims /app/work/claims.json \
  --records /app/work/scope_records.json \
  --source-root /app/work/source \
  --output /app/work/claim_audit.json
python3 "$K/scripts/scope_mesh.py" check-contract \
  --result /app/output/result.json --contract /input/case.json \
  --output /app/work/contract_validation.json
python3 "$K/scripts/self_test.py"  # expected-failure cases; independent of the example
sh "$K/run_example.sh" /app/work/synthetic-output
```

`check-contract` treats the supplied `case.output_contract` and `case.case_id` as authoritative. It recursively audits every property, item, `additionalProperties`, and combinator branch before validating a result. Supported assertions are `type`, `const`, `enum`, `required`, `properties`, `additionalProperties`, `minProperties`, `maxProperties`, `items`, `minItems`, `maxItems`, `uniqueItems`, `minLength`, `maxLength`, `pattern`, `minimum`, `maximum`, `anyOf`, `oneOf`, and `allOf`; boolean schemas and the non-assertion annotations `$schema`, `$comment`, `title`, `description`, `default`, and `examples` are accepted. `anyOf` requires at least one matching branch, `oneOf` exactly one, and `allOf` every branch. Unsupported or malformed schema constructs produce a nonzero invalid report instead of `valid: true`; in particular, references, tuple-form `prefixItems`, `format`, and unimplemented numeric/string/object constraints are not silently ignored.

A nonuniversal claim's linked records normally have the same `claim_id`. A deliberate aggregate may instead document `scope_record_link_exceptions[record_id] = {"kind":"composition","reason":"..."}`. Declared universal audits intentionally compose bounded records owned by their underlying conclusions and therefore need no such exception. Link consistency, universal flags, and schema validity remain structural checks, not semantic adjudication.

The checked-in example is entirely **synthetic / 合成示例**. `run_example.sh` accepts an output directory (default: `examples/synthetic/output`) and regenerates `result.json`, `scope_mesh.json`, `scope_mesh.md`, `audit_report.md`, and `scope_validation.json`. All are synthetic and deterministic. Inspect generated files after running; validation does not replace scientific reading.
