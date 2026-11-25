# SYNTHETIC quality-gates task

Canonical runtime root is `/app/case/quality-gates` with `task.md` and `input/case.json`; direct case directories containing both files and all materials are also accepted. Work/output defaults are `/app/work/quality-gates` and `/app/output/quality-gates`.

1. Read `source_paper.md`, `data.csv`, `specification.json`, `workorder.json`, and `scientific_review.json`. The source review is a native Agent judgment. Do not let the runner infer nodes, directions, feedback, uncertainty, or biological validity.
2. Run `python3 scripts/runner.py run --case-root /app/case/quality-gates` to execute observed through audited. Each checkpoint and the first partial result are atomic.
3. Expect fresh machine success to be `partial`, not complete. Inspect actual PNG and PDF, calculate their SHA-256 hashes, and write a visual-review JSON with `status: passed`, reviewer, observations, limitations, `png_sha256`, and `pdf_sha256`.
4. Run `python3 scripts/runner.py attest --case-root /app/case/quality-gates --visual-review /path/to/visual-review.json` to advance audited → delivered. A hash mismatch is a contract failure.
5. Recovery tests use `--inject-failure missing-png` or `--inject-failure missing-result-field`; expect exit 3 and failed result. Rerun the same case/work/output with `--resume` and no injection. Missing exports are regenerated and incomplete result fields rebuilt. Exit codes: 0 audited partial or complete attestation, 2 usage/internal, 3 contract/artifact, 4 scientific review.

The text-only bundle deliberately stores no binaries. `scripts/validate_example.py` creates all real SVG/PNG/PDF/results under challenge-scoped `validation/quality-gates/`, with an isolated mirror of `/app/work` and `/app/output`; no privileged `/app` writes are needed for local validation.
