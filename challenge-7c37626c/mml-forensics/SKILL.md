---
name: mml-forensics
description: Forensic authenticity verification of upstream source materials (publisher XML, MathML formula subsets, PDF text layers) before any formula analysis; use whenever a task hands you publisher XML / MathML / PDF formula materials and the result must be traceable to untampered, complete, correctly-identified source evidence.
---

# mml-forensics: upstream source-authenticity verification (上游数据真实性取证)

Core stance: **input materials are evidence, not truth.** Before transcribing,
explaining, or recomputing any formula, this skill establishes that the
provided artifacts are complete, well-formed, correctly identified, and
consistent with each other — or reports exactly which part fails and degrades
the result honestly. 核心立场：输入材料是证据而非真理；先取证，再分析。

This is deliberately a different center of gravity from transcription or
numerical checking: the deliverable is a **source-authenticity report plus a
verified formula inventory** that any downstream analysis can rely on. Every
later claim must cite evidence located by this report, never a remembered or
assumed source.

## Runtime contract

- Input: `/input/case.json` plus `task.md`; materials under paths given in
  `case.json.artifacts` (e.g. `artifacts/publisher-source.xml`,
  `artifacts/source-formulas.xml`, possibly a PDF). Read the actual files;
  never assume content from names or labels.
- Workspace: create `/app/work` immediately. Output: `/app/output`, with
  `result.json` written **early as an honest partial** (case_id plus every
  `output_contract` field present) and improved incrementally.
- `result.json` must contain the original `case_id` and **all fields named in
  the case's `output_contract`**, using the contract's own names, types and
  status enumeration. A `partial` / `insufficient_evidence` status must name
  what is missing and why; never fill unknowns with zeros or guesses.
- Do not submit prepared answers: every number, transcription and location in
  the output must come from the actual run on the actual input.

## Workflow

1. **Bootstrap.** Run `python3 scripts/case_bootstrap.py --input /input --work /app/work --out /app/output`
   (resolve the script relative to this SKILL.md if the skill is installed
   elsewhere). This snapshots the case, creates the work/output tree, and
   writes the early partial `result.json`. If `case.json` or `output_contract`
   is absent, record that fact in the result instead of guessing a schema.
2. **Forensic scan.** Run `python3 scripts/forensic_scan.py --input /input --work /app/work`.
   For every input file: SHA-256 and byte size. For every XML: well-formedness
   with line/column error location; if malformed, salvage `<math>` fragments
   with byte offsets and mark them `salvaged_fragment` (a salvaged fragment is
   weaker evidence than a parsed node — say so). Structure statistics: counts
   of MathML elements (`mfrac`, `msub`, `msup`, `msubsup`, `msqrt`, `mtable`,
   `mfenced`, `mrow`), the math-node ids, and which ids carry `alttext`.
   Verify that `artifacts/source-formulas.xml` is really a subset of
   `artifacts/publisher-source.xml` (match by node id and structural
   signature), not a divergent or fabricated catalog.
3. **Structural signature cross-check.** Run
   `python3 scripts/crosscheck_layers.py --case /input/case.json --work /app/work`.
   For each formula id: compare the publisher `alttext` TeX against the MathML
   structure via feature multisets (fraction/script/radical/fence counts and
   symbol sets). Disagreements are reported, never silently resolved. If a PDF
   exists, run `pdftotext -layout` and check that the numeric constants stated
   in the XML text layer actually appear in the PDF text layer (found/missing
   per constant). A formula whose three layers (MathML structure, alttext,
   PDF text) agree is **verified at source level**; anything else is
   `partial` evidence and must be flagged.
4. **Write the authenticity report.** Merge the scan and cross-check into
   `/app/work/authenticity_report.json`, then copy the final verdict into
   `/app/output/result.json`: per-artifact integrity (hashes, well-formedness,
   salvage), per-formula verification status and provenance (file, node id,
   byte offset), and an explicit `uncertainty` section listing any corruption,
   divergence or missing layer.
5. **Hand off.** The verified formula inventory in the result (ids, signatures,
   alttext, evidence locations) is the safe input for transcription, symbol
   explanation, derivation or numeric verification — by the agent's own
   reading or by other skills. If forensics failed for an artifact, downstream
   steps on that artifact must carry the same degraded status.

## Exception handling

- **Missing artifact path**: record `missing` with the path; do not fabricate
  a fallback file.
- **Corrupt XML**: salvage what parses, mark byte offsets, degrade status.
- **`pdftotext` unavailable or PDF unreadable**: mark the PDF layer `skipped`
  with the reason; the remaining two layers still produce a report.
- **No formulas at all** (missing-formula branch): the report says so
  explicitly and the result status is `insufficient_evidence` for any
  formula-level task — never reverse-engineer formulas from metrics.
- **Conflicting layers**: report the conflict verbatim (both token sets) and
  mark the formula `conflict`; a conflict is a finding, not an error to hide.

## Minimal example (SYNTHETIC — not a platform case, not evidence)

`examples/run_synthetic_example.sh` runs this skill's scripts end-to-end
against a fabricated JATS-style fixture (Einstein relation and Poole–Frenkel
mobility, invented constants). It produces `forensic_report.json`,
`crosscheck.json` and a `result.json` whose status is `success` only because
the synthetic layers agree. The fixture, its numbers and its outputs are
synthetic demonstrations of the interface, not platform results.

## Requirements and limitations

Python 3.9+ standard library only; `pdftotext` optional (degrades gracefully).
The signature cross-check detects structural divergence, not semantic
equivalence; glyph-level visual confirmation still belongs to the reading
agent. Hashes prove integrity against accidental corruption, not malicious
forgery. Maintain by testing against real publisher XML and recording new
corruption patterns in `references/corruption_patterns.md`.
