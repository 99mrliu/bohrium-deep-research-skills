---
name: ppt-evidence-fidelity-gate
description: >-
  Quote-gated, machine-audited evidence fidelity for turning a research paper
  PDF into an academic slide deck. Trigger when the task asks to convert a
  paper/PDF into slides (学术汇报 PPT / paper-to-slides / 论文转PPT) and any claim,
  number, unit, method name, or figure/table citation must stay faithful to the
  source: builds a per-page evidence index, requires a verbatim quote for every
  factual slide bullet, and blocks delivery until audit_deck.py passes.
---

# ppt-evidence-fidelity-gate

A verification gate, not a deck template. It prevents the four classic
paper→slide mutations: (1) numbers/units silently changed, (2) figure/table
numbers mis-cited, (3) schematics presented as experimental data, (4) other
papers' results presented as this paper's. The deck is **not done** until the
deterministic auditor passes or every finding is dispositioned in writing.

## Runtime contract (DeepSeek Harness)

- Skill installed at `/skills/weekly-skill`. Inputs: `/input/case.json`,
  `/input/task.md`; tools listed in `environment/resources.yaml`
  (pdf-text-tool = `pdftotext`, pdf-render-tool = `pdftoppm`, ocr-tool,
  office-renderer = LibreOffice `soffice`, font-discovery = `fc-list`,
  scientific-python). **Read actual files; never assume content from labels.**
  The paper PDF arrives with no pre-extracted answer layer.
- Work under `/app/work`; deliver under `/app/output`. Required outputs:
  `/app/output/result.json` (original `case_id` + every field named by the
  case's `output_contract`, honest `status`, `sources`, `uncertainty`, change
  record), the editable `.pptx`, rendered PDF/PNG previews of the deck,
  `evidence_map.json`, `audit_report.json`.
- Budgets: 64 model requests, 900 s wall clock, 16384 tokens per response.
  **Save a valid partial `result.json` early** (`make_result.py` right after
  reading case.json) and improve in place.
- Never fabricate paper content, figure numbers, software state, or scores.
  If something cannot be extracted, say so in `uncertainty` and downgrade the
  slide claim — do not invent it.

## The two-pass protocol

```
PASS 1  extract + index ........ extract_evidence.py   (machine)
PASS 2  quote-gated plan ....... slide_plan.json       (you, gated by check_plan.py)
BUILD   deck ................... python-pptx or stdlib writer
AUDIT   verify ................. audit_deck.py         (machine, blocking)
REPAIR  fix / downgrade / label  loop until audit passes
```

### PASS 1 — extract and index (always first, ~1 command)

```bash
python3 /skills/weekly-skill/scripts/extract_evidence.py \
    --pdf /input/<paper>.pdf --outdir /app/work
```

Produces in `/app/work`: `paper.txt` (formfeed-separated pages — your **only**
source of truth for quotes), `paper_pages.json`, `evidence_index.json`
(sections, figures, tables, in-text refs, fact_pool of number+unit sentences),
`pages/page-*.png` (150 dpi renders). Fields marked `heuristic: true` are
regex guesses: **open the PNG of any page you cite** and visually confirm the
caption matches the figure content (schematic vs data — see rules). If
`pdftotext` yields nothing (scanned/encrypted PDF), run the ocr-tool first,
then re-extract; note this in `uncertainty`.

If `case.json` provides an organizer template `.pptx` or a starting deck,
inspect it now (unzip, list layouts/masters) — you must respect its
masters/layouts, fonts, and footers during BUILD.

### PASS 2 — quote-gated slide plan

Write `/app/work/slide_plan.json` (format: `references/plan_format.md`;
rules: `references/quote_gate_rules.md`). Core gate:

- Every bullet stating a **number, unit, method name, dataset, or conclusion**
  MUST carry a `quote` field = **verbatim copy** from `paper.txt` (copy the
  characters; fix line wraps only; never retype, never "improve" numbers or
  significant figures) plus a `locator` (`page`, and `Figure N`/`Table M`/
  section when relevant).
- Anything not quote-backed MUST be labeled `status: "inferred"` or
  `"unsupported"` — or removed. Taxonomy:
  `established / supported / preliminary / inferred / unsupported`.
