#!/bin/bash
# run_example.sh — 【合成示例】端到端演示（非正式案例结果）。
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
ROOT="${1:-$(mktemp -d /tmp/kbqa-render-demo.XXXXXX)}"
echo "== 合成示例根目录: $ROOT"
python3 "$HERE/make_fixture.py" "$ROOT"
mkdir -p "$ROOT/work" "$ROOT/output"
W="$ROOT/work"; O="$ROOT/output"; I="$ROOT/input"

echo "== 1) render_scan"
python3 "$SKILL/scripts/render_scan.py" --input "$I" --work "$W" --out "$O"

echo "== 2) 撰写 answers.json（示例内置合成内容，坐标取自真实编目）"
python3 - "$W" <<'PYEOF'
import json, sys
cat = json.load(open(sys.argv[1] + "/render_catalog.json"))
f1 = next(e for e in cat["files"] if e["file_id"] == "F001")
ans = {"answers": [{"question_id": "q1",
  "answer": "DEV-3 在 532 nm 激光下的响应度为 120 A/W。",
  "claims": [{"claim": "DEV-3 在 532 nm 下响应度为 120 A/W",
              "evidence": [{"file_id": "F001", "sha8": f1["sha256"][:8],
                            "line_start": 2, "line_end": 2,
                            "quote": "器件 DEV-3 在 532 nm 激光下的响应度为 120 A/W。"}]}],
  "uncertainty": []}]}
json.dump(ans, open(sys.argv[1] + "/answers.json", "w"), ensure_ascii=False, indent=2)
PYEOF

echo "== 3) render_kb"
python3 "$SKILL/scripts/render_kb.py" --work "$W" --out "$O"

echo "== 4) link_check"
python3 "$SKILL/scripts/link_check.py" --input "$I" --work "$W" --out "$O"

echo "== 反例演示：篡改答案卡引文 → 机检抓出"
sed -i '' 's/120 A\/W/999 A\/W/' "$O/handover/answers/q_q1.md" 2>/dev/null || true
python3 "$SKILL/scripts/link_check.py" --input "$I" --work "$W" --out "$O" | python3 -c "
import json,sys; d=json.load(sys.stdin); print('pass:',d['pass']); [print(' violation:',v) for v in d['violations'][:3]]"
# 还原（重渲染）
python3 "$SKILL/scripts/render_kb.py" --work "$W" --out "$O" >/dev/null
python3 "$SKILL/scripts/link_check.py" --input "$I" --work "$W" --out "$O"

echo "== handover 结构"; find "$O/handover" -type f | sort
echo "== knowledge_index.md"; cat "$O/handover/knowledge_index.md"
echo "== DONE (合成示例，输出为虚构数据)"
