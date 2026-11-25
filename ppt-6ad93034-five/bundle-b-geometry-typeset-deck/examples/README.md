# Synthetic example (合成示例)

**Everything here is synthetic.** Fictional study, fictional template,
fictional numbers. Marked `synthetic` in `plan.json` meta, the deck title
prefix `SYNTHETIC EXAMPLE — `, and `"synthetic_example": true` in
`result.json`.

## Run

```bash
bash run_example.sh
```

## What it builds

`make_fixture.py` (stdlib only) generates all inputs under `examples/work/`:

- `input/target-template.pptx` — a minimal valid pptx assembled by **importing
  the bundle's own `deck_forge` machinery** (`sys.path.insert` to
  `../scripts`) with a custom `theme1.xml`: title font **Georgia**, body font
  **Helvetica**, accent1 **#1F4E79**. It plays the role of the organizer
  template.
- `input/case.json` — `case_id: "synthetic-demo-002"` with an
  `output_contract` containing the six default fields.
- `input/task.md` — the slide work order.
- `work/plan.json` — the agent-authored plan, deliberately DENSE:
  - title slide,
  - **12 long bullets** on one slide → forces the continuation-split policy,
  - **45 bullets** on one slide → exceeds the continuation budget → forces
    backup-overflow slides,
  - one slide with a `source_line` and a **missing image** → placeholder box.

## What run_example.sh asserts

1. `theme.json` `source == "template"` with Georgia/Helvetica/#1F4E79 probed.
2. `layout.json` contains `(cont.)` slides, backup slides, a non-empty
   `actions[]` log, and body font never below 14pt.
3. `presentation.pptx` is a valid zip whose `ppt/theme/theme1.xml` is
   **byte-identical** to the fixture template's theme (theme cloning proof).
4. Preview SVGs exist; preview PNGs (matplotlib is available on this machine)
   are all >10KB.
5. `render_audit.json` verdict is `RENDERER_MISSING` (no soffice locally) —
   the honest degradation path.
6. `result.json` has `case_id == "synthetic-demo-002"`, all six contract
   fields, `status: "success"`, `synthetic_example: true`.

See `expected_output.md` for a captured artifact listing.
