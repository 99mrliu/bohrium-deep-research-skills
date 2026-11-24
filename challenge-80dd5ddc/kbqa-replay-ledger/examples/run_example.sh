#!/bin/bash
# run_example.sh — 【合成示例】端到端演示（非正式案例结果）。
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
ROOT="${1:-$(mktemp -d /tmp/kbqa-ledger-demo.XXXXXX)}"
echo "== 合成示例根目录: $ROOT"
python3 "$HERE/make_fixture.py" "$ROOT"
mkdir -p "$ROOT/work" "$ROOT/output"
W="$ROOT/work"; O="$ROOT/output"; I="$ROOT/input"

echo "== 0) init + 骨架 result.json（合成内容）"
python3 "$SKILL/scripts/oplog.py" init --work "$W"
python3 - "$I" "$O" <<'PYEOF'
import json, sys
case = json.load(open(sys.argv[1] + "/case.json"))
skel = {"case_id": case["case_id"], "status": "partial",
        "answers": [{"question_id": "q1", "answer": None, "state": "pending"}],
        "sources": [], "uncertainty": ["skeleton at init"], "change_log": []}
for f in case["output_contract"]["fields"]:
    skel.setdefault(f, None)
json.dump(skel, open(sys.argv[2] + "/result.json", "w"), ensure_ascii=False, indent=2)
PYEOF

echo "== 1) 过程留痕（scan/search/read/decide/verify）"
python3 "$SKILL/scripts/oplog.py" append --work "$W" --op scan \
    --detail '{"files": 2, "all_readable": true}'
python3 "$SKILL/scripts/oplog.py" append --work "$W" --op search \
    --detail '{"query": "BAT-11 首次库仑效率", "hits": 1}'
python3 "$SKILL/scripts/oplog.py" append --work "$W" --op read \
    --file "$I/docs/bat11_notes.txt"
python3 "$SKILL/scripts/oplog.py" append --work "$W" --op read \
    --file "$I/docs/bat11_cycle.txt"
python3 "$SKILL/scripts/oplog.py" append --work "$W" --op decide \
    --detail '{"conclusion": "q1=89.3%, 来源 bat11_notes.txt L2"}'
python3 "$SKILL/scripts/oplog.py" append --work "$W" --op verify \
    --detail '{"manual_check": "quote verified against file"}'

echo "== 2) 写正式 result.json（合成内容）→ seal → audit → selfcheck → replay"
python3 - "$I" "$O" <<'PYEOF'
import json, sys
case = json.load(open(sys.argv[1] + "/case.json"))
r = {"case_id": case["case_id"], "status": "completed",
     "answers": [{"question_id": "q1",
                  "answer": "BAT-11 的首次库仑效率为 89.3%（docs/bat11_notes.txt 第 2 行）。",
                  "state": "answered"}],
     "sources": [{"relpath": "docs/bat11_notes.txt"}],
     "uncertainty": [], "change_log": [{"event": "finalized after audit"}]}
json.dump(r, open(sys.argv[2] + "/result.json", "w"), ensure_ascii=False, indent=2)
PYEOF
python3 "$SKILL/scripts/oplog.py" seal --work "$W"
python3 "$SKILL/scripts/journal_audit.py" --input "$I" --work "$W" --out "$O"
python3 "$SKILL/scripts/selfcheck.py" --input "$I" --work "$W" --out "$O"
python3 "$SKILL/scripts/replay_pack.py" --work "$W" --out "$O"

echo "== 3) 反例演示：seal 后追加日志 → 审计标记 post_seal"
python3 "$SKILL/scripts/oplog.py" append --work "$W" --op note --detail '{"demo": "post seal"}'
python3 "$SKILL/scripts/journal_audit.py" --input "$I" --work "$W" --out "$O" | python3 -c "
import json,sys; d=json.load(sys.stdin); print('pass:',d['pass'],'issues:',d['issues'])"

echo "== 产物清单"; find "$O" -type f | sort
echo "== DONE (合成示例，输出为虚构数据)"
