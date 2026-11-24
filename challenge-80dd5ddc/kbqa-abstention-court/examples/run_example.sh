#!/bin/bash
# run_example.sh — 【合成示例】端到端演示（非正式案例结果）。
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
ROOT="${1:-$(mktemp -d /tmp/kbqa-court-demo.XXXXXX)}"
echo "== 合成示例根目录: $ROOT"
python3 "$HERE/make_fixture.py" "$ROOT"
mkdir -p "$ROOT/work" "$ROOT/output"

echo "== 1) suff_index"
python3 "$SKILL/scripts/suff_index.py" --input "$ROOT/input" --work "$ROOT/work" --out "$ROOT/output"
echo "== 2) suff_matrix"
python3 "$SKILL/scripts/suff_matrix.py" --work "$ROOT/work" --out "$ROOT/output"
echo "== 3) suff_conflict"
python3 "$SKILL/scripts/suff_conflict.py" --work "$ROOT/work" --out "$ROOT/output"

echo "== 4a) suff_verdict（纯机器裁决）"
python3 "$SKILL/scripts/suff_verdict.py" --work "$ROOT/work" --out "$ROOT/output"

echo "== 4b) 模型越级申报（q2 申报 L5，演示回降）"
cat > "$ROOT/work/model_verdicts.json" <<'EOF'
{"verdicts": [{"question_id": "q2", "level": 5, "reason": "演示越级申报"}]}
EOF
python3 "$SKILL/scripts/suff_verdict.py" --work "$ROOT/work" --out "$ROOT/output"

echo "== verdicts.json"
cat "$ROOT/output/verdicts.json"
echo "== result.json answers"
python3 -c "
import json; r=json.load(open('$ROOT/output/result.json'))
print(json.dumps(r['answers'],ensure_ascii=False,indent=1))
print('uncertainty:',json.dumps(r['uncertainty'],ensure_ascii=False))"
echo "== DONE (合成示例，输出为虚构数据)"
