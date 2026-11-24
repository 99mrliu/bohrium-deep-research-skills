#!/usr/bin/env bash
# run_example.sh — bundle C 端到端自测（合成示例，非真实数据）。
# (a) 生成合成数据 → pipeline run → figure_forge --force-svg → 断言 SVG 生成、签名有效、图注含每组 n
# (b) figure_audit 好例 → 断言 exit 0
# (c) 埋雷三连：删图 → MISSING_FIGURE；篡改图注 n → CAPTION_NUMBER_MISMATCH；
#     塞入 n<30 均值条形图声明 → RULE_VIOLATION_BAR；各断言 exit 1 且命中违例码
# (d) 若本机有 matplotlib，再验证一次 PNG 通道（产物验证后删除，不入库）
# 全部断言通过才 exit 0。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$(dirname "$HERE")/scripts"
TMP="$(mktemp -d /tmp/figforge_example.XXXXXX)"
fail() { echo "EXAMPLE CHECK FAILED: $*" >&2; exit 1; }

echo "== [1/6] 生成合成示例数据 =="
python3 "$HERE/make_synthetic.py" --out "$TMP/input" >/dev/null
mkdir -p "$TMP/work" "$TMP/output"

echo "== [2/6] pipeline run（一键 baseline）=="
python3 "$SCRIPTS/pipeline_c.py" run --input "$TMP/input" --work "$TMP/work" --output "$TMP/output" >/dev/null
python3 -m json.tool "$TMP/output/result.json" >/dev/null || fail "result.json 非法 JSON"
python3 - <<PYEOF
import json
r = json.load(open("$TMP/output/result.json"))
need = ["case_id","status","cleaning","descriptive","hypothesis_test","effect_size",
        "confidence_interval","interpretation","limitations"]
assert all(k in r for k in need), "result.json 缺契约字段"
assert r["status"] == "ok", "status != ok"
assert len(r["hypothesis_test"]["analyses"]) >= 1, "无分析"
PYEOF

echo "== [3/6] figure_forge --force-svg（SVG 兜底通道）=="
python3 "$SCRIPTS/figure_forge.py" --work "$TMP/work" --output "$TMP/output" --force-svg >/dev/null
SVG_COUNT=$(ls "$TMP"/output/fig*.svg 2>/dev/null | wc -l | tr -d ' ')
[ "$SVG_COUNT" -ge 1 ] || fail "未生成 SVG"
for f in "$TMP"/output/fig*.svg; do
  head -c 300 "$f" | grep -q '<svg' || fail "$f 缺少 <svg 根元素（签名无效）"
done
grep -q 'n=8'  "$TMP/output/figures.md" || fail "图注缺 control n=8"
grep -q 'n=9'  "$TMP/output/figures.md" || fail "图注缺 treatA n=9"
grep -q 'n=10' "$TMP/output/figures.md" || fail "图注缺 treatB n=10"
grep -q 'ms'   "$TMP/output/figures.md" || fail "图注缺单位 ms"
echo "   SVG $SVG_COUNT 张，签名有效，图注含每组 n 与单位 ✓"

echo "== [4/6] figure_audit 好例 → 期望 exit 0 =="
set +e
python3 "$SCRIPTS/figure_audit.py" --output-dir "$TMP/output" --result "$TMP/output/result.json" > "$TMP/audit_pass.log" 2>&1
rc=$?
set -e
[ $rc -eq 0 ] || { cat "$TMP/audit_pass.log"; fail "好例 audit 未通过"; }
grep -q 'AUDIT PASS' "$TMP/audit_pass.log" || fail "好例无 AUDIT PASS 字样"

echo "== [5/6] 埋雷三连 → 期望各自 exit 1 且命中违例码 =="
# 雷 1：删掉一张被引用的图
cp -r "$TMP/output" "$TMP/outA"
rm "$TMP/outA/fig1.svg"
set +e
OUT=$(python3 "$SCRIPTS/figure_audit.py" --output-dir "$TMP/outA" --result "$TMP/outA/result.json" 2>&1)
rc=$?
set -e
[ $rc -eq 1 ] || fail "雷1 未 exit 1"
echo "$OUT" | grep -q 'MISSING_FIGURE' || fail "雷1 未命中 MISSING_FIGURE"
echo "   雷1: exit 1 + MISSING_FIGURE ✓"

