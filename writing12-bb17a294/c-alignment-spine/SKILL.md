---
name: alignment-spine
description: Bilingual academic translation workflow (EN↔ZH) centered on a stable segment-ID spine (对得齐) — 1:1 source/target alignment, structure-parity checks, and a clean target derived (never retranslated) from the bilingual master.
---

# Alignment Spine — Academic Translation & Bilingual Writing (学术翻译与双语写作)

## Purpose (目的)

Produce case deliverables for academic translation so that **every source
paragraph, caption, footnote, equation, and reference entry maps 1:1 to its
translation** (对得齐). The center of gravity is *bilingual alignment and
structural parity*: a stable segment-ID spine, a verified structure
inventory, and a clean target-language file that is **derived from the
bilingual master, never retranslated**.

## When to use (触发条件)

- A case asks for EN↔ZH academic translation, a bilingual version, or both.
- The deliverable must preserve structure: sections, figures, tables,
  equations, footnotes, references.
- You need auditable alignment: which target sentence translates which
  source segment, and proof that nothing was dropped, merged, or reordered.

## Core idea: the spine (主干)

`segment_source.py` assigns every source segment a stable ID
`⟦S0001⟧, ⟦S0002⟧, ...` in source order. That ordered ID list is the
spine. The bilingual master contains exactly one paired block per ID; the
checker verifies order, presence, and marker parity; the deriver extracts
only the target blocks. Hard rules: **never merge, never reorder, never
drop or renumber IDs** (绝不合并 / 绝不重排 / 绝不丢弃). Full format spec:
`references/method.md`.

## Full case workflow (完整流程)

### Stage 0 — Intake (读取任务)

1. Read `/input/case.json` and `/input/task.md` (and
   `environment/resources.yaml` if present). Record: the real `case_id`,
   requested deliverables, language direction, and **every field of the
   real `output_contract`** — never assume its schema
   (see `references/output_contract.md`).
2. Create `/app/work` and `/app/output`. Immediately write a valid partial
   `/app/output/result.json` (real `case_id`, `status: "partial"`).
3. Read the actual material files. A PDF has **no pre-extracted answer
   layer**: extract it yourself (`pdftotext -layout in.pdf work/source.txt`
   is available). Save the extracted text to `/app/work`.

### Stage 1 — Segmentation (分段打标)

```bash
python3 scripts/segment_source.py work/source.md -o work/
```

Produces `source_segments.txt` (human-editable) and
`structure_inventory.json` (counts and ID lists per kind, per-section map,
figure/table numbers, equation count, reference count). **Spot-check**:
kinds plausible? figure/table numbers right? references count matches the
source? Fix misclassifications by editing segment **text/kind** in place —
never IDs or order — and log the edit in `change_log.md`.

### Stage 2 — Interleaved bilingual translation (逐段对译)

Translate the source yourself, segment by segment, writing `bilingual.md`
in the paired-block format (exact spec in `references/method.md`):

```
⟦S0004⟧ paragraph
> SRC
<source text of the segment>

> TGT
<你的译文>

> NOTE
<可选译注；不算译文>
```

- Work section by section; **save `bilingual.md` after each section**
  (budget safety).
- Keep every structural marker in place: `Figure 1`→`图 1`, `[12]` kept,
  `[^1]` kept, equation bodies byte-identical, `#` heading levels kept.
- Translated additions go in `> NOTE` blocks or clearly marked inside the
  same `> TGT` — never as fake segments.
- Numbers/facts: cross-check numerals, author names, and citation keys
  against the source as you go (one line in `change_log.md` if you fix
  an extraction error; do not build a separate fact ledger here).
- Terminology: keep a running consistent choice for key terms in your
  notes (one line per term; no separate termbase machinery).

### Stage 3 — Alignment & structure parity checks (对齐校验)

```bash
python3 scripts/check_alignment.py work/bilingual.md work/source_segments.txt \
    --json output/alignment_report.json
```

Per-segment verdicts: `ok | missing_tgt | missing_src | marker_mismatch |
order_violation`. Non-zero exit on any failure. Fix `bilingual.md` and
re-run until it passes. Verify the structure inventory is complete and in
place: every section heading has a TGT heading, every figure/table number
survives, equation bodies unchanged, every reference entry translated.

