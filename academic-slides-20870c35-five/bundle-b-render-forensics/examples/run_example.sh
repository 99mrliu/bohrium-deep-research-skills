#!/usr/bin/env bash
# SYNTHETIC EXAMPLE / 合成示例 —— export-render-forensics 一键演示。
# 从 bundle 根目录运行：bash examples/run_example.sh
# 用 set +e 捕获每步真实退出码，末尾汇总 EXPECTED vs ACTUAL，全部一致则整体 exit 0。
# 演示生成的 .pdf/.pptx/.ppm/.png 二进制在结尾全部删除，仅保留文本日志与 JSON 报告。
set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RENDER_QA="$BUNDLE_DIR/scripts/render_qa.py"
MINIPPTX="$BUNDLE_DIR/scripts/minipptx.py"
FIXTURES="$SCRIPT_DIR/make_fixtures.py"
EXPECT_GOOD="$SCRIPT_DIR/expectations.json"
DECK_SPEC="$SCRIPT_DIR/deck_spec.json"
OUT="$SCRIPT_DIR/output_demo"

LINES=()
record() { LINES+=("step=$1 | expected=$2 | actual=$3 | $4"); }
step()   { echo; echo "===== $* ====="; }

step "0. 清理并重建 output_demo"
: "${OUT:?OUT 为空，拒绝删除}"
case "$OUT" in
  *examples/output_demo) ;;
  *) echo "OUT 路径异常，拒绝删除：$OUT"; exit 2 ;;
esac
rm -rf "$OUT"
mkdir -p "$OUT"
echo "OUT=$OUT"

step "1. make_fixtures（matplotlib 现场生成 good.pdf / bad.pdf / 插图 PNG，期望 exit 0）"
python3 "$FIXTURES" 2>&1 | tee "$OUT/fixtures.log"
ec=${PIPESTATUS[0]}; record 1 0 "$ec" "make_fixtures"
for f in good.pdf bad.pdf synthetic_figure.png; do
  if [ -f "$OUT/$f" ]; then record "1-$f" present present "夹具已生成"; else record "1-$f" present MISSING "夹具缺失"; fi
done

step "2. render_qa good.pdf（期望 exit 0，全门 PASS）"
python3 "$RENDER_QA" "$OUT/good.pdf" "$EXPECT_GOOD" \
  -o "$OUT/render_report_good.json" 2>&1 | tee "$OUT/render_qa_good.log"
ec=${PIPESTATUS[0]}; record 2 0 "$ec" "render_qa good"

step "3. render_qa bad.pdf（期望 exit 1，精确命中 R1..R5）"
# bad 期望：页数仍期望 4（实际 5 -> R1），期望图页为第 5 页（仅剩图题 -> R5）
cat > "$OUT/expectations_bad.json" <<'JSON'
{
  "_notice": "SYNTHETIC EXAMPLE: derived by run_example.sh for bad.pdf",
  "page_count": 4,
  "footer_zone_fraction": 0.08,
  "min_text_height_pt": 10.0,
  "expected_figure_pages": [5],
  "blank_ink_threshold": 0.001,
  "figure_ink_threshold": 0.02,
  "content_margin_fraction": 0.05,
  "ink_pixel_threshold": 240,
  "render_dpi": 72,
  "eps_pt": 0.5,
  "min_words_for_height_check": 3
}
JSON
python3 "$RENDER_QA" "$OUT/bad.pdf" "$OUT/expectations_bad.json" \
  -o "$OUT/render_report_bad.json" > "$OUT/render_qa_bad.log" 2>&1
ec=$?
cat "$OUT/render_qa_bad.log"
record 3 1 "$ec" "render_qa bad"
for code in R1 R2 R3 R4 R5; do
  if grep -q "^$code: " "$OUT/render_qa_bad.log"; then
    record "3-$code" fired fired "bad 命中 $code"
  else
    record "3-$code" fired MISSING "bad 未命中 $code"
  fi
done

step "4. minipptx build（期望 exit 0，产物可重建打开）"
python3 "$MINIPPTX" build "$DECK_SPEC" -o "$OUT/demo_deck.pptx" 2>&1 | tee "$OUT/minipptx_build.log"
ec=${PIPESTATUS[0]}; record 4 0 "$ec" "minipptx build"
if [ -f "$OUT/demo_deck.pptx" ]; then record "4-pptx" present present "pptx 已生成"; else record "4-pptx" present MISSING "pptx 缺失"; fi

step "5. minipptx verify（期望 exit 0）"
python3 "$MINIPPTX" verify "$OUT/demo_deck.pptx" 2>&1 | tee "$OUT/minipptx_verify.log"
ec=${PIPESTATUS[0]}; record 5 0 "$ec" "minipptx verify"

step "6. 删除演示二进制（.pdf/.pptx/.ppm/.png），保留文本日志与 JSON 报告"
rm -f "$OUT"/*.pdf "$OUT"/*.pptx "$OUT"/*.ppm "$OUT"/*.png
leftover=$(ls "$OUT" | grep -E '\.(pdf|pptx|ppm|png)$' || true)
if [ -z "$leftover" ]; then record 6 clean clean "二进制已清理"; else record 6 clean "LEFTOVER:$leftover" "二进制残留"; fi

echo
echo "================ 汇总 EXPECTED vs ACTUAL ================"
fail=0
for line in "${LINES[@]}"; do
  echo "$line"
  rest="${line#*expected=}"; exp="${rest%% *}"
  rest="${line#*actual=}";   act="${rest%% *}"
  if [ "$exp" != "$act" ]; then fail=1; fi
done
echo "========================================================"
if [ "$fail" -eq 0 ]; then
  echo "ALL EXPECTATIONS MET"
  exit 0
else
  echo "EXPECTATION MISMATCH"
  exit 1
fi
