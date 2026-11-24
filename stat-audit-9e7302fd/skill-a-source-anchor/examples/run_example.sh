#!/usr/bin/env bash
# run_example.sh — 端到端演示【合成示例】,非真实案件结果。
# 步骤: 1) 锚点化提取  2) 提取保真度门  3) 锚定核验门(预期 2 通过 / 1 拒绝)
# 用法: bash run_example.sh   (输出写入 examples/output/, 不覆盖 expected_output/)
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$DIR/.." && pwd)"
OUT="$DIR/output"
mkdir -p "$OUT"

echo "== [1/3] pdf_to_anchored_text: 提取并锚点化 =="
python3 "$SKILL_DIR/scripts/pdf_to_anchored_text.py" "$DIR/synthetic_paper.txt" \
    --text-out "$OUT/anchored.txt" \
    --anchors-out "$OUT/anchors.jsonl" \
    --raw-out "$OUT/raw.txt" || { echo "步骤1失败"; exit 1; }

echo "== [2/3] source_integrity: 提取保真度门(本示例预期 verdict=ok) =="
python3 "$SKILL_DIR/scripts/source_integrity.py" "$DIR/synthetic_paper.txt" \
    --out "$OUT/integrity_report.json"
INTEG_EXIT=$?
if [ "$INTEG_EXIT" -ne 0 ]; then
    echo "完整性判定为 failed(退出码 $INTEG_EXIT): 应走材料不足分支,终止示例。"
    exit 1
fi

echo "== [3/3] anchor_verify: 锚定核验门(本示例预期退出码 1: F-003 被拒绝) =="
python3 "$SKILL_DIR/scripts/anchor_verify.py" \
    --findings "$DIR/sample_findings.jsonl" \
    --raw "$OUT/raw.txt" \
    --anchors "$OUT/anchors.jsonl" \
    --out "$OUT/verified_findings.jsonl" \
    --rejects "$OUT/rejects.jsonl"
VERIFY_EXIT=$?

echo "----------------------------------------------------------"
echo "integrity 退出码 = $INTEG_EXIT (预期 0, verdict=ok)"
echo "anchor_verify 退出码 = $VERIFY_EXIT (预期 1: 1 条错误引用被拒绝)"
echo "产物: $OUT/{anchored.txt, anchors.jsonl, raw.txt, integrity_report.json, verified_findings.jsonl, rejects.jsonl}"
echo "参考输出(与本结果一致)见 $DIR/expected_output/"
exit 0
