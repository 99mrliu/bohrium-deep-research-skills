#!/usr/bin/env bash
# End-to-end synthetic interface test. No official case, answer, or score is used.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
ROOT="${CCA_RUN_ROOT:-/tmp/claim-coverage-adjudicator-example}"
case "$ROOT" in
  /tmp/claim-coverage-adjudicator-example|/tmp/claim-coverage-adjudicator-example-*) ;;
  *) echo "CCA_RUN_ROOT must be under /tmp with the claim-coverage-adjudicator-example prefix" >&2; exit 2 ;;
esac
rm -rf "${ROOT:?}"
mkdir -p "$ROOT/main/work" "$ROOT/main/out"
cp -R "$HERE/fixture/input" "$ROOT/main/input"

python3 "$BUNDLE/scripts/scaffold.py" \
  --input "$ROOT/main/input" --work "$ROOT/main/work" --out "$ROOT/main/out"
python3 - "$ROOT/main/out/result.json" "$ROOT/main/input/case.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding='utf-8'))
c = json.load(open(sys.argv[2], encoding='utf-8'))
assert r['case_id'] == c['case_id'] and r['status'] == 'partial'
assert set(r) == set(c['output_contract']['required_fields'])
assert isinstance(r['answers'], dict) and isinstance(r['evidence'], list)
print('PASS early partial uses required_fields and field_types')
PY

cp "$HERE/fixture/claims.defective.json" "$ROOT/main/work/claims.json"
cp "$HERE/fixture/result.draft.json" "$ROOT/main/work/result.draft.json"
set +e
python3 "$BUNDLE/scripts/adjudicate.py" --case "$ROOT/main/input/case.json" --work "$ROOT/main/work"
RC=$?
set -e
[ "$RC" -eq 1 ] || { echo "defective ledger should return 1, got $RC" >&2; exit 1; }
python3 "$BUNDLE/scripts/finalize.py" --case "$ROOT/main/input/case.json" \
  --work "$ROOT/main/work" --out "$ROOT/main/out"
cp "$ROOT/main/out/result.json" "$ROOT/main-partial-result.json"
python3 - "$ROOT/main/work/adjudication.json" "$ROOT/main/out/result.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1], encoding='utf-8'))
result = json.load(open(sys.argv[2], encoding='utf-8'))
codes = {item['code'] for item in report['issues']}
assert 'unsupported_substantive_claim' in codes
assert 'requested_formula_uncovered_or_unsupported' in codes
assert result['status'] == 'partial'
assert result['uncertainty']['missing_objects']
print('PASS missing eq2 evidence forces partial and retains named gaps')
PY

cp "$HERE/fixture/claims.repaired.json" "$ROOT/main/work/claims.json"
python3 "$BUNDLE/scripts/adjudicate.py" --case "$ROOT/main/input/case.json" --work "$ROOT/main/work"
python3 "$BUNDLE/scripts/finalize.py" --case "$ROOT/main/input/case.json" \
  --work "$ROOT/main/work" --out "$ROOT/main/out"
cp "$ROOT/main/out/result.json" "$ROOT/main-success-result.json"
cp "$ROOT/main/work/adjudication.json" "$ROOT/main-success-adjudication.json"
python3 - "$ROOT/main/out/result.json" "$ROOT/main/work/adjudication.json" \
  "$ROOT/main/input/case.json" "$ROOT/main/work/source_excerpts.json" <<'PY'
import json, sys
r, report, c, sources = [json.load(open(p, encoding='utf-8')) for p in sys.argv[1:]]
assert r['status'] == 'success' and report['issue_count'] == 0
assert set(r) == set(c['output_contract']['required_fields'])
assert set(report['supported_formula_ids']) == {'eq1', 'eq2'}
excerpts = {e['excerpt_id']: e for e in sources['excerpts']}
for evidence in r['evidence']:
    e = excerpts[evidence['excerpt_id']]
    assert evidence['quote'] in e['text']
    assert evidence['source_file'] == e['source_file']
    assert evidence['locator'] == e['locator']
print('PASS repaired ledger succeeds with both formulas and verbatim aggregated evidence')
PY

# Legacy fields must behave exactly like required_fields (types/enum retained).
python3 - "$ROOT/main/input/case.json" "$ROOT/legacy-case.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1], encoding='utf-8'))
c['output_contract']['fields'] = c['output_contract'].pop('required_fields')
json.dump(c, open(sys.argv[2], 'w', encoding='utf-8'), indent=2)
PY
mkdir -p "$ROOT/legacy-out"
python3 "$BUNDLE/scripts/finalize.py" --case "$ROOT/legacy-case.json" \
  --work "$ROOT/main/work" --out "$ROOT/legacy-out"
python3 - "$ROOT/legacy-out/result.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding='utf-8'))
assert r['status'] == 'success' and isinstance(r['answers'], dict)
print('PASS legacy fields alias preserves typed success')
PY

