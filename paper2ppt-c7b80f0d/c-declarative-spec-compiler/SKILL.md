---
name: ppt-spec-compiler
description: Compile an academic paper into an editable, evidence-traceable slide deck by hand-authoring ONE declarative deck.spec.json (one claim per slide, bullets, evidence locators, figure paths, speaker notes) and letting a deterministic stdlib compiler do ALL mechanical work (validation, layout, bullet caps, overflow-to-backup, text-fit, evidence footers, images, notes, template inheritance, PDF/PNG preview, result.json). Trigger when a task asks to turn a paper/PDF into an academic PPT/slide deck, adapt a starting deck, or fill an organizer template under slide-count/bullet constraints.
---

# ppt-spec-compiler

## Purpose

The mechanical phase of paper→PPT (OOXML fiddling, placeholder geometry, text
overflow, bullet caps, evidence footers, notes wiring, template inheritance) is
where agents burn budget and introduce layout errors. This skill removes that
phase: **you hand-write exactly one artifact — `deck.spec.json` — and the
compiler does all mechanical work deterministically**, recording every decision
in `compile_report.json` so reviewers can audit the deck.

What you still do (the intellectual work): read the paper, distill the
mainline, write one claim per slide with verbatim numbers and honest evidence
locators. What the compiler does: schema validation, slide-limit overflow to a
backup section, bullet demotion to notes, title wrap/elide, text-fit shrink with
a readability floor, aspect-preserving image placement, evidence footer
stamping, notes slides, template placeholder filling, and the audit report.

## Inputs (read the real files; never assume content from labels)

- `/input/case.json` — case id, `output_contract` fields, constraints
  (audience, time, slide-count limit, language). Copy `case_id` verbatim.
- `/input/task.md` — the task statement.
- Paper PDF (path given in the case materials).
- Optional organizer **template** `.pptx` (masters/layouts must be respected)
  and optional **starting deck** `.pptx` to adapt.
- `environment/resources.yaml` — available tools (pdftotext, pdftoppm, ocr-tool,
  latex-compiler, office-renderer=soffice, browser-automation,
  font-discovery=fc-list, scientific-python).
- Budgets: 64 model requests, 900 s, 16384 tokens/response. Save a partial
  `result.json` early (step 0 below).

Work under `/app/work`; final artifacts under `/app/output`.

## Pipeline

All scripts are stdlib-only and flag-overridable; run them from any directory.
`SKILL_DIR` below = the installed skill root (e.g. `/skills/weekly-skill`).

### 0. Case intake + early partial result (do this first)

```bash
mkdir -p /app/work /app/output
cat /input/case.json            # case_id, output_contract, slide limits, language
python3 "$SKILL_DIR/scripts/make_result.py" \
  --case /input/case.json --out /app/output/result.json \
  --status partial --note "intake: case read, pipeline started"
```

### 1. Fast paper extraction (minutes, not deep reading)

```bash
pdftotext -layout PAPER.pdf /app/work/paper.txt          # text layer
pdftoppm -png -r 80 -f 1 -l 6 PAPER.pdf /app/work/pg     # eyeball first pages
```

- Skim abstract/intro/conclusion and the captions of every figure/table in
  `/app/work/paper.txt`. Distill: problem → gap → method → evidence groups →
  limitations → conclusion. See `references/spec_authoring.md` for the
  one-claim-per-slide discipline.
- If the PDF is image-only (no text layer), use the `ocr-tool` per
  `environment/resources.yaml`; disclose OCR use in `result.json` uncertainty.
- For each figure you want to show, crop it from its page render:

```bash
# first find the page, then render ONLY the figure region at high DPI
pdftoppm -png -r 200 -f 5 -l 5 -x 100 -y 320 -W 1000 -H 700 PAPER.pdf /app/work/fig2
# (-x -y -W -H are pixel offsets/size within the -r 200 render)
```

Rename crops to stable paths, e.g. `/app/work/fig2.png`. Never relabel a
figure's number; if a crop is schematic vs. data, say so in the caption/notes.

### 2. Author `/app/work/deck.spec.json` (the ONLY hand-written artifact)

Schema: `$SKILL_DIR/spec_schema.json` (mirrored by the validator). Quick shape:

