# grounded-intro-ledger

Agent skill for writing and auditing manuscript introductions and related work
in which **every claim about prior work is bound to a verbatim quote** from the
provided sources, every number is traced to a quote or to the fact base, and
every contribution names an available manuscript anchor. Center of gravity:
upstream fact truthfulness.

- `SKILL.md` — the skill (purpose, runtime contract, method, exceptions).
- `scripts/` — pure Python 3 stdlib tools: `extract_sources.py` (evidence
  store), `bind_claims.py` (verbatim binding R1–R6 + scaffold),
  `verify_grounding.py` (draft audit G1–G6).
- `references/` — grounding protocol and claim schema.
- `examples/` — runnable **synthetic** end-to-end example (`bash
  examples/run_example.sh`); invented material, interface demonstration only.

Runtime contract in one line: read `/input/case.json` + `task.md`, work in
`/app/work`, deliver editable artifacts plus a contract-complete `result.json`
(with `case_id` and honest `status`) in `/app/output`.

Source mirror: see `GITHUB_URL.txt`.
