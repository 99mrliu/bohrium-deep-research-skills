#!/bin/sh
# 合成示例（synthetic demo, NOT a formal case result）：
# 现场生成合成 case.json 与三步 plan，演示 bootstrap -> gate(含失败/续跑) -> selfcheck。
set -eu
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d /tmp/gate-demo.XXXXXX)"
echo "demo workspace: $WORK"
mkdir -p "$WORK/input" "$WORK/work" "$WORK/output"

python3 - "$WORK" <<'PY'
import json, sys
w = sys.argv[1]
case = {"case_id": "demo-synthetic-001",
        "task": "count rows of a synthetic table",
        "output_contract": {"fields": ["analysis_result", "evidence", "exceptions"]}}
json.dump(case, open(w + '/input/case.json', 'w'), indent=1)
plan = {"steps": [
  {"name": "G1_make_data", "gate": "G1",
   "cmd": ["python3", "-c",
           "import sqlite3; c=sqlite3.connect('%s/work/demo.db'); "
           "c.execute('create table t(id integer, v real)'); "
           "c.executemany('insert into t values (?,?)', [(i, i*1.5) for i in range(10)]); "
           "c.commit(); open('%s/work/schema_note.txt','w').write('table t: 10 rows')"
           % (w, w)],
   "produces": ["%s/work/schema_note.txt" % w]},
  {"name": "G2_count", "gate": "G2",
   "cmd": ["python3", "-c",
           "import sqlite3, json; c=sqlite3.connect('%s/work/demo.db'); "
           "n=c.execute('select count(*) from t').fetchone()[0]; "
           "m=c.execute('select avg(v) from t').fetchone()[0]; "
           "json.dump({'n': n, 'mean_v': m}, open('%s/work/stats.json','w'))"
           % (w, w)],
   "produces": ["%s/work/stats.json" % w]},
  {"name": "G4_fill_result", "gate": "G4",
   "cmd": ["python3", "-c",
           "import json; s=json.load(open('%s/work/stats.json')); "
           "r=json.load(open('%s/output/result.json')); "
           "r.update({'analysis_result': 'synthetic table t has %%d rows, mean(v)=%%.2f' %% (s['n'], s['mean_v']), "
           "'evidence': 'stats.json', 'exceptions': 'none', 'status': 'complete', "
           "'limitations': 'synthetic demo only'}); "
           "json.dump(r, open('%s/output/result.json','w'), ensure_ascii=False, indent=1); "
           "open('%s/output/analysis_notes.md','w').write('# demo notes\\nsynthetic data')"
           % (w, w, w, w)],
   "produces": ["%s/output/analysis_notes.md" % w]}]}
json.dump(plan, open(w + '/work/plan.json', 'w'), indent=1)
print('synthetic case + plan written')
PY

python3 "$SKILL_DIR/scripts/bootstrap.py" --case "$WORK/input/case.json" --outdir "$WORK/output"
echo "--- gate run 1 (all steps) ---"
python3 "$SKILL_DIR/scripts/gate.py" --plan "$WORK/work/plan.json" \
  --state "$WORK/work/run_state.json" --logdir "$WORK/work/logs"
echo "--- gate run 2 (resume demo: all steps skipped) ---"
python3 "$SKILL_DIR/scripts/gate.py" --plan "$WORK/work/plan.json" \
  --state "$WORK/work/run_state.json" --logdir "$WORK/work/logs"
echo "--- selfcheck ---"
python3 "$SKILL_DIR/scripts/selfcheck.py" --case "$WORK/input/case.json" \
  --outdir "$WORK/output" --out "$WORK/work/selfcheck.json" --md "$WORK/work/selfcheck.md"
cat "$WORK/output/result.json"