### Stage 4 — Derive the clean target (派生净译文)

```bash
python3 scripts/derive_target.py work/bilingual.md \
    --segments work/source_segments.txt \
    --inventory work/structure_inventory.json \
    -o output/translation_target.md --json output/coverage.json
```

The target file is **extracted from the bilingual master** — never
retranslated. Coverage must be 100% (sections, captions, equations,
references); the deriver exits non-zero and writes nothing if any segment
lacks a TGT. If the case wants only the bilingual master, still run this
stage: the coverage summary is your parity evidence.

### Stage 5 — Package & deliver (交付)

Copy to `/app/output`: the case-requested deliverable(s)
(`translation_target.md` and/or `bilingual.md`), plus
`source_segments.txt`, `structure_inventory.json`,
`alignment_report.json`, `change_log.md`, and the final `result.json`
filled per `references/output_contract.md` (real `case_id`, all actual
contract fields, honest status, sources, uncertainty, change records).
State the boundary of what was done (边界): files processed, pages
covered, anything left out and why.

## Invocation (调用方式)

All scripts are Python 3 stdlib-only, no network:

```bash
python3 scripts/segment_source.py SOURCE [-o OUTDIR]
python3 scripts/check_alignment.py BILINGUAL SEGMENTS [--json REPORT.json]
python3 scripts/derive_target.py BILINGUAL [--segments SEGMENTS] \
        [--inventory INVENTORY.json] [-o TARGET.md] [--json COV.json]
```

Exit codes: `0` pass; `1` alignment/coverage failure; `2` usage/IO error.
A fully worked synthetic example lives in `examples/synthetic/` (see its
README).

## Inputs / Outputs (输入输出)

- **Inputs**: case files under `/input/`; a source text/markdown file
  (extract it from PDF yourself with `pdftotext` when needed).
- **Intermediates** (`/app/work`): extracted source text,
  `source_segments.txt`, `structure_inventory.json`, `bilingual.md`.
- **Outputs** (`/app/output`): clean target (derived) and/or bilingual
  master per the case, plus the segment file, inventory, alignment report,
  change log, and `result.json`.

## Exception handling (异常处理)

- **PDF extraction garbled** (two-column interleave, broken formulas):
  note it in `change_log.md` and uncertainty; fix segment text by hand in
  `source_segments.txt` before translating; never silently "repair"
  content.
- **Checker fails**: read the per-segment verdicts, fix `bilingual.md`,
  re-run. Do not edit the report or the derived target by hand.
- **Deriver refuses (missing TGT)**: finish the missing translations; the
  target file must never be partially derived.
- **Segment boundary feels wrong** (e.g., a table split mid-row): fix the
  segmentation, regenerate IDs from scratch, and re-translate the affected
  span — do not hand-renumber IDs mid-stream.
- **Budget nearly exhausted**: ensure the latest `bilingual.md` is saved,
  run the checker + deriver on what exists, and ship a partial
  `result.json` stating exactly which segments are untranslated and why.
- **Ambiguous instructions or unreadable content**: record in uncertainty;
  mark the gap; never fabricate source content or translation.

## Runtime contract (运行时约定)

- **First** read `/input/case.json` and `/input/task.md` (and
  `environment/resources.yaml` if present); record the actual `case_id`,
  the requested deliverables, the language direction, and **every field of
  the real `output_contract`** — never assume its schema. Read the actual
  material files; a PDF has no pre-extracted answer layer — extract it
  yourself (`pdftotext` is available).
- Create `/app/work` and `/app/output`. Save a valid **early partial**
  `/app/output/result.json` before long work; update it **atomically**
  (write temp, then rename) after each stage. Budget: **64 model requests /
  900 s** — run the deterministic scripts early, and save `bilingual.md`
  after each section.
- Final `/app/output`: the case-requested deliverable(s) (clean target
  derived via script and/or bilingual master), `source_segments.txt`,
  `structure_inventory.json`, `alignment_report.json`, `change_log.md`,
  and `result.json` containing the real `case_id`, all actual
  `output_contract` fields, an honest status, sources, uncertainty, and
  change records. Editable Office/slide/diagram artifacts also need real
  PDF/PNG previews. A partial result states exactly what is missing and
  why. **Never fabricate.**
