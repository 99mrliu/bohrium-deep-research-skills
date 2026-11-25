---
name: conflict-mechanism-atlas
description: Build citation-exact common-field matrices, scoped proposition and conflict-mechanism atlases, and dynamic result.json files without converting lexical polarity, condition differences, or speculation into unsupported scientific conflict or causality.
---

# Claim-scope and conflict-mechanism atlas

Use this skill when documents appear to disagree and the task is to determine whether they corroborate, complement, genuinely conflict, differ only by scope, are incomparable, or provide insufficient evidence. This is deliberately **not** an old-style claim graph: claims are not mapped to `+1/-1`, condition differences are not presumed to explain disagreement, and no causal attribution is inferred from conditions alone.

## Non-negotiable interpretation rules

1. Separate lexical sentiment from scientific relation. A word such as “improved” is not a cross-paper verdict.
2. Model each proposition as `(topic, comparison, metric, scope)`. Record `evidence_kind` as exactly `observed_result`, `author_interpretation`, or `speculation`.
3. Assign direction only when the cited result warrants it. Keep strength wording in `strength.wording` and significance in `strength.statistical_significance`; never infer statistical significance.
4. Preserve `claim_scope` (`scoped` or `universal`), applicability conditions, and within-paper limitations. Do not turn a scoped result into a universal claim.
5. Use only these verdicts: `corroborates`, `complements`, `genuine_conflict`, `apparent_conflict_due_to_scope`, `incomparable`, `insufficient`.
6. Treat mechanism attribution as a hypothesis unless tested. Use `supported_by_direct_comparison`, `consistent_with_conditions`, or `unresolved`; record supporting **and** alternative explanations. Speculation cannot establish a mechanism.
7. Before any quantitative synthesis, test task, metric, units, material, pollutant, and budget. Preserve `unreported` and `noncomparable`. Never pool unlike datasets, materials, metrics, or dyes. The example deliberately performs no pooling.
8. Every common-matrix cell must cover every document and cite its exact `source_document_id` and `paragraph_id`.

## Runtime

Inputs are `/input/case.json`, `/input/task.md`, `/input/comparison-workorder.json`, and the source PDFs/text named by the workorder. Work only in `/app/work`; deliver in `/app/output`.

```bash
python3 scripts/run_pipeline.py --input-dir /input --work-dir /app/work --output-dir /app/output
```

Text sources use `[paragraph-id]` marker lines. Real PDFs are converted locally with an available `pdftotext`; no package installation or network access occurs. If conversion is unavailable, the run fails honestly rather than inventing text or citations. See [references/protocol.md](references/protocol.md) for page/paragraph identifiers and production extraction steps.

The runner always produces `comparison-matrix.md`, `conflict-atlas.md`, and `result.json`; it also produces `integrated-response.md`. `assemble_result.py` reads the actual `output_contract` whether list or dictionary, preserves it verbatim, and populates each requested result field. Status is exactly `success`, `partial`, or `failed`.

## Agent procedure

1. Read `case.json`, `task.md`, the workorder, and every source. Normalize/extract sources into `/app/work` with stable paragraph identifiers.
2. Complete the common-field matrix before synthesis. Include explicit `unreported` cells with citations; do not silently omit missing fields.
3. Extract propositions and evidence using [references/schemas.md](references/schemas.md). Assign only agent-specified `proposition_key` values to clusters. Never invent clusters through fuzzy entity or material-name matching.
4. Record explicit candidate relation pairs. Judging two papers to be in conflict requires comparable scientific estimands and sufficiently matched conditions, not similar wording.
5. For each apparent mechanism, identify the comparison that would test it. A direct head-to-head moderator test may support an explanation; a co-occurring condition difference only makes it consistent or unresolved. List alternatives.
6. Run validation, exact-key clustering, atlas generation, and attribution detection. Resolve errors before declaring success.
7. Assemble `result.json` dynamically from the original output contract, with exact `case_id`, sources, uncertainties, and change records.

## Commands

```bash
python3 scripts/validate_workorder.py --input-dir /input --work-dir /app/work
python3 scripts/cluster_propositions.py --workorder /input/comparison-workorder.json --output /app/work/clusters.json
python3 scripts/detect_attribution.py --workorder /input/comparison-workorder.json
python3 scripts/build_atlas.py --workorder /input/comparison-workorder.json --clusters /app/work/clusters.json --output-dir /app/output
python3 scripts/assemble_result.py --case /input/case.json --workorder /input/comparison-workorder.json --output-dir /app/output --validation /app/work/validation.json --clusters /app/work/clusters.json
```

## Synthetic verification

```bash
bash examples/run_example.sh
bash tests/run_all_tests.sh
```

The three synthetic papers include an acidic-scope complement, an opposite matched-condition result that remains a genuine unresolved conflict, and a direct pH-by-material head-to-head test supporting a bounded moderator explanation. No result is pooled across dyes or datasets. The negative test changes a speculation-based mechanism to `supported_by_direct_comparison`; attribution detection must fail.

See [references/protocol.md](references/protocol.md), [references/schemas.md](references/schemas.md), and [references/output-contract.md](references/output-contract.md).
