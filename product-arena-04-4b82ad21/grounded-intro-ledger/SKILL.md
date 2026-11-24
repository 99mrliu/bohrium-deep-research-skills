---
name: grounded-intro-ledger
description: Write or audit a manuscript introduction and related work with every claim about prior work bound to a verbatim quote from the provided sources. Use for grounding claims, evidence-ledger drafting, citation traceability, no-new-facts enforcement, and pre-submission grounding audits of introductions or related-work sections.
---

# Grounded Introduction Ledger

Write introductions whose every factual statement can be traced back, sentence
by sentence, to the provided material. The center of this skill is **upstream
fact truthfulness**: before prose is written, an evidence store fixes what the
sources actually say; while prose is drafted, every claim is bound to verbatim
quotes; before delivery, a mechanical audit proves the binding still holds.
A draft that cannot produce its quotes is not finished.

## When to use

- Drafting an introduction / related work from a fixed fact base and a fixed
  bibliography, where claims must stay inside the provided evidence.
- Revising an existing draft whose attributions, numbers, or citations are
  suspect.
- Pre-submission audit: prove every citation resolves to verbatim source text.

Do not use this skill to expand coverage beyond the provided bibliography, and
never use it to make an unsupported claim look supported: the ledger records
what the sources say, and a failed binding is fixed by changing the prose or
moving the item to open items — never by inventing a quote.

## Runtime contract

1. Input is `/input/case.json` and `/input/task.md` plus the material files the
   case declares. Read the actual files; directory labels and file names are
   not evidence. Do not read anything the case withholds.
2. Do all intermediate work under `/app/work` (evidence store, claim ledger,
   drafts, audit reports).
3. Final deliverables go to `/app/output`: the editable manuscript text and a
   `result.json` that contains `case_id` copied verbatim from the input and
   **every field of the case's own `output_contract`**, with the nesting and
   types the contract describes. The claims ledger produced here maps directly
   onto a `facts_and_sources`-style array; the audit maps onto a
   `verification`-style object.
4. `status` is honest: `complete` only when the draft passes the binding and
   grounding audits; `partial` when a deliverable exists but specific bindings
   or material are missing — enumerate exactly which in open items;
   `blocked` when material is unreadable — state what is missing.
5. Save an editable partial draft early (first third of the budget) and keep
   the ledger in sync as you revise. Budget awareness: extraction and audits
   are script work; spend model requests on reading sources and writing prose.
   Two audit passes (bind, fix, verify) are normally enough.

## Method

### Phase 1 — Build the evidence store (script)

```sh
python3 <skill-dir>/scripts/extract_sources.py --case /input/case.json --out-dir /app/work/evidence
```

This parses the declared bibliography and fact base into
`/app/work/evidence/evidence_store.json` with per-reference evidence levels
(`abstract`, `title-only`, `metadata-only`) and a list of material gaps. Read
`index.md` first. **Evidence levels are binding rules**: a title-only reference
supports identification and topic only — never attribute findings, numbers, or
limitations to it. If the store reports fewer references than the readable
bibliography lists, investigate the discrepancy before writing.

### Phase 2 — Draft with the ledger, not after it

Draft the introduction section by section. For every sentence that says
something about another work, immediately add a claim record to
`/app/work/claims.json`:

```json
{"id": "c7", "section": "related_work",
 "text": "<the exact sentence as it appears in the draft>",
 "type": "prior_work", "refs": ["<ref key>"],
 "quotes": {"<ref key>": "<verbatim quote copied from that reference's text>"},
 "source_span": "abstract sentence 2", "stance": "notes_limitation",
 "confidence": "high"}
```

Rules that make the ledger worth having:

- **Verbatim or nothing.** The quote must be a contiguous substring of the
  source's available text (whitespace may differ). If no such quote exists,
  the sentence has no source: rewrite it or move it to open items.
- **One quote cannot cover two works.** A sentence citing A and B needs a
  quote from A for A's clause and a quote from B for B's clause — or split the
  sentence.
- **Every number is traced.** Each number in a prior-work sentence must appear
  in that claim's bound quotes; each number in an own-work sentence must appear
  in the manuscript fact base. Numbers that appear nowhere are deleted.
- **Own-work claims name anchors.** Every contribution statement names an
  available anchor from the case (a figure or section), and asserts only what
  the fact base states — a pipeline figure supports a design claim, not an
  accuracy claim; planned evaluation stays planned.
