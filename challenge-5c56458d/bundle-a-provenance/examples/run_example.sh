#!/bin/sh
# 合成示例（synthetic demo, NOT a formal case result）：
# 自建一个 iris 形态、但 sepal_width 被放大 1.1 倍的 SQLite 库，
# 跑 fingerprint -> verify，期望得到 DRIFT 判定。
set -eu
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d /tmp/veritas-demo.XXXXXX)"
echo "demo workspace: $WORK"

python3 - "$WORK" <<'PY'
import sqlite3, sys, random
random.seed(7)
db = sys.argv[1] + '/lab.db'
con = sqlite3.connect(db)
con.execute('CREATE TABLE flowers (sepal_length REAL, sepal_width REAL, petal_length REAL, petal_width REAL, species TEXT)')
species = ['Iris-setosa','Iris-versicolor','Iris-virginica']
rows = []
for i in range(150):
    sp = species[i // 50]
    base = i // 50
    rows.append((round(5.0 + base*0.9 + random.uniform(-0.4,0.4),1),
                 round((3.4 - base*0.3 + random.uniform(-0.3,0.3))*1.1, 2),  # tampered column
                 round(1.5 + base*2.0 + random.uniform(-0.5,0.5),1),
                 round(0.2 + base*0.9 + random.uniform(-0.2,0.2),1), sp))
con.executemany('INSERT INTO flowers VALUES (?,?,?,?,?)', rows)
con.commit(); con.close()
print('synthetic db written:', db)
PY

python3 "$SKILL_DIR/scripts/fingerprint.py" --db "$WORK/lab.db" --out "$WORK/fingerprint.json"
python3 "$SKILL_DIR/scripts/verify_snapshot.py" --fingerprint "$WORK/fingerprint.json" \
  --cards "$SKILL_DIR/references/reference_cards.json" \
  --out "$WORK/verdict.json" --md "$WORK/verdict.md"
echo "--- verdict.md ---"
cat "$WORK/verdict.md"
