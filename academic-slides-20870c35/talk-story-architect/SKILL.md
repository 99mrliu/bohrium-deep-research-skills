---
name: talk-story-architect
description: Organize an academic talk around its audience, goal and narrative arc. Builds a validated per-slide storyboard (one message per slide, narrative roles, time budget, transitions) from the actual paper and work order, then realizes it as an editable templated deck with speaker notes, evidence locators and rendered previews. Use when a case asks to turn a paper plus a slide work order (fixed audience/duration/slide count/template, sometimes a starting deck) into a presentation under /input with results in /app/output.
---

# Talk story architect: storyboard before slides

The failure this skill prevents is structural: pages that paraphrase the paper section by section, a slide count divorced from the speaking time, and conclusions the audience cannot reconstruct. This skill's unit of work is the **storyboard** — a machine-checkable plan in which every slide has exactly one message, a narrative role, a time slice and a transition — produced and validated *before* any slide is built, then realized into the supplied template.

Adjacent concerns are handled only at the depth a talk needs: claim-to-source precision is recorded as locators, not audited number by number; template mechanics are respected, not re-engineered. If the work order is purely about template migration or about auditing an existing deck's numbers, say so and apply only the relevant phase.

## Phase 0 — Contract intake (always first)

1. Recursively inspect `/input`: read the actual `case.json`, `task.md`, `material.json`, `artifacts/slide-workorder.json` (names may differ; locate them), `environment/resources.yaml` if present, and list all PDF/PPTX/DOCX/XLSX files. Never assume content from a file's name.
2. From the work order record verbatim in `/app/work/contract.json`: `case_id`; the exact `output_contract` root fields; mode (create / edit / adapt); audience and venue; duration in minutes; exact slide count or range; language; template path; starting-deck path if any; source-preservation rules; required sections; export formats; any per-slide instructions. Explicit requirements outrank every heuristic in this skill.
3. `mkdir -p /app/work /app/output`. Immediately write `/app/output/result.json` containing the real `case_id` and every root field named by the case's `output_contract`, with type-correct partial values, `status` reflecting reality (`partial`), and an exceptions/uncertainty list. Update it after each phase. A typical contract for this task family uses root fields like `case_id, status, editable_source, export_artifact, content_map, compliance_checks, exceptions` — copy the case's own field names and nesting, never this example.
4. Record the tool census in `/app/work/tools.json`: python3, python-pptx, `pdftotext`/`pdftoppm`, LibreOffice (`soffice`), fonts (`fc-list`). Use what is installed; do not depend on network installs. Budget is finite (order of 60 model requests / 900 s): plan each phase's commands before running them, batch independent shell calls, and save deliverables before polishing.

## Phase 1 — Abstract the paper into story material

Read the actual paper (text per page via `pdftotext -layout`; render pages with `pdftoppm` when figure content matters) and write `/app/work/material.json`:

- `central_question`: the one question the work answers, in the paper's own scope.
- `approach`: the method in at most two sentences; what is new about it.
- `results`: each key result as `{statement, strength, locator}` where strength is one of `established | preliminary | contextual` and locator is `{file, page, section, figure_or_table}`. Numbers are transcribed exactly with units and conditions.
- `limitations`: the limitations that change interpretation, including ones stated only in discussion.
- `surprise`: what a specialist would not have predicted; what a non-specialist needs explained. These drive slide order, not the paper's table of contents.

Do not invent results. If the paper lacks something the work order requests (e.g. no comparison baseline), record the gap and continue.

## Phase 2 — Model the audience and the talk's goal

Write `/app/work/audience.json` using `references/audience.md`:

- `decision`: what this audience should know, believe or decide after the talk, one sentence, checkable (e.g. "committee can judge whether the method is novel", "group understands progress vs plan and the top risk").
- `prior_knowledge`: what can be assumed; everything else that is load-bearing must be explained on a slide.
- `objections`: the two or three questions this audience is most likely to press; each must be answered by a planned slide or an explicit backup.
- Levers derived from these: background share of slides, terminology explanation scope, evidence depth, and where the conclusion sits (conclusion-first for reviewers, evidence-first for defenses).

## Phase 3 — Choose a narrative spine and allocate the budget

Pick one spine from `references/spines.md` (progress / defense / conference / review / pitch) or justify a hybrid in one line. A spine fixes the role sequence — hook, context, gap, idea, method, validation, result, limitation, takeaway — not a slide quota. Map the material onto spine beats:

