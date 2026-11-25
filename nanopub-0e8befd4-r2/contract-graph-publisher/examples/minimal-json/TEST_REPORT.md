# Minimal JSON real test report

Scope: SYNTHETIC test only, not a formal result. No other bundle was read or reused.

Commands were run from the Skill root with Python 3 and `PYTHONDONTWRITEBYTECODE=1`:

```bash
python3 scripts/publish.py --case examples/minimal-json/input/case.json --task examples/minimal-json/input/task.md --resources environment/resources.yaml --work examples/minimal-json/work --output examples/minimal-json/expected
python3 scripts/publish.py --case examples/minimal-json/input/case.json --task examples/minimal-json/input/task.md --resources environment/resources.yaml --work examples/minimal-json/work --output examples/minimal-json/actual
python3 -c 'import json,pathlib; root=pathlib.Path("examples/minimal-json"); actual=json.loads((root/"actual/result.json").read_text(encoding="utf-8")); expected=json.loads((root/"expected/result.json").read_text(encoding="utf-8")); assert actual==expected; assert not list((root/"actual").glob("*.trig")); assert not list((root/"actual").glob("*.jsonld")); print("MINIMAL_MATCH", len(actual["claims"]), "claims; NO_RDF_ARTIFACTS")'
```

Observed results:

- Both publisher invocations exited 0 and independently read back `result.json`.
- Expected run elapsed 0.002476 seconds; actual run elapsed 0.001284 seconds. Both reported 0 network requests.
- The comparison printed `MINIMAL_MATCH 2 claims; NO_RDF_ARTIFACTS` and exited 0.
- Exact keys are `case_id`, `claims`, `evidence`, `sources`, `uncertainty`, `change_records`; case_id is `SYNTHETIC-MINIMAL-001`.
- Reference counts: 2 claims, 2 evidence records, 1 source, all complete.
- `expected/result.json` is a real generated result, not hand-written expected output. `expected/validation-report.json` and `actual/validation-report.json` are independent text reports.
- Work contains early `result.partial.json` and validated `result.candidate.json`.
- No `nanopubs.trig` or `nanopubs.jsonld` exists in either expected or actual JSON output directory.

Limit: this is a local JSON contract/reference test, not truth validation of the synthetic claims.
