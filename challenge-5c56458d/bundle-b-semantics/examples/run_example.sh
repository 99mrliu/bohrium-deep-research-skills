#!/bin/sh
# 合成示例（synthetic demo, NOT a formal case result）：
# 自建含编码列/近义状态列/0与NULL 的合成库 + 合成任务文本，
# 跑 profile_fields -> build_dictionary -> resolve_caliber。
set -eu
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d /tmp/caliber-demo.XXXXXX)"
echo "demo workspace: $WORK"

python3 - "$WORK" <<'PY'
import sqlite3, sys, random
random.seed(11)
db = sys.argv[1] + '/lab.db'
con = sqlite3.connect(db)
con.execute('''CREATE TABLE assay (
  sample_id TEXT, class INTEGER, alcohol REAL, additive REAL,
  sample_status TEXT, experiment_status TEXT)''')
rows = []
for i in range(120):
    cls = [1,2,3][i % 3]
    additive = None if i % 17 == 0 else (0.0 if i % 4 == 0 else round(random.uniform(1,9),2))
    rows.append(('S%04d' % i, cls, round(random.uniform(11,15),2), additive,
                 ['ok','hemolyzed'][i % 9 == 0 and 1 or 0],
                 ['finished','aborted'][i % 13 == 0 and 1 or 0]))
con.executemany('INSERT INTO assay VALUES (?,?,?,?,?,?)', rows)
con.commit(); con.close()
open(sys.argv[1] + '/task.md','w').write('按 class 分组统计 alcohol 的平均值与样本数，只看 experiment_status 为 finished 的记录。')
print('synthetic db + task written')
PY

python3 "$SKILL_DIR/scripts/profile_fields.py" --db "$WORK/lab.db" --out "$WORK/field_profile.json"
python3 "$SKILL_DIR/scripts/build_dictionary.py" --profile "$WORK/field_profile.json" \
  --pack "$SKILL_DIR/references/semantics_pack.json" \
  --out "$WORK/data_dictionary.json" --md "$WORK/data_dictionary.md"
python3 "$SKILL_DIR/scripts/resolve_caliber.py" --task-file "$WORK/task.md" \
  --dictionary "$WORK/data_dictionary.json" --out "$WORK/caliber.json" --md "$WORK/caliber.md"
echo "--- caliber.md ---"
cat "$WORK/caliber.md"
