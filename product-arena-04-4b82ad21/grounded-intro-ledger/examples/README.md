# Examples — SYNTHETIC EXAMPLE

> **All material in this directory is synthetic.** The case, manuscript facts,
> references, authors, journals, DOIs and abstracts are invented to demonstrate
> the skill's interface end to end. Nothing here is a real scientific claim,
> and nothing here is an answer to the organizers' fixed cases.

## Layout

- `synthetic-case/` — an invented mini case in the platform's input shape:
  `case.json` (with `output_contract`), `task.md`, `material/` (fact base +
  bibliography in JSON and Markdown), and `filled/` (a draft introduction and
  a claims ledger written against that material).
- `run_example.sh` — runs the real pipeline.
- `sample-output/` — the real outputs of the last run of `run_example.sh`
  (regenerate any time).

## Run

```sh
bash examples/run_example.sh
```

What it does:

1. `extract_sources.py` builds `sample-output/work/evidence/evidence_store.json`
   from the synthetic case (6 references, evidence levels, material-gap notes).
2. `bind_claims.py` verifies the 11 filled claim records: every quote verbatim,
   every number traced, no title-only attributions (expected: pass, exit 0).
3. `verify_grounding.py` audits the draft introduction against the ledger and
   emits `sample-output/verification.json`, the object that would go into the
   `verification` field of `result.json`.
4. A scaffold run shows how claim skeletons are generated from an existing
   draft.

To see failures detected, corrupt a quote in a *copy* of
`synthetic-case/filled/claims.json` (e.g. change `0.41` to `0.42` inside a
quote) and re-run step 2 against the copy: `bind_claims.py` exits 1 and names
the claim and rule (R3) that failed.
