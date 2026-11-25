# examples — synthetic end-to-end demo (合成示例 / synthetic)

Everything in this directory is a **synthetic example**: the fixture paper's
title contains SYNTHETIC, the case is `synthetic-demo-005` with
`"synthetic_example": true`, the deck title starts with "SYNTHETIC EXAMPLE — ",
and the numbers (e.g. "accuracy of 92.3%") are invented demo data, not real
research results.

## Files

- `make_fixture.py` — stdlib-only generator: writes `work/input/paper.pdf`
  (one-page synthetic English paper via a minimal PDF writer), `case.json`,
  `task.md`, and `work/plan.json` (3 slides whose evidence quotes really
  appear in the fixture paper).
- `run_example.sh` — full pipeline:
  1. `make_fixture.py`
  2. `watchdog.py init` — **asserts `result.json` exists immediately** with
     honest `status=partial`
  3. `journal.py init` → `pdf_text.py` → journal log → `gate.py plan`
  4. `mini_build.py` → journal log → `gate.py build`
  5. PDF export only if `soffice` exists → `gate.py render`
     (on machines without soffice this records an honest `renderer-absent` pass)
  6. `replay.py` (manifest + RUN_REPORT) → `replay.py --check` →
     `journal.py verify` → `watchdog.py finalize --status success`
  7. **Negative demo (by design):** copies the whole tree, flips one byte in
     the copied `presentation.pptx`, and verifies that BOTH `journal.py verify`
     and `replay.py --check` exit non-zero naming the tampered artifact. The
     script itself asserts the non-zero exits; this is a feature demonstration,
     not a failure.
- `expected_output.md` — what the run should produce and what each artifact proves.

## Run

```
bash run_example.sh    # exit 0 means the demo AND the tamper detection worked
```

Scratch space (`examples/work/`) is deleted and recreated on every run.
