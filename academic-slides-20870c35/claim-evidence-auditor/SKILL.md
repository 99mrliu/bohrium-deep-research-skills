---
name: claim-evidence-auditor
description: Build an academic presentation whose every on-slide claim is traceable to an exact source location and calibrated to its evidence strength. Produces a claim ledger, a page-level content map, a full-source coverage ledger and an automated audit report (numbers and citations on slides cross-checked against the source text) alongside the editable deck. Use when a case under /input asks for slides from a paper where factual fidelity, citation accuracy and verifiability are scored, delivering to /app/output.
---

# Claim-evidence auditor: nothing on a slide that cannot be pointed to

The failure this skill prevents is factual drift: numbers copied from memory, figures cited against the wrong caption, conclusions stated stronger than the evidence, and figure crops that silently change meaning. The method is a **claim ledger** — every substantive statement that will appear on any slide is first a ledger entry with an exact locator and a strength grade — plus **automated audit gates** that re-check the finished deck against the source before delivery.

Narrative and template work are done at the depth a correct deck needs; this skill's added value is the traceability chain. If a case is purely about re-narration for a new audience, apply the ledger to the rewritten claims all the same.

## Phase 0 — Contract intake (always first)

1. Recursively inspect `/input`: the actual `case.json`, `task.md`, `material.json`, `artifacts/slide-workorder.json` (locate real names), `environment/resources.yaml` if present, and every PDF/PPTX/data file. Read content, never infer from filenames.
2. Record in `/app/work/contract.json`: real `case_id`; the exact `output_contract` root fields; mode; slide count/range; audience; duration; language; template and starting-deck paths; full-source or coverage rules (e.g. "every figure must appear or be dispositioned"); required citations style; export formats. Case requirements outrank this skill's defaults.
3. `mkdir -p /app/work /app/output`; immediately write `/app/output/result.json` with the real `case_id`, all contract root fields holding type-correct partial values, honest `status: partial`, and an exceptions list. Update after every phase.
4. Tool census in `/app/work/tools.json`: `pdftotext`, `pdftoppm`, python3 + python-pptx, `soffice`, OCR availability. Budget-aware execution: batch shell calls, save early, render at most twice.

## Phase 1 — Index the source

Run `python3 scripts/pdf_index.py <paper.pdf> --out /app/work/source_index.json` (uses `pdftotext -layout`; see `references/evidence-schema.md`). It produces per-page text plus registries of figure captions, table captions, section headings and in-text citations. Then:

- Render the pages carrying key figures (`pdftoppm -png -r 150 -f N -l N`) and look at them; a caption text match does not prove what the figure shows.
- Note for every registry item its printed page and PDF page (they often differ).
- If the PDF is scanned and OCR is unavailable, say so in exceptions and fall back to visual transcription of the few needed items, flagged `unverified_text`.

## Phase 2 — Extract claim cards, not paragraphs

From the full text (not only the abstract), write `/app/work/claims.json`: one card per claim that may go on a slide, per `references/evidence-schema.md`:

- `statement`: the claim as it may appear, in the source's scope.
- `kind`: `measured | computed | cited_prior | inferred | framing`.
- `strength`: graded per `references/strength-rubric.md` — `established | preliminary | contextual | speculative`.
- `locator`: `{file, pdf_page, printed_page, section, exhibit}` (Figure/Table/panel or paragraph anchor).
- `anchor`: the exact short quote or the transcribed value with units, sample/conditions and the comparison it belongs to.
- `attribution`: `this_work | cited_work | presenter_synthesis`.

Rules: original results and cited prior work never share a card without separate attributions; a value without its conditions is an incomplete card; anything you cannot point to exactly does not get a card and does not get a slide.

## Phase 3 — Plan pages as claim bindings

Write `/app/work/page_plan.json`: per slide, its single message, the list of claim-card IDs it binds, the figure crop (source page + region description) or editable table it will show, and the strength wording allowed on that slide. Enforce the **full-source rule** from the contract: build `/app/work/coverage.json` dispositioning *every* registered figure, table and section — `slide N | backup | omitted: reason` — so a reviewer can verify nothing was silently dropped.

## Phase 4 — Build the deck from the ledger

- Slide text uses only card statements, at or below card strength; the wording rules of `references/strength-rubric.md` are binding (no rounding, no causality upgrade, no scope widening, no silent synthesis).
- Figures are faithful crops from rendered source pages including legend/axes/units/panel letters; beside each, cite the original exhibit number and page. Never redraw data curves from bitmaps; redraw only with the actual underlying data, else crop. Editable tables only when the transcription is verified cell by cell; otherwise a cited crop.
- Notes carry the locator and the interpretive caveat; slides cite sources on-slide or in notes per the work order.
- Build on the actual template (create mode) or a copy of the starting deck (edit mode: preserve unrequested slides and masters, log every change in `/app/work/changelog.md`). Save to the contract's path, typically `/app/output/presentation.pptx`.

## Phase 5 — Audit gates (the core deliverable)

Follow `references/audit-playbook.md`. Run `python3 scripts/audit_deck.py /app/output/presentation.pptx --index /app/work/source_index.json --claims /app/work/claims.json --out /app/output/audit_report.json`, which checks:

1. **Number gate** — every numeric token on slides/notes appears in the source index text (or is whitelisted in the claims ledger as a transcribed anchor); mismatches, rounding and unit drops are listed.
2. **Citation gate** — every Figure/Table/Section reference on slides exists in the source registry; dangling references are listed.
3. **Strength gate** — wording on each slide is compared with the bound cards' strengths; upgrades ("proves" over a preliminary result) are listed.
4. **Coverage gate** — the coverage ledger accounts for 100% of registry items.

Then the **visual gate**: for every cropped figure, reopen the rendered source page and the rendered slide side by side and confirm the crop shows what the slide claims (right panel, right curve, legend intact). Automated gates are aids; this eyeball pass is mandatory when rendering is available. Repair and re-audit until clean or until the residual is honestly recorded.

## Phase 6 — Deliver with the evidence chain

- Export PDF + PNG previews with the available renderer; record renderer and version, or mark unverified.
- `/app/output` holds: the deck, `content_map.json` (slide → claim IDs → locators, satisfying the contract's content-map field), `coverage.json`, `audit_report.json`, previews, `changelog.md`.
- Finalize `result.json`: real paths, `status`, per-requirement `compliance_checks` with observed values, every uncertainty (unverifiable numbers, OCR gaps, unresolved audit findings) spelled out. A deck with two flagged unverifiable numbers and an honest report outranks a clean-looking deck that hides them.

## Invocation, scope and failure handling

Typical invocation: "Use claim-evidence-auditor on the paper and work order under /input; deliver the deck, content map, coverage ledger, audit report and result.json to /app/output." A synthetic minimal example is in `examples/minimal/`.

In scope: fidelity, traceability, strength calibration, coverage accounting for slide generation or revision. Out of scope: judging whether the paper's science is right, re-deriving its statistics, or recovering data from bitmaps. On failure — missing source, encrypted/scanned PDF without OCR, contract demanding coverage the slide count forbids — deliver the best honest partial, name the exact blocker in exceptions, and never fabricate a locator, a number or an audit pass.
