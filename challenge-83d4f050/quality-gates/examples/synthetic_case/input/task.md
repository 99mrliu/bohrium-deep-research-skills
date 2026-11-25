# SYNTHETIC quality-gates task

Use `task.md` at the case root as the canonical task contract. This input-side copy preserves compatibility with readers expecting `/input/case.json` and `/input/task.md` together.

Run `python3 scripts/runner.py run --case-root /app/case/quality-gates`, inspect generated PNG/PDF, then hash-bind native visual attestation using `runner.py attest`. Fresh success is audited/partial until that visual gate. Contract failures return 3; scientific review failures return 4. Test recovery with the two documented `--inject-failure` modes followed by `--resume`. All example data and claims are SYNTHETIC.