- Reorder by argument, not by paper section. Merge what one message can carry; split only when two messages would compete on one slide.
- The opening question must be answered, at its qualified strength, by the closing slide.
- Every limitation in `material.json` that changes interpretation gets a beat; it may share a slide but not vanish.
- Allocate minutes per beat; reserve Q&A time if the work order specifies it.

## Phase 4 — Build and validate the storyboard

Write `/app/work/storyboard.json` per `references/storyboard-spec.md`: for each slide, `index`, `role`, `headline` (one full sentence stating the slide's only message, evidence-qualified), `support` (figure/table/quote locators from `material.json`), `time_sec`, `transition` (the spoken sentence linking from the previous slide), `notes_hint`, and for edit-mode `source_slide`. Hard rules:

- Slide count equals the work order exactly; `sum(time_sec)` equals the allotted speaking time within ±10%.
- One message per slide; the headline is a sentence a listener could repeat, not a topic label ("Method" fails; "X separates A from B at half the cost of Y" passes).
- Reading all headlines in order must reconstruct the talk. This "headline test" is the core quality gate.
- Every headline is supported by its listed locators at its stated strength; framing or synthesis slides are marked `role: framing`.

Run `python3 scripts/storyboard_check.py /app/work/storyboard.json --contract /app/work/contract.json` (stdlib-only; schema and gate details in `references/storyboard-spec.md`). Fix every reported violation before building slides; a storyboard that fails its checks produces a deck that fails on stage.

## Phase 5 — Realize the storyboard into the template

Build the deck so the template's identity survives (details of placeholder/layout handling are secondary here — follow the actual template):

- Create mode: open the actual template with python-pptx, add slides on its own layouts, use title/body placeholders where they exist. Edit mode: copy the starting deck, change only what the work order requests, keep unrequested slides, masters and order; record `source_slide → new_slide` in the storyboard and a change log in `/app/work/changelog.md` (what, why, reversible).
- Slide title = storyboard headline (shortened only if the placeholder cannot fit; the message, not just keywords, survives). Body supports the headline; nothing on the slide may contradict or outrun it.
- Figures are faithful crops from the rendered source page (legend, axes, units, panel letters kept), with the original figure/table number and page cited beside the graphic. Do not redraw data plots from a bitmap; do not place decorative or invented graphics.
- Speaker notes expand the headline — interpretation, the transition sentence, timing, source locator — they must not repeat the bullets verbatim.
- Save to the path the contract requires (typically `/app/output/presentation.pptx`). Keep versioned copies (`/app/work/versions/`) so any iteration can roll back.

## Phase 6 — Render, rehearse, report

- Export with the available renderer (e.g. `soffice --headless --convert-to pdf`), rasterize every page (`pdftoppm -png -r 110`), and inspect a contact sheet plus dense pages: overflow, clipped crops, unreadable type, blank pages, broken masters. Repair the storyboard or the slide, re-render at most twice, then record the residual issue honestly.
- Rehearse on paper: read the headlines in order against the timer; confirm the per-slide time slices sum to the duration and the transitions are speakable. Adjust the storyboard, not just the slides.
- Copy the storyboard to `/app/output/storyboard.json` as the plan record, plus the PDF, PNG previews and `content_map` (slide → locators) as required by the contract.
- Finalize `result.json`: all contract fields with real paths, `status` `complete` or `partial`, per-requirement `compliance_checks` with observed values (renderer version, page count, slide count), uncertainties, and change records. If a renderer was unavailable, deliver the PPTX, mark the render check unverified — never claim a preview you did not produce.

## Invocation, scope and failure handling

Typical invocation: "Use talk-story-architect on the paper, template and slide work order under /input; deliver the deck, storyboard, previews and result.json to /app/output." A minimal worked example (synthetic, marked as example) is in `examples/minimal/`.

In scope: organizing existing research material into a talk for a specified audience/duration/count; create and edit modes; narrative, notes and timing. Out of scope: judging the science itself, recovering numeric data from bitmaps, redesigning template masters. On failure — missing paper, unreadable scan (use OCR if available, else flag), template with unusable layouts, impossible slide count for the mandated coverage — keep the best honest partial deliverable, record the exact blocker in `result.json` exceptions, and never fill gaps with invented content.
