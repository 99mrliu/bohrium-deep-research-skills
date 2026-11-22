# Budget & Checkpoint Protocol

Defaults: 900 s wall time, 64 model requests, 16384 tokens/response. If the case states
different budgets, scale percentages (they are budget-relative, not absolute).

Track both clocks. `session_state.json.budget.started_at` is written by
`scaffold_output.py`; compare `date +%s` against it. Count your own requests.

## Phase table

| Phase | Window (time) | Window (requests) | Goal | Exit condition |
|---|---|---|---|---|
| P0 scaffold | 0–10% (~90 s) | 1–6 | Valid partial `result.json` + skeleton `deck.pptx` + validation report exist | `validate_output.py` prints `partial` (not `broken`) |
| P1 extract & plan | 10–35% (~315 s) | 7–22 | `paper.txt` + per-slide extract files under `work/extract/`; slide plan reconciled with paper's real figures/tables | every planned slide has an extract file (or a recorded "no content in paper" note) |
| P2 slide upgrades | 35–80% (~720 s) | 23–50 | Slides patched in priority order, each step validated | all main-line slides `done` OR checkpoint fires |
| P3 render & verify | 80–95% (~855 s) | 51–60 | `deck.pdf` + PNG previews + `render_manifest.json`; defects fixed or disclosed | manifest written; final validate run |
| P4 finalize | last ~5% (reserve **≥120 s** incl. P3 tail) | 61–64 | `result.json` finalized: status, contract fields, uncertainty, change record, sources | `deliverable_state` = complete/partial |

## Checkpoint rules (evaluate at the end of EVERY request)

1. **Invariant check:** after every mutating action, `/app/output` still validates. If a
   patch broke the deck, re-validate immediately; on `broken`, restore by re-running
   `build_skeleton_deck.py` (loses upgrades, keeps validity) — never continue on a broken set.
2. **50% time, method slide not done** → compress plan to ≤8 slides: edit `slide_plan` in
   `session_state.json` (drop backup, limitations, extra evidence — in that order), rebuild
   skeleton, re-apply already-written extract files, continue.
3. **80% time OR request #50** → stop ALL new content. Remaining placeholders stay
   placeholders (that is legal and honest). Go to P3 now.
4. **Request budget < 5 remaining** → exactly these requests left: render, validate,
   finalize result.json, (spare). Nothing else.
5. **Response-token risk:** never paste more than ~30 lines of extracted paper text per
   response; write extracts to files with heredocs instead of holding them in context.
6. **Each model request should end with a state update + validate.** A request that only
   "thinks" spends budget without moving the deliverable; fold thinking into a request that
   also writes a file.

## Abort rules per phase (drop to skeleton+notes and jump to P3)

- P1: `pdftotext` fails twice (encrypted/image-only and no OCR) → keep all placeholders,
  set status `unable_to_determine` for content fields, jump to P3.
- P2: a patch fails twice on the same slide → leave that slide as placeholder, note it in
  `uncertainty`, move to the next slide. Never burn >2 requests on one slide's formatting.
- P3: render fails once with a fixable cause (e.g. missing outdir) → fix and retry once;
  otherwise write `renderer_unavailable`/failed manifest, disclose, go to P4.

## Rationale

Harness cutoffs arrive mid-request. The only things that survive are files on disk, so the
protocol front-loads a *complete, valid, honest* deliverable (P0) and makes every subsequent
step a monotonic improvement of files already valid (checkpoint invariant). Placeholders are
a feature: `[pending: extract from §Method]` is truthful, machine-detectable, and scores
partial credit, whereas a half-written deck with corrupt XML scores zero. Reserving the last
~120 s for render+finalize guarantees the "editable slides have real previews" and
"result.json reflects reality" contract clauses are never skipped under time pressure.
