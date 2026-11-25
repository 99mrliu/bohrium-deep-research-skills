---
name: claim-coverage-adjudicator
description: Final task-atom-to-claim-to-verbatim-evidence-to-output-field coverage and contradiction adjudication for scientific reading, formula, derivation, and numeric tasks; use before delivery to prevent unsupported answers, omitted formulas, placeholder success, silent contradictions, and output_contract drift, including MathML-rich and missing-formula metrics-only cases.
---

# Claim coverage adjudicator

Use this as the **final evidentiary gate**, not as an early generic contract
linter. The agent still reads the paper and authors the scientific answer. This
skill makes that answer prove its chain: exact task atom → substantive claim →
short quote in a normalized source excerpt → exact output field. It banks an
honest partial early so the final gate remains safe under interruption.

## Runtime and commands

Input is `/input/case.json` and the actual `task.md`; work is `/app/work` and
final delivery is `/app/output`. From the installed skill directory
(`/skills/weekly-skill`), run:

```bash
python3 /skills/weekly-skill/scripts/scaffold.py \
  --input /input --work /app/work --out /app/output
```

Run this **before analysis**. It writes:

- `/app/output/result.json`: exact input `case_id`, every field named by
  `output_contract.required_fields` (legacy `fields` is also accepted), contract
  types, an allowed early `partial` status, and named unfinished limits;
- `/app/work/source_excerpts.json`: excerpts from the actual task and readable
  UTF-8 text/JSON/XML, with exact `source_file`, `locator`, and normalized text;
- `/app/work/claims.template.json`: an intentionally empty authoring template,
  never an answer;
- `/app/work/change_log.json`: change records.

MathML excerpts retain their XML and `formula_source_id`. Normalization only
converts CRLF/CR to LF. Unsupported/binary inputs are named as skipped rather
than represented as parsed. Read `source_excerpts.json` and the original source
when structural context is needed.

## Agent authoring protocol

### 1. Atomize the complete final task

Copy `/app/work/claims.template.json` to `/app/work/claims.json`, then replace
its empty `task_atoms` with the agent's actual decomposition. Every atom has:

- `atom_id` and `exact_requirement` (the precise requested clause, including an
  expanded formula ID when the task says “for each formula”);
- `output_fields`, such as `answers.equations` or a contract field name;
- one or more authored `claims`.

Cover every clause: **all requested formulas, every requested symbol class,
derivation prerequisites/steps, explicit conditions, and each requested numeric
check**. Do not stop after the first formula. The adjudicator mechanically
checks every ID in `target_formulas` (or the formula catalog when no target list
exists); broader semantic atom completeness still requires the manual review in
`references/manual-adjudication-limits.md`.

Each central claim must contain:

- `claim_id`, substantive `answer`, and `claim_type`: `formula`, `variable`,
  `derivation`, `numeric`, or `statement`;
- `completion_status`: `completed`, `partial`, `not_started`,
  `insufficient_evidence`, or `refuted`;
- exact `output_fields` targeted;
- `origin`: `reported` or `inference`;
- `evidence`: records with `excerpt_id`, `source_file`, exact `locator`, exact
  short `quote` copied from that excerpt, `relation` (`supports`, `refutes`, or
  `context`), and `formula_source_id` whenever the excerpt has one;
- `uncertainty` and `missing_objects` naming every unresolved gap.

A formula claim also has top-level `formula_source_id`. A `context` quote does
not count as support. A reported answer needs at least one valid `supports`
quote. An inference additionally needs nonempty `inference_prerequisites` and a
transparent `inference_rationale`; each premise must itself be supported by the
attached evidence and authored prerequisite claims. Keep numeric zero and false
as values, but never use `TBD`, `unknown`, `not reported`, empty containers, or
similar placeholders as a completed answer.

