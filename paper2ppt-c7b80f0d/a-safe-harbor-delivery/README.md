# ppt-safe-harbor-delivery

Budget-aware execution protocol for the "论文转学术 PPT" (paper → academic slide deck)
challenge (`ppt-c7b80f0d`). It guarantees that **at every moment of the run a complete,
valid deliverable set exists on disk**: scaffold an honestly-partial output in the first
minutes, upgrade one slide at a time in main-line priority order under explicit time/request
checkpoints, then finish with a mandatory render-verify pass (LibreOffice → PDF → per-slide
PNG) with a render manifest.

This bundle is the *delivery-engineering* complement to evidence-fidelity and
declarative-spec skills: its center of gravity is scheduling, checkpointing, and
guaranteed-valid outputs.

## Install

Copy the `skill/` directory contents into the evaluator's skill directory:

```bash
cp -R skill/ /skills/weekly-skill/
```

No build step. No third-party Python dependencies for the scripts (see below).

## Dependencies

| Component | Requirement |
|---|---|
| All `scripts/*.py` | Python 3.8+ standard library only. `python-pptx` is imported lazily inside try/except and only when a `--template` is given. |
| Template backend (optional) | python-pptx (tested with 1.0.2). Absence is handled: stdlib writer fallback + recorded deviation. |
| `render_preview.py` | LibreOffice `soffice` (headless) + `pdftoppm` (poppler), `fc-list` optional. Missing `soffice` degrades gracefully: manifest `renderer_unavailable`, exit 0. |
| P1 extraction (agent-run) | `pdftotext` (poppler); OCR tool for image-only PDFs. |

## Usage walkthrough

```bash
# P0 — scaffold (first ~90 s of the run)
python3 scripts/scaffold_output.py --case /input/case.json --task /input/task.md \
    --outdir /app/output --workdir /app/work
python3 scripts/build_skeleton_deck.py --state /app/work/session_state.json \
    --out /app/output/deck.pptx            # [--template /input/tpl.pptx] [--titles-from work/paper.txt]
python3 scripts/validate_output.py --outdir /app/output --case /input/case.json \
    --state /app/work/session_state.json   # expect deliverable_state: partial

# P1 — extract (agent): pdftotext -layout paper.pdf work/paper.txt; write per-slide
#      bullets/notes files under work/extract/.

# P2 — upgrade slides in priority order; each step re-validates
printf -- '- Problem: ...\n- Why it matters: ...\n' > work/extract/02-problem.bullets.txt
printf '30s: motivate from X; transition to gap.\n' > work/extract/02-problem.notes.txt
python3 scripts/patch_slide.py --deck /app/output/deck.pptx --slide 2 \
    --title "Problem & Background" \
    --bullets-file work/extract/02-problem.bullets.txt \
    --notes-file  work/extract/02-problem.notes.txt \
    --footer "Source: §1 Introduction"

# P3 — render & verify (reserve final ~120 s)
python3 scripts/render_preview.py --deck /app/output/deck.pptx --outdir /app/output/preview
python3 scripts/validate_output.py --outdir /app/output --case /input/case.json \
    --state /app/work/session_state.json

# P4 — finalize result.json (status, contract fields, uncertainty, change record).
```

Files produced: `result.json`, `deck.pptx` (+ `deck.pptx.slides.json` sidecar),
`preview/slide-*.png`, `preview/deck.pdf`, `render_manifest.json`,
`validation_report.json`; state in `work/session_state.json`.

See `SKILL.md` for the full protocol, `references/budget_protocol.md` for the checkpoint
table, `references/output_contract.md` for result.json rules, `examples/minimal_example.md`
for an end-to-end illustration.

## Limitations

- The stdlib deck writer (minipptx) supports one visual layout (title + bullets + footer,
  16:9). It cannot embed images; evidence slides carry verbatim numbers/captions as text.
  Use the template backend (python-pptx) when richer layouts or embedded figures are needed.
- Template-backend decks cannot be patched by `patch_slide.py` (zip/XML surgery would risk
  the template's masters); the script refuses and prints the exact python-pptx recipe instead.
- `scaffold_output.py` infers constraints best-effort (case.json keys + light task.md regex);
  the case's explicit `output_contract` always wins.
- Render verification requires LibreOffice; without it only structural validation is possible
  (disclosed in `uncertainty`).

## Maintenance

- Keep `scripts/` stdlib-only; test changes with the smoke sequence in
  `examples/minimal_example.md` plus opening the deck with python-pptx
  (`Presentation(path)` must not raise).
- If the harness budget changes, update defaults in `scaffold_output.py`
  (`DEFAULT_TIME_BUDGET_S`, `DEFAULT_REQUEST_BUDGET`) and the checkpoint percentages in
  `references/budget_protocol.md`.
- Repository: https://github.com/99mrliu/bohrium-deep-research-skills/tree/main/paper2ppt-c7b80f0d/a-safe-harbor-delivery
