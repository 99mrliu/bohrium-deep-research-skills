# Failure modes: recognition, disposal, and wording

Universal disposal rule: **degrade to `partial` (or `blocked`) with specific
`open_items` / `material_gaps`; never fabricate content; never modify the
original inputs.**

Each entry below gives: the recognition signal, the exact disposal steps, and
copyable English phrasings for `open_items` / `material_gaps` (these strings
land in `result.json` under `version_and_boundary`, so write them for an
evaluator, not for yourself).

---

## 1. Material file missing

**Recognition.** A path declared in `case.material` does not exist when read
in Stage 1–2, or is empty (zero bytes).

**Disposal.**
1. Note the exact missing path and which `case.material` key declared it.
2. Continue with the remaining material only; do not guess what the missing
   file contained.
3. If the missing file was the fact base or the whole bibliography, expect
   status `partial` at best; if no draft can be grounded at all, deliver
   `blocked`.
4. Checkpoint the decision so the reason survives an interruption.

**Copyable phrasings.**
- open_items: `"Declared material file missing: '<path>' (case.material key '<key>'); content depending on it was omitted rather than reconstructed."`
- material_gaps: `"No access to '<path>'; any facts expected from it are absent from the draft."`
- limits (auto from assemble_result.py): `no_draft` / `claims_missing` — add prose in open_items, do not hand-edit `limits`.

---

## 2. Bibliography empty or unparseable

**Recognition.** The bibliography JSON parses to zero entries, fails JSON
parsing, or the readable version lists no works.

**Disposal.**
1. Do not cite anything from memory or from outside the case. Zero usable
   references means zero citations.
2. Re-frame the related-work part as a gap statement grounded in the fact
   base alone, clearly without literature support.
3. Expect `min_distinct_citations` to fail in `contract_check.py`; accept
   status `partial` — an honest partial outranks a fabricated citation list.

**Copyable phrasings.**
- material_gaps: `"Bibliography is empty/unparseable; no prior work could be cited. Related-work passage states the gap from the fact base only."`
- open_items: `"constraint min_distinct_citations=<n> cannot be satisfied without a bibliography; left unsatisfied deliberately."`

---

## 3. Reference has no abstract (title-only)

**Recognition.** A bibliography entry lacks an abstract (or the readable
version marks it `title-only`).

**Disposal.**
1. You may cite the work's *existence* and *topic* exactly as far as the
   title supports.
2. Do not attribute findings, numbers, methods or limitations to it.
3. If the case brief expected a comparison with that work, record the
   shortfall instead of improvising one.

**Copyable phrasings.**
- open_items: `"Reference [<n>] '<title>' is title-only; cited for existence/topic only, no findings attributed."`
- material_gaps: `"No abstract available for [<n>]; a direct comparison with the present work could not be grounded and was omitted."`

---

## 4. Unknown citation style

**Recognition.** `constraints.citation_style` is absent, or names a style you
cannot identify.

**Disposal.**
1. Fall back to the bibliography's own numbering, cited as `[n]` by first
   appearance — the safest common denominator.
2. State the fallback explicitly; do not invent a style specification or
   imitate a style you cannot verify.
3. Keep numbering consistent throughout the draft (mechanical consistency is
   checkable; style elegance is not).

**Copyable phrasings.**
- open_items: `"citation_style '<value>' not recognized; used Vancouver-style [n] numbering by first appearance as a declared fallback."`

---

## 5. output_contract descriptor unparseable

**Recognition.** `init_run.py` prints `WARNING: fields needing manual
review`, or `work/contract_map.json` carries `needs_manual_review` notes on a
field or subfield (this also covers prose fragments inside field lists, such
as `"pass/fail/not_verifiable counts"`).

**Disposal.**
1. Read the raw descriptor text in `case.json` and interpret it by hand;
   fill the field with your best-faith structure.
2. Record your interpretation so the evaluator can see the reasoning.
3. `contract_check.py` will mark that node `not_verifiable` rather than
   failing it — that is expected and acceptable. A `not_verifiable` never
   blocks delivery; a fabrication does.

**Copyable phrasings.**
- open_items: `"output_contract descriptor for '<field>' did not parse mechanically ('<raw text>'); filled by hand as <your interpretation>."`

---

## 6. Language switch mid-case

**Recognition.** `case.language` or `constraints.language_of_output`
disagrees with `task.md`, or the material is written in a different language
than the required output.

**Disposal.**
1. Priority order: `constraints.language_of_output` > `case.language` >
   `task.md`. Write the deliverable in exactly one language.
2. Quote source material verbatim where needed (quotes may stay in the
   source language), but never let the prose itself mix languages silently.
3. Note the discrepancy so the evaluator knows it was a decision, not an
   oversight.

**Copyable phrasings.**
- open_items: `"Language conflict: case.language='<a>' vs task.md '<b>'; wrote output in '<chosen>' per constraints.language_of_output."`
- material_gaps: `"Source material in '<lang>'; quotations kept verbatim, prose written in '<lang2>'."`

---

## What never changes

In every failure mode above:

- The draft contains only what the material supports.
- `result.json` status is `complete` only when nothing is missing; otherwise
  `partial` with a `limits` list, or `blocked` with a stated blocker.
- Original inputs under `/input` are untouched.
- The newest checkpoint plus the work directory allow anyone to reconstruct
  exactly how far the run got and why it stopped there.