# 雷 2：篡改 figures.md 中某组 n
cp -r "$TMP/output" "$TMP/outB"
sed -i.bak 's/n=8/n=80/' "$TMP/outB/figures.md" && rm -f "$TMP/outB/figures.md.bak"
set +e
OUT=$(python3 "$SCRIPTS/figure_audit.py" --output-dir "$TMP/outB" --result "$TMP/outB/result.json" 2>&1)
rc=$?
set -e
[ $rc -eq 1 ] || fail "雷2 未 exit 1"
echo "$OUT" | grep -q 'CAPTION_NUMBER_MISMATCH' || fail "雷2 未命中 CAPTION_NUMBER_MISMATCH"
echo "   雷2: exit 1 + CAPTION_NUMBER_MISMATCH ✓"

# 雷 3：塞入一张 n<30 的 bar 图声明（dynamite plot）
cp -r "$TMP/output" "$TMP/outC"
cp "$TMP/outC/fig1.svg" "$TMP/outC/fig_bar.svg"
cat >> "$TMP/outC/figures.md" <<'EOF'

## fig_bar — fig_bar.svg
- file: fig_bar.svg
- channel: svg
- type: bar_se
- analyses: a1
- rationale: 人工补画的均值+SE 条形图（违例演示）
- caption: 图X｜均值条形图｜组 control：n=8，均值=10.00，SD=1.00；组 treatA：n=9，均值=12.00，SD=1.10；组 treatB：n=10，均值=13.50，SD=2.30
- data_range: [8.00, 16.00]
EOF
set +e
OUT=$(python3 "$SCRIPTS/figure_audit.py" --output-dir "$TMP/outC" --result "$TMP/outC/result.json" 2>&1)
rc=$?
set -e
[ $rc -eq 1 ] || fail "雷3 未 exit 1"
echo "$OUT" | grep -q 'RULE_VIOLATION_BAR' || fail "雷3 未命中 RULE_VIOLATION_BAR"
echo "   雷3: exit 1 + RULE_VIOLATION_BAR ✓"

echo "== [6/6] 可选：PNG 通道验证（有 matplotlib 才跑，产物删除不入库）=="
if python3 -c "import matplotlib" 2>/dev/null; then
  mkdir -p "$TMP/outP"
  cp "$TMP/output/result.json" "$TMP/output/report.md" "$TMP/outP/"
  python3 "$SCRIPTS/figure_forge.py" --work "$TMP/work" --output "$TMP/outP" --force-png >/dev/null
  python3 "$SCRIPTS/figure_audit.py" --output-dir "$TMP/outP" --result "$TMP/outP/result.json" >/dev/null || fail "PNG 通道 audit 未通过"
  python3 - <<PYEOF
import glob, struct
pngs = sorted(glob.glob("$TMP/outP/fig*.png"))
assert pngs, "PNG 通道无产物"
for p in pngs:
    raw = open(p, "rb").read()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", p + " magic bytes 错"
    w, h = struct.unpack(">II", raw[16:24])
    assert w >= 100 and h >= 100, p + " 尺寸非平凡失败"
print("   PNG 通道 %d 张，magic bytes + IHDR 尺寸有效 ✓" % len(pngs))
PYEOF
  rm -rf "$TMP/outP"
  echo "   PNG 产物已删除（不入库）✓"
else
  echo "   本机无 matplotlib，跳过 PNG 通道（SVG 兜底已验证）"
fi

# 真实文本产物入库（仅 json/md/svg/log；PNG 永不入库）
rm -rf "$HERE/example_output"
mkdir -p "$HERE/example_output"
cp "$TMP/output/result.json" "$TMP/output/report.md" "$TMP/output/figures.md" "$HERE/example_output/"
cp "$TMP/work/digest.md" "$HERE/example_output/"
cp "$TMP"/output/fig*.svg "$HERE/example_output/"
cp "$TMP/audit_pass.log" "$HERE/example_output/"
rm -rf "$TMP"
echo "RUN_EXAMPLE ALL CHECKS PASSED"