- Classify each cited figure as `schematic` vs `data` (caption verbs:
  "schematic/illustration/overview/pipeline" vs "measured/plotted/fitted/
  accuracy of"); never put a schematic on a results slide captioned as
  measurement.
- Others' results: a claim followed in the paper by a citation marker
  (`[12]`, `(Smith et al.)`) is prior art — label it as such or drop it.

Validate **before** building:

```bash
python3 /skills/weekly-skill/scripts/check_plan.py \
    --plan /app/work/slide_plan.json \
    --index /app/work/evidence_index.json \
    --paper /app/work/paper.txt
```

Exit 0 required. Fix findings in the plan and re-run; do not build from a
failing plan.

### BUILD — deck (lean part)

- Prefer `python-pptx` if importable (`python3 -c "import pptx"`); copy the
  organizer template, fill its layouts/placeholders, keep masters and footers.
  If python-pptx is unavailable, write a minimal stdlib pptx (zip + XML) or
  generate via the office-renderer; a plain correct deck beats a fancy broken
  one.
- Slide text must reuse the plan's bullet text **unchanged** (the auditor
  re-checks deck text against the paper — any drift is caught). Speaker notes
  must not introduce new numbers beyond plan notes.
- Respect case constraints: audience, time, slide-count limit, language.
- One claim per slide; keep the plan's figure pairing (page PNG crops may be
  embedded as images, but keep the caption text verbatim).

### AUDIT — blocking verification

```bash
python3 /skills/weekly-skill/scripts/audit_deck.py \
    --deck /app/output/deck.pptx \
    --index /app/work/evidence_index.json \
    --paper /app/work/paper.txt \
    --report /app/output/audit_report.json \
    --plan /app/work/slide_plan.json
```

It parses the `.pptx` zip/XML itself (no python-pptx dependency) and checks:
every number+unit token on slides and in notes ∈ paper fact pool (fuzzy
numeric match, units normalized); every cited `Figure N`/`Table M` exists and
caption-shaped slide lines match the indexed caption; every plan quote is
verbatim. Exit 0 = pass; exit 1 = unresolved findings with stable ids.

### REPAIR loop — dispositions

For each finding, either fix the deck/plan and re-audit, or accept the
deviation explicitly by writing `/app/work/dispositions.json`:

```json
[{"finding_id": "F003", "action": "downgraded",
  "reason": "removed the number; claim now qualitative and labeled inferred"}]
```

Allowed actions: `fixed`, `downgraded`, `labeled-unsupported`, `accepted`
(each needs a concrete `reason`). Re-run audit with
`--dispositions /app/work/dispositions.json`; exit 0 requires zero unresolved
findings. Never disposition a mutated number as `accepted` — fix it.

### Render + deliver

```bash
soffice --headless --convert-to pdf --outdir /app/output /app/output/deck.pptx   # preview
pdftoppm -png -r 100 /app/output/deck.pdf /app/output/preview
python3 /skills/weekly-skill/scripts/make_result.py \
    --case /input/case.json --out /app/output/result.json --status complete \
    --uncertainty "<what could not be verified>" --note "final"
```

Open one preview PNG and check for overflow/font substitution; if fonts are
missing, pick installed ones via `fc-list`.

## Delivery checklist

- [ ] `/app/output/deck.pptx` opens; respects organizer template if provided
- [ ] Rendered `deck.pdf` + `preview-*.png` present and eyeballed once
- [ ] `/app/output/evidence_map.json` — per slide: claim → locators + verbatim
      quotes + status (derive from slide_plan.json; this is the page-level gold
      standard reviewers ask for)
- [ ] `/app/output/audit_report.json` — verdict `pass` (dispositions allowed,
      reasons written)
- [ ] `/app/output/result.json` — `case_id`, all `output_contract` fields,
      honest `status`, `sources` (PDF name, tool versions), `uncertainty`,
      `change_log`
- [ ] Speaker notes present, non-duplicative, no unbacked numbers

## Minimal illustrative example (EXAMPLE — not real case output)

Paper sentence in `paper.txt` (p.1): `Our model reaches 92.3% accuracy on XYZ.`
Plan bullet:
```json
{"text": "92.3% accuracy on the XYZ dataset",
 "quote": "Our model reaches 92.3% accuracy on XYZ.",
 "locator": {"page": 1, "section": "Abstract"}, "status": "supported"}
```
Mutated variant `93.2%` makes `check_plan.py` exit 1
(`unbacked_number`/`quote_not_verbatim`); a slide containing `93.2%` makes
`audit_deck.py` exit 1 until fixed. Full walkthrough:
`examples/minimal_example.md`.

## Failure handling cheatsheet

| Situation | Action |
|---|---|
| pdftotext empty (scanned/encrypted) | ocr-tool → re-extract; note in `uncertainty` |
| Figure is an image; caption heuristic looks wrong | confirm on `pages/page-*.png`; trust eyes over regex |
| Number on slide not in fact pool | fix to paper value or delete; never round/invent |
| Template placeholders insufficient | add text boxes on the same layout; keep master/footer |
| Audit fails near deadline | downgrade claims, disposition with reasons, ship honest `partial` |