```json
{
  "meta": {"case_id": "<from case.json>", "title": "...", "audience": "...",
           "language": "en", "slide_limit": 12, "max_bullets": 6,
           "footer_prefix": "Source: "},
  "slides": [
    {"id": "s01", "kind": "title", "title": "...", "claim": "...",
     "notes": "opening: who/what/why in 30 seconds"},
    {"id": "s02", "kind": "content", "claim": "<one sentence claim>",
     "bullets": ["short speakable phrase", "number + unit verbatim"],
     "evidence": [{"ref": "Fig. 2", "page": 5, "quote": "optional verbatim"}],
     "notes": "transition + emphasis + Q&A backup; do NOT repeat bullets"},
    {"id": "s05", "kind": "figure", "claim": "...",
     "image": {"path": "fig2.png", "caption": "Fig. 2 (verbatim caption fragment)"},
     "evidence": [{"ref": "Fig. 2", "page": 5}], "notes": "..."}
  ]
}
```

Rules the validator enforces (fail fast, itemized errors, exit 1):
- `kind` ∈ {title, section, content, figure, table, two-column, conclusion, backup}.
- **Exactly one `claim` string** on content/figure/table/two-column/conclusion.
- **Evidence locator required** on content/figure/table slides (`ref` + `page`).
- **`notes` required on every slide** — and they must add talk value, not repeat.
- Unknown fields, wrong types, >15 bullets, >40 slides → hard errors.
- Warnings only (compiler handles them): bullets over `meta.max_bullets`,
  slide count over `meta.slide_limit`, missing image files.

Authoring guidance (mainline, claim-as-banner, audience adaptation, a filled
mini-spec): `references/spec_authoring.md`. Keep numbers, units, method names
and figure numbers **verbatim from the paper text** — never invent or rescale.

### 3. Validate (before any building)

```bash
python3 "$SKILL_DIR/scripts/validate_spec.py" --spec /app/work/deck.spec.json
```

Fix every ERROR and re-run until exit 0. Warnings are fine — they are the
compiler's job.

### 4. Compile (backend chosen automatically)

```bash
# organizer template provided:
python3 "$SKILL_DIR/scripts/compile_deck.py" --spec /app/work/deck.spec.json \
  --template /input/TEMPLATE.pptx --out /app/output/deck.pptx \
  --report /app/output/compile_report.json
# organizer STARTING DECK provided (adapt-in-place mode):
python3 "$SKILL_DIR/scripts/compile_deck.py" --spec /app/work/deck.spec.json \
  --start-deck /input/START.pptx --out /app/output/deck.pptx \
  --report /app/output/compile_report.json
# neither provided: same command without --template/--start-deck -> builtin backend
```

Backend selection rules (recorded in the report):
1. **template backend** iff `python-pptx` imports AND `--template`/`--start-deck`
   is given. It introspects the file's layouts, picks per slide kind
   (title→title layout, section→section header, else title+content), fills real
   placeholders, and never overrides theme fonts/colors. `--start-deck`
   additionally rewrites existing slides in order, appends missing ones, and
   removes leftovers — every action logged.
2. **builtin backend** otherwise: a bundled pure-stdlib OOXML writer (plain
   16:9 theme, real notes slides, PNG embedding). The deviation from the
   organizer template is disclosed in `compile_report.json` and must be copied
   into `result.json` uncertainty.

### 5. Render + visually inspect (mandatory)

```bash
python3 "$SKILL_DIR/scripts/render_preview.py" --deck /app/output/deck.pptx \
  --outdir /app/output/preview --manifest /app/output/render_manifest.json
```

Then **open the per-slide PNGs** (`/app/output/preview/slide-*.png`) and check
each slide: no text overflow, no shrunk-below-floor fonts, footer present with
the right figure/table numbers, images not distorted, notes exist. If a slide
is wrong, fix the SPEC (not the pptx) and re-run steps 3–5. If soffice is
unavailable the manifest says `renderer_unavailable` (exit 0) — disclose it.

### 6. Finalize result.json

```bash
python3 "$SKILL_DIR/scripts/make_result.py" --case /input/case.json \
  --out /app/output/result.json --status complete \
  --sources '["PAPER.pdf","/app/work/deck.spec.json","/app/output/compile_report.json"]' \
  --uncertainty "<backend deviations, renderer status, OCR use, any demotions>" \
  --note "final: deck compiled, rendered, visually inspected"
```

Ensure every `output_contract` field points at a real artifact (deck path,
evidence map = the spec + compile_report, render record = render_manifest).

## Constraint policy (enforced by the compiler at build time)

