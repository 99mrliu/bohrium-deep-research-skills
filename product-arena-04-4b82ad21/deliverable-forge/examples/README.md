# Examples — SYNTHETIC EXAMPLE

> **All material in this directory is synthetic.** The case, manuscript facts,
> references, authors, journals, DOIs and abstracts are invented to demonstrate
> the skill's interface end to end. Nothing here is a real scientific claim,
> and nothing here is an answer to the organizers' fixed cases.

## Layout

- `synthetic-case/` — invented mini case in the platform input shape, plus
  `filled/introduction.md` (v1 draft) and `filled/introduction.v2.md`
  (a revised v2, used to demonstrate change records).
- `run_example.sh` — runs the real rendering pipeline.
- `sample-output/` — real outputs of the last run. **Binary artifacts**
  (`introduction.docx`, `preview.pdf`) are generated and verified during the
  run and then removed, because skill bundles ship UTF-8 text only; re-run
  `run_example.sh` to regenerate and inspect them.

## Run

```sh
bash examples/run_example.sh
```

Steps executed for real:

1. `word_budget.py` — measures words per rhetorical part against the case
   limits (400 total / 260 related work) and writes `work/word_report.json`.
2. `md2docx.py --verify` — writes a genuine OOXML `introduction.docx` and
   re-opens it to prove the container and XML are valid.
3. `make_preview.py` — renders `preview.pdf` with the first available
   renderer (pdflatex/xelatex/tectonic, else matplotlib, else an honest
   plain-text `preview.txt` with status `not_verifiable`); see
   `preview_report.json` for which one fired.
4. `change_record.py` — sentence-level diff v1→v2 with rationales, written to
   `work/changes.json` (the shape of `version_and_boundary.changes`).
5. The script inspects the docx internals and saves a text log
   (`work/docx_inspection.txt`) before removing the binary.
