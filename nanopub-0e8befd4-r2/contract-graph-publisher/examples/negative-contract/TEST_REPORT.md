# EXACT extra-field negative real test report

Scope: SYNTHETIC deliberate contract violation, not a formal result.

Command executed from the Skill root (the shell captured the publisher status, then asserted the expected rejection and absence of final files):

```bash
set +e
PYTHONDONTWRITEBYTECODE=1 python3 scripts/publish.py --case examples/negative-contract/input/case.json --task examples/negative-contract/input/task.md --resources environment/resources.yaml --work examples/negative-contract/work --output examples/negative-contract/actual
status=$?
set -e
printf 'NEGATIVE_EXIT=%s\n' "$status"
test "$status" -eq 2
test ! -e examples/negative-contract/actual/result.json
test ! -e examples/negative-contract/actual/nanopubs.trig
test ! -e examples/negative-contract/actual/nanopubs.jsonld
printf 'NEGATIVE_REJECTION_AND_NO_FINAL_ARTIFACTS=PASS\n'
```

Observed stderr:

```text
ERROR: manifest.output_fields must exactly match output_contract.fields; missing=[] extra=['debug_status']
```

Observed status and assertions:

```text
NEGATIVE_EXIT=2
NEGATIVE_REJECTION_AND_NO_FINAL_ARTIFACTS=PASS
```

The wrapper's assertions exited 0. `work/publish-error.json` records `complete_publication_claimed=false`. There is no final `result.json`, TriG or JSON-LD. Because the exact original keys cannot be reconciled with the manifest, no potentially misleading partial result was written; an honest error is the safe early checkpoint.

Limit: this negative case proves rejection of an additional manifest-declared top-level key. It is not evidence that arbitrary external schemas or every possible malformed RDF file are handled.
