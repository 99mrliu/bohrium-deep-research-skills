#!/usr/bin/env bash
# run_example.sh — dr-source-veritas 合成示例全流程演示（synthetic demo）。
# 串起 corpus_build -> quote_verify(good/bad) -> refcheck，
# 捕获并打印每步真实退出码，汇总 EXPECTED vs ACTUAL。
# 全部材料与产物为合成示例，产物保留在 examples/output_demo/。
set +e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$HERE/.." && pwd)"
OUT="$HERE/output_demo"
WORK="$OUT/work"

echo "== 0. 生成合成 PDF（paper_gamma.pdf，matplotlib 单页） =="
python3 "$HERE/make_gamma_pdf.py"
GEN=$?
echo "make_gamma_pdf.py EXIT=$GEN"
if [ $GEN -ne 0 ]; then echo "PDF 生成失败，终止演示"; exit 2; fi

PASS=0; FAIL=0
declare -a SUMMARY
check() {  # $1=label $2=expected $3=actual
  if [ "$2" = "$3" ]; then PASS=$((PASS+1)); SUMMARY+=("OK   $1: EXPECTED=$2 ACTUAL=$3");
  else FAIL=$((FAIL+1)); SUMMARY+=("FAIL $1: EXPECTED=$2 ACTUAL=$3"); fi
}

echo; echo "== 1. corpus_build.py（构建语料，PDF 走 pdftotext 路径） =="
python3 "$SKILL_ROOT/scripts/corpus_build.py" \
  --materials "$HERE/materials" --workdir "$WORK"
CB=$?
echo "corpus_build EXIT=$CB"
check "corpus_build" 0 "$CB"

echo; echo "== 2. quote_verify.py @ good_ledger.jsonl（6 条全部逐字，应通过） =="
mkdir -p "$OUT/good"
python3 "$SKILL_ROOT/scripts/quote_verify.py" \
  --ledger "$HERE/good_ledger.jsonl" --corpus "$WORK/corpus" \
  --outdir "$OUT/good"
QG=$?
echo "quote_verify good EXIT=$QG"
check "quote_verify(good)" 0 "$QG"

echo; echo "== 3. quote_verify.py @ bad_ledger.jsonl（3 个埋雷，门控应开火） =="
mkdir -p "$OUT/bad"
python3 "$SKILL_ROOT/scripts/quote_verify.py" \
  --ledger "$HERE/bad_ledger.jsonl" --corpus "$WORK/corpus" \
  --outdir "$OUT/bad"
QB=$?
echo "quote_verify bad EXIT=$QB"
check "quote_verify(bad)" 1 "$QB"

echo; echo "== 4. refcheck.py @ references.json（幻影 + malformed DOI，门控应开火） =="
python3 "$SKILL_ROOT/scripts/refcheck.py" \
  --refs "$HERE/references.json" --corpus "$WORK/corpus" \
  --outdir "$OUT"
RC=$?
echo "refcheck EXIT=$RC"
check "refcheck" 1 "$RC"

# 清理运行时生成的二进制 PDF：平台 Skill 资源约束为纯 UTF-8 文本，paper_gamma.pdf
# 属运行时产物（每次演示由 make_gamma_pdf.py 重新生成），不随 bundle 交付。
rm -f "$HERE/materials/paper_gamma.pdf"
echo "已清理运行时生成的 paper_gamma.pdf（纯文本交付约束）"

echo; echo "================= EXPECTED vs ACTUAL ================="
for line in "${SUMMARY[@]}"; do echo "  $line"; done
echo "产物目录: $OUT"
echo "  语料索引:      $WORK/corpus/corpus_index.json"
echo "  身份候选:      $WORK/corpus/identity_candidates.json"
echo "  回链报告(good): $OUT/good/linkage_report.json"
echo "  回链报告(bad):  $OUT/bad/linkage_report.json"
echo "  身份核验报告:   $OUT/refcheck_report.json"
if [ $FAIL -gt 0 ]; then echo "RESULT: $FAIL 项不符合预期"; exit 1; fi
echo "RESULT: 全部 $PASS 项符合预期（含两处门控开火 exit 1）"
exit 0
