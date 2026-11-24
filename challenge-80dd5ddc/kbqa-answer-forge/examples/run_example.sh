#!/bin/bash
# run_example.sh — 【合成示例】端到端演示（非正式案例结果）。
# 用法：bash examples/run_example.sh [临时根目录]
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
ROOT="${1:-$(mktemp -d /tmp/kbqa-forge-demo.XXXXXX)}"
echo "== 合成示例根目录: $ROOT"
python3 "$HERE/make_fixture.py" "$ROOT"
mkdir -p "$ROOT/work" "$ROOT/output"

echo "== 1) qa_init"
python3 "$SKILL/scripts/qa_init.py" --input "$ROOT/input" --work "$ROOT/work" --out "$ROOT/output"

echo "== 2) qa_retrieve (q1 命中 / q2 阴性)"
python3 "$SKILL/scripts/qa_retrieve.py" --work "$ROOT/work" --question-id q1 \
    --query "60 摄氏度 界面阻抗" --top 3 | head -30
python3 "$SKILL/scripts/qa_retrieve.py" --work "$ROOT/work" --question-id q2 \
    --query "循环伏安 扫描速率" --top 3 | head -8

echo "== 3) 撰写 citations/answers（示例内置合成内容）并核验"
cat > "$ROOT/work/citations.jsonl" <<'EOF'
{"citation_id": "c1", "claim_id": "q1-c1", "file_id": "F003", "sha8": "PLACEHOLDER", "line_start": 4, "line_end": 4, "quote": "60 摄氏度下界面阻抗降至 45 Ω·cm²。"}
EOF
# 用真实 sha8 替换占位符（演示版本坐标核验）
SHA8=$(python3 -c "
import json
d=json.load(open('$ROOT/work/kb_index.json'))
e=[x for x in d['files'] if x['file_id']=='F003'][0]
print(e['sha256'][:8])")
sed -i '' "s/PLACEHOLDER/$SHA8/" "$ROOT/work/citations.jsonl"
cat > "$ROOT/work/answers.json" <<'EOF'
{"answers": [
  {"question_id": "q1", "answer": "60 摄氏度下界面阻抗降至 45 Ω·cm²。",
   "claims": [{"claim_id": "q1-c1", "claim": "60 摄氏度下界面阻抗为 45 Ω·cm²",
               "evidence": [{"citation_id": "c1", "file_id": "F003",
                             "line_start": 4, "line_end": 4,
                             "quote": "60 摄氏度下界面阻抗降至 45 Ω·cm²。"}],
               "paraphrase": false}]},
  {"question_id": "q2", "answer": "库中无依据：备忘录仅注明循环伏安数据尚未整理入库。",
   "claims": []}
]}
EOF
# answers.json 中 evidence 需要 citation_id 与 citations.jsonl 对应；sha8 由核验脚本裁定
python3 "$SKILL/scripts/qa_verify.py" --work "$ROOT/work" --out "$ROOT/output" \
    --citations "$ROOT/work/citations.jsonl"

echo "== 4) qa_finalize"
python3 "$SKILL/scripts/qa_finalize.py" --input "$ROOT/input" --work "$ROOT/work" --out "$ROOT/output"

echo "== result.json"
cat "$ROOT/output/result.json"
echo "== DONE (合成示例，输出为虚构数据)"