When claims compete, give them the same `contradiction_group` within an atom.
Different completed central answers in that group block success. Declare known
conflicts in `contradictions` with `status: unresolved`; a resolution needs
`resolution` and verified `resolution_evidence`. Never delete the losing side to
hide a conflict: retain it as noncentral/refuted with an explained, supported
resolution. Any verified `refutes` evidence on a central claim blocks success.

See `references/claims-ledger.schema.md` for the full record grammar.

### 2. Author the result draft, not a generic answer

Write `/app/work/result.draft.json` with the exact case ID and every required
contract field. Map the authored claim answers into the required fields without
renaming or changing their declared JSON types. The finalizer does not invent
missing answers. It only copies declared draft fields, applies the adjudicated
status, aggregates claim evidence, records named gaps, and points to audit
artifacts. Empty draft `evidence`, `uncertainty`, and `artifacts` are acceptable
when their contract types are respectively array/object/object.

### 3. Adjudicate and repair

```bash
python3 /skills/weekly-skill/scripts/adjudicate.py \
  --case /input/case.json --work /app/work \
  --claims /app/work/claims.json --draft /app/work/result.draft.json
python3 /skills/weekly-skill/scripts/finalize.py \
  --case /input/case.json --work /app/work --out /app/output \
  --claims /app/work/claims.json --draft /app/work/result.draft.json
```

`adjudicate.py` returns 0 only for a clean success, 1 for an adjudicated
partial/insufficient result, and 2 for unreadable inputs. Run the finalizer even
after a defect report: it independently re-runs adjudication and writes the
honest result. Its return is 0 for a contract-valid success/partial/insufficient
result, 1 if the emitted contract remains invalid, and 2 if authoring inputs
cannot be read (the existing checkpoint is then left untouched).

Success requires all of the following, not merely nonempty JSON:

1. every atom has a completed, substantive, supported central claim;
2. every substantive non-refuted answer has verified direct support, or verified
   support plus transparent inference and prerequisites;
3. every quote occurs verbatim in its claimed excerpt and source/locator/ID
   match; all requested formula IDs have matching MathML support;
4. every content output field is targeted and substantive, while all required
   fields have the declared `field_types` and status is in `status_enum`;
5. no unresolved contradiction or refuted central claim remains.

Defects force `partial`; if there are no substantive answer objects, the result
is `insufficient_evidence`. The finalizer, not an optimistic draft, selects the
status. See `references/coverage-semantics.md` for edge cases.

## Case-specific evidence boundaries

- **C01/C03 MathML:** transcribe each requested source ID and inspect MathML
  hierarchy (fractions, subscripts, superscripts, roots, delimiters), then link
  symbol/derivation/numeric claims to the relevant prose excerpts. The formula
  catalog is not a derivation or a linearized answer. Do not silently substitute
  Unicode visual similarity or an `alttext` string for structural inspection.
- **C02-like missing objects:** only explicitly reported metrics and conditions
  can be answered as reported claims. If formula representation, derivation
  objects, per-item predictions, or recalculable raw data are absent, mark the
  affected atom `partial` or `insufficient_evidence` and name the exact missing
  objects. Do not reverse-engineer a formula, infer individual predictions from
  an aggregate metric, or fill unknowns with zero. Explicit metric answers plus
  blocked formula work yield `partial`; no substantive answer objects yield
  `insufficient_evidence`.

## Synthetic verification and limits

`examples/run_synthetic_example.sh` runs real scripts on wholly synthetic data:
a three-atom/two-formula case first fails for missing eq2 evidence, then passes
after that ledger record is repaired; a contradictory score pair fails; and a
metrics-only branch preserves named missing objects. These are interface tests,
not official cases, answers, scores, or benchmark results.

Python 3.9+ standard library only; no network, package installation, shared
modules, or external skill files are needed. The scripts verify provenance and
coverage mechanics, not semantic entailment, mathematical correctness, complete
human atomization, or numeric recalculation. Perform the manual review checklist
before trusting a clean gate. PDFs without supplied text/XML are listed as
skipped; this bundle does not claim OCR or PDF extraction.