# Deliberate contradiction: both answers have valid quote mechanics, but their
# completed central values differ in one explicit contradiction group.
mkdir -p "$ROOT/contradiction/work" "$ROOT/contradiction/out"
cp "$ROOT/main/work/source_excerpts.json" "$ROOT/contradiction/work/source_excerpts.json"
cp "$HERE/fixture/claims.repaired.json" "$ROOT/contradiction/work/claims.json"
cp "$HERE/fixture/result.draft.json" "$ROOT/contradiction/work/result.draft.json"
python3 - "$ROOT/contradiction/work/claims.json" <<'PY'
import copy, json, sys
p = sys.argv[1]
ledger = json.load(open(p, encoding='utf-8'))
claim = ledger['task_atoms'][2]['claims'][0]
claim['contradiction_group'] = 'toy-held-out-score'
other = copy.deepcopy(claim)
other['claim_id'] = 'claim-score-conflicting'
other['answer'] = '0.91 on the fixed toy split'
ledger['task_atoms'][2]['claims'].append(other)
ledger['contradictions'].append({
    'contradiction_id': 'deliberate-score-conflict',
    'contradiction_group': 'toy-held-out-score',
    'claim_ids': ['claim-score', 'claim-score-conflicting'],
    'description': 'Deliberately conflicting synthetic score answers.',
    'status': 'unresolved'
})
json.dump(ledger, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
PY
set +e
python3 "$BUNDLE/scripts/adjudicate.py" --case "$ROOT/main/input/case.json" --work "$ROOT/contradiction/work"
RC=$?
set -e
[ "$RC" -eq 1 ] || { echo "contradiction should return 1, got $RC" >&2; exit 1; }
python3 "$BUNDLE/scripts/finalize.py" --case "$ROOT/main/input/case.json" \
  --work "$ROOT/contradiction/work" --out "$ROOT/contradiction/out"
cp "$ROOT/contradiction/out/result.json" "$ROOT/contradiction-result.json"
python3 - "$ROOT/contradiction/work/adjudication.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding='utf-8'))
assert any(i['code'] == 'unresolved_contradiction' for i in r['issues'])
assert r['recommended_status'] == 'partial'
print('PASS deliberate contradiction cannot be silently collapsed')
PY

# C02-like branch: only the explicit metric is answerable.
mkdir -p "$ROOT/c02/work" "$ROOT/c02/out"
cp -R "$HERE/fixture/c02-input" "$ROOT/c02/input"
python3 "$BUNDLE/scripts/scaffold.py" --input "$ROOT/c02/input" \
  --work "$ROOT/c02/work" --out "$ROOT/c02/out"
cp "$HERE/fixture/c02-claims.json" "$ROOT/c02/work/claims.json"
cp "$HERE/fixture/c02-result.draft.json" "$ROOT/c02/work/result.draft.json"
set +e
python3 "$BUNDLE/scripts/adjudicate.py" --case "$ROOT/c02/input/case.json" --work "$ROOT/c02/work"
RC=$?
set -e
[ "$RC" -eq 1 ] || { echo "C02 missing objects should return 1, got $RC" >&2; exit 1; }
python3 "$BUNDLE/scripts/finalize.py" --case "$ROOT/c02/input/case.json" \
  --work "$ROOT/c02/work" --out "$ROOT/c02/out"
cp "$ROOT/c02/out/result.json" "$ROOT/c02-partial-result.json"
python3 - "$ROOT/c02/out/result.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding='utf-8'))
assert r['status'] == 'partial'
for gap in ('formula representation', 'per-item predictions', 'recalculable raw data or explicit numeric inputs'):
    assert gap in r['uncertainty']['missing_objects']
print('PASS metrics-only branch answers only explicit metric and names missing objects')
PY

# With no substantive answer objects, insufficient_evidence is mandatory.
python3 - "$ROOT/c02/work/claims.json" "$ROOT/c02/work/result.draft.json" <<'PY'
import json, sys
p, draft_path = sys.argv[1:]
ledger = json.load(open(p, encoding='utf-8'))
claim = ledger['task_atoms'][0]['claims'][0]
claim['answer'] = ''
claim['completion_status'] = 'insufficient_evidence'
claim['uncertainty'] = ['Metric answer deliberately withheld for the no-objects branch test.']
json.dump(ledger, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
draft = json.load(open(draft_path, encoding='utf-8'))
draft['answers']['reported_metric'] = ''
json.dump(draft, open(draft_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
PY
set +e
python3 "$BUNDLE/scripts/adjudicate.py" --case "$ROOT/c02/input/case.json" --work "$ROOT/c02/work"
RC=$?
set -e
[ "$RC" -eq 1 ]
python3 "$BUNDLE/scripts/finalize.py" --case "$ROOT/c02/input/case.json" \
  --work "$ROOT/c02/work" --out "$ROOT/c02/out"
cp "$ROOT/c02/out/result.json" "$ROOT/c02-insufficient-result.json"
python3 - "$ROOT/c02/out/result.json" <<'PY'
import json, sys
assert json.load(open(sys.argv[1], encoding='utf-8'))['status'] == 'insufficient_evidence'
print('PASS no substantive answer objects forces insufficient_evidence')
PY

printf '\nAll synthetic adjudicator integration checks passed.\nArtifacts: %s\n' "$ROOT"
