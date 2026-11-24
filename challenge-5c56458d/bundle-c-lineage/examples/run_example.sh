#!/bin/sh
# 合成示例（synthetic demo, NOT a formal case result）：
# 自建含 NULL 与重复键的合成库，跑 lineage_export -> recompute。
set -eu
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d /tmp/lineage-demo.XXXXXX)"
echo "demo workspace: $WORK"

python3 - "$WORK" <<'PY'
import sqlite3, json, sys, random
random.seed(3)
db = sys.argv[1] + '/lab.db'
con = sqlite3.connect(db)
con.execute('CREATE TABLE measurements (sample_id TEXT, group_id TEXT, metric REAL)')
rows = []
for i in range(60):
    g = ['control','treat_a','treat_b'][i % 3]
    m = None if i == 7 else round(random.uniform(5, 25), 3)
    rows.append(('S%03d' % i, g, m))
rows.append(('S000', 'control', 99.9))  # deliberate duplicate key
con.executemany('INSERT INTO measurements VALUES (?,?,?)', rows)
con.commit(); con.close()
spec = {"table": "measurements", "key": "sample_id", "group_by": ["group_id"],
        "aggregates": [{"func": "COUNT", "column": "*", "as": "n"},
                       {"func": "AVG", "column": "metric", "as": "mean_metric"}],
        "where": "metric IS NOT NULL"}
json.dump(spec, open(sys.argv[1] + '/spec.json', 'w'), indent=1)
print('synthetic db + spec written')
PY

python3 "$SKILL_DIR/scripts/lineage_export.py" --db "$WORK/lab.db" \
  --spec "$WORK/spec.json" --tag q1 --outdir "$WORK"
python3 "$SKILL_DIR/scripts/recompute.py" --db "$WORK/lab.db" --tag q1 --outdir "$WORK"
echo "--- q1.csv ---"; cat "$WORK/q1.csv"
echo "--- first lineage record ---"; head -1 "$WORK/q1.lineage.jsonl" | cut -c1-200
echo "--- recompute ---"; cat "$WORK/q1.recompute.json"
