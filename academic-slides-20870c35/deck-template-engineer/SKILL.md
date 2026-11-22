---
name: deck-template-engineer
description: Produce or revise academic slide decks that strictly honor the supplied PowerPoint template and survive export. Performs template/master forensics, layout-slot mapping, version-safe editing of starting decks, and an automated render QA pipeline (page count, blank pages, text overflow, font substitution, image integrity) with a repair playbook, delivering the editable deck, rendered PDF/PNG previews, compliance records and result.json to /app/output. Use for cases under /input involving a target template and/or starting deck with fixed slide count and export requirements.
---

# Deck template engineer: the deck you export is the deck they open

The failure this skill prevents is mechanical: template identity destroyed by rebuilding from scratch, masters corrupted by "one small edit", text overflowing after export, fonts silently substituted, images cropped, and no way to tell which iteration is the deliverable. The method is **forensics → mapping → build/edit with version control → render QA → repair**, with every compliance claim backed by an observed value, never a presumed one.

Content selection and narrative are covered only at the depth the deck mechanics need; this skill's added value is that the delivered file is editable, template-faithful and provably rendered. If a case is purely about narrative reorganization of an existing deck, apply the edit-mode versioning and render QA phases all the same.

## Phase 0 — Contract intake (always first)

1. Recursively inspect `/input`: actual `case.json`, `task.md`, `material.json`, `artifacts/slide-workorder.json` (locate real names), `environment/resources.yaml` if present, and every PPTX/PDF. Read the actual files; a file named `template.pptx` is a suspect until inspected.
2. Record in `/app/work/contract.json`: real `case_id`; exact `output_contract` root fields; mode (create from template / edit starting deck / adapt); exact slide count; required layouts or master names; fonts/colors/footer rules; preservation rules for existing slides; export formats; naming of deliverables. Case requirements outrank this skill's defaults.
3. `mkdir -p /app/work /app/work/versions /app/output`; immediately write `/app/output/result.json` with the real `case_id`, all contract root fields holding type-correct partial values, `status: partial`, exceptions list. Update after each phase.
4. Tool census in `/app/work/tools.json`: python3 + python-pptx version, `soffice` path and version, `pdftoppm`/`pdffonts`/`pdftotext`, `fc-list` fonts. Never depend on network installs. Budget is finite: batch shell calls, save early, at most two full render cycles.

## Phase 1 — Template and starting-deck forensics

Run `python3 scripts/inspect_deck.py <file.pptx> --out /app/work/inspect_<name>.json` for the template and, in edit mode, the starting deck (see `references/template-forensics.md`). The report captures: slide size, masters, layouts per master, every placeholder (type, idx, position, size), theme fonts and colors, existing slide inventory with their layout names, footer/slide-number fields.

Decisions this drives, recorded in `/app/work/layout_map.json`:

- Which layout each planned slide uses and which placeholder receives the title, body and each figure — before any slide exists.
- Whether a mandated layout/master exists; if the work order demands one the template does not have, record the conflict now, not after building.
- In edit mode: the exact slide→layout→master relationships to preserve, so a save cannot silently re-parent slides.

## Phase 2 — Build or edit with version discipline

Follow `references/edit-versioning.md`. Essentials:

- **Create mode**: `Presentation(template_path)` — build inside the actual template so masters, theme and footers are inherited, never reconstructed. Remove sample slides only when they are not mandated content. Add slides with `slide_layouts[i]` of *this* presentation; put text in the layout's title/body placeholders when they exist; only fall back to free text boxes (styled with theme fonts/colors) when no placeholder fits, logging each fallback.
- **Edit mode**: copy the starting deck to `/app/work/versions/v1.pptx` and edit the copy. Change only what the work order requests; unrequested slides, their order, masters, notes and embedded media stay byte-identical in intent. Snapshot `v2.pptx`, `v3.pptx`… per revision round with a `changelog.md` entry: what changed, why, which slide indices, how to roll back (copy which version). The deliverable is the last snapshot, copied to the contract's path.
- Never claim template application you did not verify: after saving, reopen and assert each new slide's `slide_layout` is the intended layout object of the correct master; a visual resemblance check is not a relationship check.
- Figures: crop from the rendered source PDF at ≥150 dpi with margins that keep legend/axes/units/panel letters; preserve aspect ratio; place inside the content placeholder bounds or a clear content region that does not cover master graphics, logos or footers. Cite exhibit number and page beside the figure.
- Text fit: shorten or split content rather than shrinking below the template's own size floor; if a mandated text cannot fit, that is a plan defect — fix the plan.

## Phase 3 — Render QA pipeline

Run `python3 scripts/render_qa.py /app/output/presentation.pptx --outdir /app/output --out /app/output/render_qa.json` (behavior and checks in `references/render-playbook.md`). With `soffice` available it converts to PDF, rasterizes pages and checks:

1. **Count** — PDF pages == deck slides == mandated count.
2. **Blank** — no page with neither extractable text nor images (catches lost masters and all-white slides).
3. **Overflow** — text extracted per page is checked for lines that approach/exceed page bounds via `pdftotext -bbox` geometry; suspects are listed for visual confirmation.
4. **Fonts** — `pdffonts` output vs the theme fonts recorded in phase 1; substitutions are named, not waved through.
5. **Integrity** — zero-byte outputs, missing images (`pdfimages -list` vs placed pictures), empty placeholders ("Click to add" residues) via deck re-inspection.

Then the **visual pass**: assemble a contact sheet of all rendered pages and inspect every page at readable scale — crops, contrast, overlaps, footer and numbering, equation fidelity. Automated checks nominate suspects; the agent's inspection decides. If no renderer exists, deliver the PPTX, mark render `unverified` in the QA report and result.json, and do not produce fake previews.

## Phase 4 — Repair, re-render, record

Apply `references/render-playbook.md`'s failure→repair table: overflow → shorten/split, never shrink past floor; font substitution → remap to an installed font and note the change; clipped figure → re-crop with margin; lost master → rebuild the affected slides from the correct layout. Keep each repair in `changelog.md` with before/after page numbers. Re-render once after repairs; whatever remains is recorded as a known issue.

## Phase 5 — Compliance record and delivery

Finalize in `/app/output`: deck (contract's path), PDF, per-page PNGs, `render_qa.json`, `layout_map.json`, `changelog.md`, and `result.json` with:

- all contract root fields populated with real existing paths;
- `compliance_checks` as observed facts: actual layout/master names per slide, renderer name+version, font list from `pdffonts`, page count, file sizes and SHA-256 of deliverables, repair history;
- `exceptions`: every unverified check, conflict (e.g. mandated layout missing, template/starting-deck master incompatibility) and known residual issue, each with impact. Honest `partial` beats a decorated `complete`.

## Invocation, scope and failure handling

Typical invocation: "Use deck-template-engineer on the work order, template and starting deck under /input; deliver the compliant deck, render QA report, previews and result.json to /app/output." A synthetic minimal example is in `examples/minimal/`.

In scope: template-faithful creation, version-safe editing, export/render verification and repair for academic decks. Out of scope: choosing the science narrative, judging claims' truth, redesigning masters. On failure — corrupt/encrypted PPTX, renderer absent, masters in conflict, mandated content that cannot fit the mandated count — deliver the best honest partial (source deck + records), name the exact blocker in exceptions, never fabricate a render, a layout relationship or a compliance pass.
