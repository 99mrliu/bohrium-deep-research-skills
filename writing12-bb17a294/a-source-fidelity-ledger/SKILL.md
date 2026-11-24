---
name: source-fidelity-ledger
description: Academic translation and bilingual writing (EN↔ZH) with upstream source fidelity (上游数据真实性) as the center of gravity — provenance-anchored extraction, a machine-checkable fact ledger of every number/unit/citation in the source, and a deterministic audit proving the translation preserves every ledger fact.
---

# Source Fidelity Ledger — 学术翻译与双语写作（事实锚定）

## Purpose

Complete full academic translation cases on supplied research material while
guaranteeing **upstream source fidelity**: every number, unit, percent,
range, year, citation, figure and table reference in the source is extracted
into a machine-checkable **fact ledger (事实台账)** with page/line
provenance, and the finished translation is **deterministically audited**
against that ledger. Nothing is rounded, converted, dropped, or added
without being detected and recorded.

Deliverables per case: (1) the target deliverable (clean target-language
version and/or bilingual aligned version, as the case requests), (2) a fact
& source mapping (数字/术语/引用/图表 均可溯源), (3) version & boundary
records (change log, human-confirmation items, gaps).

Scope boundaries: terminology management, sentence alignment and boundary
handling are supporting concerns only — keep a lightweight term list and
align segments as needed, but do NOT build separate termbase/alignment
machinery; the ledger and audit are the machinery of this skill.

## When to trigger

- A case asks for academic translation (学术翻译) or bilingual writing
  (双语写作) EN↔ZH on supplied research material (PDF/text/markdown).
- Any task where numeric/citation fidelity to a source document must be
  provable, not merely claimed.

## Workflow

### 0. Intake & contract (read before anything else)

1. Read `/input/case.json` and `/input/task.md` (and
   `environment/resources.yaml` if present). Record the real `case_id`,
   the requested deliverables, the language direction, and EVERY field of
   the case's actual `output_contract` — never assume its schema.
2. List the actual material files and read them. A PDF has no
   pre-extracted answer layer: extract it yourself (step 1).
3. Create `/app/work` and `/app/output`. Immediately save a valid EARLY
   partial `/app/output/result.json` (real `case_id`, all required fields
   with honest partial/empty values, `status: "partial"`). Update it
   atomically (temp file + move) after every stage.
4. Budget discipline: 64 model requests / 900 s. Run the deterministic
   scripts EARLY (they are cheap and catch problems while there is still
   budget), translate section by section, and save after each section.

### 1. Provenance-anchored extraction (溯源锚定抽取)

```bash
python3 scripts/extract_source.py /input/<material>.pdf -o /app/work
# or .txt/.md input — same command
```

Produces `/app/work/source.txt`, `pages.json` (page-anchored line map;
single pseudo-page for text input), and `extraction_manifest.json`
(method, file size, page count, per-page char-count coverage checksum,
sha256). On missing pdftotext or an empty text layer the script exits
non-zero: mark extraction degraded in `result.json`, state it in the
uncertainty list, and never fabricate source content.

### 2. Fact ledger (事实台账)

```bash
python3 scripts/build_fact_ledger.py /app/work    # writes /app/work/facts.jsonl
```

One JSON per fact: stable id (F0001…), type
(`number|percent|range|year|sample_size|unit_value|citation_marker|figure_ref|table_ref`),
raw value, normalized value, unit, page, line, context snippet. Handles
decimal/thousand separators, scientific notation, en-dash/hyphen/to
ranges, 19xx/20xx years, [12], [3–5], (Smith, 2020), Smith et al. (2021),
and superscript-style ^12. Read the ledger before translating; if you
spot a fact the script missed, append it manually (next free id,
`"note": "manual addition"`) and log it in `change_log.md`.

### 3. Segment translation (agent 分段翻译)

Translate section by section, against the ledger — never from memory.
Follow `references/method.md`: never round, never convert units unless
asked, percents stay percents, ranges keep both endpoints, citations
travel with their claims, cross-locale rewrites (万/亿 ↔ million/billion)
are allowed but are `normalized` events that must be listed. Mark anything
unverifiable as `[待确认]`. Save the translation file after each section
and update `result.json` atomically.

### 4. Deterministic fact audit (确定性事实审计)

```bash
python3 scripts/audit_translation.py /app/work/facts.jsonl \
    /app/output/<translation>.md -o /app/output/audit_report.json
```

Per-fact verdict: `preserved` | `normalized` (acceptable cross-locale
rewrite, always listed) | `missing` | `altered`; plus `added` detection
(numbers in the translation with no source counterpart). Exit code is
non-zero iff any fact is `missing` or `altered`. If the audit fails: fix
the translation (not the ledger, unless the ledger itself was wrong — log
that), re-run, iterate until exit 0 or budget forces an honest `partial`.

### 5. Deliver (交付)

Final `/app/output`: the case-requested deliverable(s), the fact & source
mapping (generated FROM `facts.jsonl` + `audit_report.json`: fact id,
type, raw value, source page/line, translation rendering and location,
verdict), `facts.jsonl`, `audit_report.json`, `extraction_manifest.json`,
`change_log.md` (changes, human-confirmation items, gaps), and
`result.json` filled per `references/output_contract.md` with honest
`status` (`success|partial|failed`), sources with extraction method,
uncertainty list, and change records. If the case requests an editable
Office/slide/diagram artifact, also render a real PDF/PNG preview. A
partial result must state exactly what is missing and why. Never fabricate
missing software state or scientific data.

## Invocation

All scripts are Python 3, standard library only (no pip, no network);
`pdftotext` from Poppler is used via subprocess for PDFs with graceful
fallback. Typical run:

```bash
python3 scripts/extract_source.py <input.pdf|txt|md> -o /app/work
python3 scripts/build_fact_ledger.py /app/work
python3 scripts/audit_translation.py /app/work/facts.jsonl <translation> \
    -o /app/output/audit_report.json
```

A fully worked, fully synthetic example (with real script outputs and a
negative-check recipe) is in `examples/synthetic/` — run it first if you
are unsure of the pipeline.

## Inputs / Outputs

- Inputs: `/input/case.json`, `/input/task.md`, optional
  `environment/resources.yaml`, and the case's material files
  (PDF/text/markdown).
- Work dir `/app/work`: `source.txt`, `pages.json`,
  `extraction_manifest.json`, `facts.jsonl`.
- Output dir `/app/output`: case deliverable(s), fact & source mapping,
  `facts.jsonl`, `audit_report.json`, `extraction_manifest.json`,
  `change_log.md`, `result.json` (+ PDF/PNG preview when an editable
  artifact is requested).

## Exception handling

- **No pdftotext / empty PDF text layer**: script exits 3/5 → extraction
  degraded; record honestly in `result.json` (status cannot be `success`
  unless every ledger fact is verifiable by another stated means); do not
  fabricate source text.
- **Audit exit non-zero**: enumerate the failing facts, fix the
  translation, re-audit; unresolved items become human-confirmation items
  in `change_log.md` and `result.json`.
- **`added` numbers**: justify each in `change_log.md` or remove it.
- **Unverifiable content**: mark `[待确认]` inline and list it under
  uncertainty; never silently guess.
- **Budget exhaustion**: stop after the current section, keep the last
  atomic `result.json` with `status: "partial"` stating exactly what is
  missing and why.