| Constraint | Policy | Recorded in report as |
|---|---|---|
| slide count > `slide_limit` | overflow slides moved after a labelled "Backup / Appendix" divider | `slide-limit` warning + `backup_overflow` count |
| bullets > `max_bullets` | surplus demoted to speaker notes with `[DEMOTED:bullet-cap]` | decision per slide |
| long title | wrap ≤ 2 lines, then elide with "..."; full title preserved in notes | `title-policy` decision |
| estimated text overflow | body font walks the ladder 20→18→16→14→12 pt; at the 12 pt floor, trailing bullets demoted to notes with `[DEMOTED:text-fit]`; never below the floor | `text-fit` decision + warning |
| tables > 8 rows | rows beyond 8 compacted into notes `[DEMOTED:table-rows]` | `table-compaction` decision |
| images | aspect ratio preserved inside the content bounding box; PNG sized from its header; missing/unreadable → labelled placeholder + warning | `image` / `image-missing` decision |
| evidence | every slide with locators gets a stamped footer `"Source: Fig. 2 (p. 5); ..."` | footer action per slide |
| notes | real notes-slide text on every slide, demotions appended | — |

Estimator constants (CJK = 2 width units, latin = 1, line height 1.3 em) are
documented in `references/text_fit.md`.

## Exception table

| Situation | Action |
|---|---|
| `python-pptx` missing | compiler falls back to builtin backend automatically; deviation disclosed in report + result.json |
| no organizer template | builtin backend; disclose plain-theme deviation |
| image-only / encrypted PDF | use `ocr-tool` on page renders; if still unreadable, state it in uncertainty — never invent content |
| figure needs cropping | `pdftoppm -r 200 -f P -l P -x X -y Y -W W -H H` (pixel box in the rendered page), save as PNG |
| figure is a photo/scan region | crop generously; keep the paper's own figure number in `caption` and `evidence.ref` |
| font substitution in preview | check `render_manifest.json` fonts (fc-list); if a CJK font is missing, prefer the paper's language fonts available in fc-list and note the substitution |
| slide overflow | nothing to do — compiler moves overflow to the backup section and labels it |
| table too wide | reduce columns in the spec (keep the decisive ones); put the full table in notes/backup |
| soffice missing | render_preview exits 0 with `renderer_unavailable`; disclose and continue |
| template placeholders insufficient | template backend adds a plain text box and records the deviation |

## Delivery checklist

- [ ] `/app/output/deck.pptx` opens; slide count ≤ limit (+ labelled backup)
- [ ] every content/figure/table slide has a stamped evidence footer matching the spec
- [ ] every slide has non-repeating speaker notes (demotions included)
- [ ] `/app/output/compile_report.json` lists backend, deviations, all demotions/shrinks
- [ ] `/app/output/preview/` PDF + per-slide PNGs inspected by eye; `render_manifest.json` present
- [ ] `/app/work/deck.spec.json` copied to `/app/output/` (page-level evidence map)
- [ ] `/app/output/result.json` has original `case_id`, all `output_contract`
      fields, honest status/sources/uncertainty/change_record
- [ ] no fabricated numbers, figure numbers, captions, or software state

## Minimal illustrative example (EXAMPLE — not a case result)

```bash
# spec with 2 slides, no template -> builtin backend
cat > /tmp/deck.spec.json <<'EOF'
{"meta": {"title": "Demo", "language": "en", "slide_limit": 10, "max_bullets": 6},
 "slides": [
  {"id": "s1", "kind": "title", "title": "Demo deck", "claim": "A demo.",
   "notes": "Say hello."},
  {"id": "s2", "kind": "content", "claim": "X improves Y by 40% (95% CI 33-47).",
   "bullets": ["Setup: cohort A vs B", "Outcome: Y at 12 weeks"],
   "evidence": [{"ref": "Table 2", "page": 7}],
   "notes": "Emphasize the CI, expect a question on power."}]}
EOF
python3 "$SKILL_DIR/scripts/validate_spec.py" --spec /tmp/deck.spec.json
python3 "$SKILL_DIR/scripts/compile_deck.py" --spec /tmp/deck.spec.json --out /tmp/deck.pptx
python3 "$SKILL_DIR/scripts/render_preview.py" --deck /tmp/deck.pptx --outdir /tmp/preview
```

A full end-to-end walkthrough with a complete spec and a compile_report excerpt
is in `examples/minimal_example.md`.
