# Minimal invocation example (illustrative, synthetic)

This example shows the interface only. The paper, numbers and outputs below are **synthetic illustrations**, not a formal case result.

## Input (hypothetical)

- `/input/case.json` — `case_id: "DEMO-SYNTH"`, output contract with root fields `case_id, status, editable_source, export_artifact, content_map, compliance_checks, exceptions`.
- `/input/paper.pdf` — a (hypothetical) paper reporting a 12% error reduction in its Figure 2.
- `/input/artifacts/slide-workorder.json` — audience: defense committee; duration: 10 min speaking + 5 min Q&A; slide count: 8; template: `target-template.pptx`; mode: create.

## Invocation

> Use talk-story-architect on the paper, template and slide work order under /input; deliver the deck, storyboard, previews and result.json to /app/output.

## What the agent does

1. Contract intake → `/app/work/contract.json`; early `/app/output/result.json` (status `partial`).
2. `material.json`: central question, approach, results with `{statement, strength, locator}` (e.g. the Figure 2 result, strength `established`, locator `paper.pdf p.4 Fig.2`).
3. `audience.json`: decision = "committee can judge validity of the method"; objections → gap real? validation adequate? contribution boundary?
4. Spine = `defense`; 10 min over 8 slides → time budget per beat.
5. `storyboard.json` (see `storyboard.example.json`), validated:
   `python3 scripts/storyboard_check.py /app/work/storyboard.json --contract /app/work/contract.json`
   → `storyboard OK: 8 slides, total 600s of 600s`.
6. Deck built on the template's layouts; Figure 2 cropped from the rendered page with its caption citation; notes carry transitions and timing.
7. Render → PDF/PNG previews inspected; `result.json` finalized with real paths, compliance checks and `status: complete`.

## Illustrative output excerpt

`storyboard.example.json` in this directory is the kind of artifact phase 4 produces — marked as an example, reusable as a format reference only.