- **Stance is honest.** Use `notes_limitation` when the source itself states
  the limit, `scopes` when you delimit applicability, `contrasts` for genuine
  conflicts. Preserve conditional superiority, negative results, and
  counterexamples; calling something "author judgment" does not exempt an
  unsupported fact.

A scaffold of claim skeletons for an existing draft is available:

```sh
python3 <skill-dir>/scripts/bind_claims.py --store /app/work/evidence/evidence_store.json \
  --scaffold /app/work/draft.md --out /app/work/claims_skeleton.json
```

### Phase 3 — Bind and verify (scripts)

```sh
python3 <skill-dir>/scripts/bind_claims.py --store /app/work/evidence/evidence_store.json \
  --claims /app/work/claims.json --out /app/work/bindings_report.json

python3 <skill-dir>/scripts/verify_grounding.py --store /app/work/evidence/evidence_store.json \
  --draft /app/output/introduction.md --claims /app/work/claims.json \
  --out /app/output/verification.json
```

`bind_claims.py` checks, per claim: ref keys exist (R1), no findings attributed
to title-only refs (R2), every quote verbatim (R3), every number traceable
(R4), own-work claims anchor-backed and ref-free (R5), stance/confidence
vocabulary (R6). Exit code 1 means hard failures — fix from the sources.

`verify_grounding.py` audits the finished draft in the other direction: every
cited sentence has a claim record (G1), no orphan records (G2), every number in
the draft traceable to quotes or the fact base (G3), citation numbers within
bibliography range (G4), contribution claims anchor-backed (G5), and material
gaps surfaced for open items (G6). Its output is shaped for the
`verification` field of `result.json`.

Fix failures by re-reading the source and changing the prose or the claim —
never by editing a quote to fit. Do not re-run audits that already passed;
spend the remaining budget on the prose.

### Phase 4 — Deliver per contract

Write `/app/output/result.json` with the case's own `output_contract` fields:
`case_id` verbatim; the artifact object with real path, format, sections and
word counts; `facts_and_sources` from the claims ledger (it already carries
id/section/text/type/refs/quote/source_span/stance/confidence);
`version_and_boundary` with changes, open items (including every material gap
the store surfaced and every claim that could not be bound), and status; the
`verification` object from Phase 3; and the honest top-level `status`. Reopen
both files and read them once before finishing.

## Exception handling

| Situation | Disposal |
|---|---|
| Bibliography file missing/unreadable | Store records the gap; if no bibliography at all, status `blocked` with the missing path; never reconstruct references from memory |
| Reference has no abstract | Evidence level `title-only`; cite for identification/topic only; R2 blocks finding attribution |
| Fact base missing a needed fact | Put the specific fact in open items with the claim it blocks; deliver the supported portion as `partial` |
| A claim cannot be bound to any verbatim quote | Rewrite the sentence to what the source supports, or drop it to open items; never fabricate the quote |
| Case constraints absent (no word limits, no anchors) | Proceed, record `not_verifiable` for those checks, note the assumption in version_and_boundary |

## Limitations

- The checks are mechanical: verbatim substring, number occurrence, vocabulary.
  They do not prove semantic entailment, novelty, or scientific validity; a
  claim can pass R3 and still misrepresent the source's emphasis. One careful
  human-style re-read of each bound quote against its sentence remains part of
  the method.
- Extraction parses the bibliography formats declared by the case (JSON with
  `references`/`entries`, plus a readable Markdown rendering). Unusual formats
  are reported as material gaps, not silently skipped.
- The bundled example under `examples/` is **synthetic**: invented material
  demonstrating the interface end to end. It is not an answer to any organizer
  case, and precomputed answers must never be submitted as real runs.

## Files

- `scripts/extract_sources.py` — case + materials → evidence store (evidence levels, material gaps)
- `scripts/bind_claims.py` — claims scaffold generator and verbatim-binding verifier (R1–R6)
- `scripts/verify_grounding.py` — draft-level grounding audit (G1–G6) emitting a contract-shaped verification object
- `references/grounding_protocol.md` — evidence levels, quote discipline, number tracing, stance taxonomy with examples
- `references/claim_schema.md` — the claim record schema field by field, with failure examples
- `examples/` — synthetic end-to-end run (see `examples/README.md`)
