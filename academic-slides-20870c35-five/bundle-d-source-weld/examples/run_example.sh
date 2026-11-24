#!/usr/bin/env bash
# run_example.sh — source-weld-verifier 合成示例全流程演示（SYNTHETIC EXAMPLE）。
# 串起 make_gamma_pdf -> source_index -> anchor_audit(good/bad)，
# 捕获并断言每步真实退出码与违例码，产物（纯文本日志）保留在
# examples/output_demo/，运行时生成的 PDF 在演示结束删除。
set +e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$HERE/.." && pwd)"
OUT="$HERE/output_demo"
WORK="$OUT/work"
mkdir -p "$WORK" "$OUT/good" "$OUT/bad"

echo "== 0. 生成合成 PDF（synthetic_note_gamma.pdf，matplotlib 单页） =="
python3 "$HERE/make_gamma_pdf.py"
GEN=$?
echo "make_gamma_pdf EXIT=$GEN"
if [ $GEN -ne 0 ]; then echo "PDF 生成失败，终止演示"; exit 2; fi

PASS=0; FAIL=0
declare -a SUMMARY
check() {  # $1=label $2=expected $3=actual
  if [ "$2" = "$3" ]; then PASS=$((PASS+1)); SUMMARY+=("OK   $1: EXPECTED=$2 ACTUAL=$3");
  else FAIL=$((FAIL+1)); SUMMARY+=("FAIL $1: EXPECTED=$2 ACTUAL=$3"); fi
}

echo; echo "== 1. source_index.py（两份 txt 走 direct-read，PDF 走 pdftotext 路径） =="
python3 "$SKILL_ROOT/scripts/source_index.py" \
  --materials "$HERE/materials" --out "$WORK/source_index.json"
SI=$?
echo "source_index EXIT=$SI"
check "source_index exit" 0 "$SI"

echo; echo "== 1b. 确认 PDF 解析方式如实记录在索引中 =="
PM=$(python3 - "$WORK/source_index.json" <<'EOF'
import json, sys
idx = json.load(open(sys.argv[1], encoding="utf-8"))
gam = [d for d in idx["docs"] if d["doc_id"] == "synthetic_note_gamma"]
print(gam[0]["parse_method"] if gam else "MISSING")
EOF
)
echo "synthetic_note_gamma parse_method=$PM"
case "$PM" in
  pdftotext-*) check "pdf parse_method recorded" "pdftotext-prefix" "pdftotext-prefix" ;;
  *)           check "pdf parse_method recorded" "pdftotext-prefix" "$PM" ;;
esac

echo; echo "== 2. anchor_audit.py @ claims_good.json（6 条全部应焊住） =="
python3 "$SKILL_ROOT/scripts/anchor_audit.py" \
  --claims "$HERE/claims_good.json" --index "$WORK/source_index.json" \
  --outdir "$OUT/good"
AG=$?
echo "anchor_audit good EXIT=$AG"
check "anchor_audit(good) exit" 0 "$AG"
GOOD_STATS=$(python3 - "$OUT/good/audit_report.json" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
print(f"{r['states']['verified']}/{r['total']}", r["linkage_rate"])
EOF
)
echo "good verified/linkage = $GOOD_STATS"
check "good 6/6 verified linkage 1.0" "6/6 1.0" "$GOOD_STATS"

echo; echo "== 3. anchor_audit.py @ claims_bad.json（5 个埋雷，门控应精确开火） =="
python3 "$SKILL_ROOT/scripts/anchor_audit.py" \
  --claims "$HERE/claims_bad.json" --index "$WORK/source_index.json" \
  --outdir "$OUT/bad"
AB=$?
echo "anchor_audit bad EXIT=$AB"
check "anchor_audit(bad) exit" 1 "$AB"
BAD_STATES=$(python3 - "$OUT/bad/audit_report.json" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
m = {x["claim_id"]: x["state"] for x in r["results"]}
print(",".join(f"{k}={m.get(k)}" for k in ("b1", "b2", "b3", "b4", "b5")))
EOF
)
echo "bad states = $BAD_STATES"
EXPECTED_BAD="b1=not_verbatim,b2=page_mismatch,b3=number_not_in_source,b4=strength_overclaim,b5=doc_missing"
check "bad five planted codes" "$EXPECTED_BAD" "$BAD_STATES"

# 清理运行时生成的二进制 PDF：bundle 交付约束为纯 UTF-8 文本，
# synthetic_note_gamma.pdf 每次演示由 make_gamma_pdf.py 重新生成。
rm -f "$HERE/materials/synthetic_note_gamma.pdf"
echo "已清理运行时生成的 synthetic_note_gamma.pdf（纯文本交付约束）"

echo; echo "================= EXPECTED vs ACTUAL ================="
for line in "${SUMMARY[@]}"; do echo "  $line"; done
echo "产物目录: $OUT"
echo "  源索引:        $WORK/source_index.json"
echo "  审计报告(good): $OUT/good/audit_report.json"
echo "  审计报告(bad):  $OUT/bad/audit_report.json"
if [ $FAIL -gt 0 ]; then echo "RESULT: $FAIL 项不符合预期"; exit 1; fi
echo "ALL EXPECTATIONS MET（$PASS 项全部符合预期，含 bad 集门控开火 exit 1）"
exit 0
