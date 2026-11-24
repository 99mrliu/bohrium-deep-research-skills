# deliverable-forge

Agent skill for the downstream half of introduction/related-work writing:
turning a grounded draft into the **real deliverables** — enforced word
budgets, a genuine editable `.docx` (true OOXML, produced with the Python
standard library only), an inspectable PDF/text preview, and sentence-level
change records for revision tasks. Center of gravity: rendering and delivery
engineering.

- `SKILL.md` — the skill (purpose, runtime contract, method, exceptions).
- `scripts/` — pure Python 3 stdlib tools: `word_budget.py`, `md2docx.py`,
  `make_preview.py`, `change_record.py`.
- `references/` — the artifact contract and revision-record discipline.
- `examples/` — runnable **synthetic** end-to-end example
  (`bash examples/run_example.sh`); invented material, interface demo only.
  Binary artifacts are generated and verified during the run, then removed
  (bundles ship text only).

Runtime contract in one line: read `/input/case.json` + `task.md`, work in
`/app/work`, deliver real editable artifacts plus a contract-complete
`result.json` (with `case_id` and honest `status`) in `/app/output`.

Source mirror: see `GITHUB_URL.txt`.
