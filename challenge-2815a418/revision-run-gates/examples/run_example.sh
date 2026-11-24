#!/usr/bin/env bash
# run_example.sh — 合成示例，非正式案例结果。
# 演示完整受控流程：
#   run（停在 decisions 门）→ status → 拷入示例判断文件 → mark 自动跑完
#   → 再跑两次证明幂等跳过且产物一致 → 负例（坏锚点）验证 qc/finalize 报错。
# 产物到 examples/output/ 与 examples/work/。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(dirname "$HERE")"
PY=python3
RG="$BUNDLE/scripts/run_gates.py"
FZ="$BUNDLE/scripts/finalize.py"
IN="$HERE/case"
WORK="$HERE/work"
OUT="$HERE/output"
FAIL=0
ok(){ if [ "$1" -eq 0 ]; then echo "[OK] $2"; else echo "[FAIL] $2"; FAIL=1; fi }
md5q(){ md5 -q "$1" 2>/dev/null || md5sum "$1" | cut -d' ' -f1; }

echo "### 合成示例，非正式案例结果 ###"
echo "== 0. 清理旧产物 =="
rm -rf "$WORK" "$OUT" "$HERE/work_neg" "$HERE/output_neg" \
       "$HERE/neg_mark.log" "$HERE/neg_finalize.log" "$HERE"/.*.log

echo "== 1. 第一次 run：应停在 decisions 门，且 result.json 已合法（partial）=="
$PY "$RG" run --input "$IN" --work "$WORK" --output "$OUT" | tee "$HERE/.gate.log"
grep -q "GATE-STOP decisions" "$HERE/.gate.log"; ok $? "第一次 run 停在 decisions 门（GATE-STOP）"
$PY - "$OUT/result.json" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
assert r["case_id"] == "SYNTH-EXAMPLE-ONLY-004", r["case_id"]
assert r["status"] == "partial", r["status"]
for f in ["revised_manuscript", "response_letter", "change_locations", "evidence_checklist"]:
    assert f in r, f
print("result.json: case_id 正确、status=partial、4 个契约字段齐全（早落盘）")
EOF
ok $? "门停下时 result.json 已合法（partial 骨架）"

echo "== 2. status：decisions 及之后应 PENDING =="
$PY "$RG" status --input "$IN" --work "$WORK" --output "$OUT" | tee "$HERE/.status.log"
grep -qE "decisions +PENDING" "$HERE/.status.log"; ok $? "status 显示 decisions PENDING（人判门）"

echo "== 3. 拷入示例判断文件并 mark：应自动跑完且 finalize OK =="
cp "$HERE/decisions.json" "$WORK/decisions.json"
cp "$HERE/edits.json" "$WORK/edits.json"
$PY "$RG" mark --input "$IN" --work "$WORK" --output "$OUT" | tee "$HERE/.mark.log"
RC=${PIPESTATUS[0]}
grep -q "FINALIZE-OK" "$HERE/.mark.log"; ok $? "finalize 通过（FINALIZE-OK）"
[ "$RC" -eq 0 ]; ok $? "mark 退出码为 0"
$PY - "$WORK" "$OUT" <<'EOF'
import json, os, sys
work, out = sys.argv[1], sys.argv[2]
r = json.load(open(os.path.join(out, "result.json"), encoding="utf-8"))
assert r["status"] == "partial", r["status"]  # 2.1 无法补做 → 诚实 partial
assert any("2.1" in u for u in r["uncertainty"]), r["uncertainty"]
for f in ["revised_manuscript", "response_letter", "change_locations", "evidence_checklist"]:
    assert os.path.exists(os.path.join(out, r[f])), r[f]
q = json.load(open(os.path.join(work, "qc_report.json"), encoding="utf-8"))
assert q["overall"] == "pass", q["overall"]
print("status=partial（uncertainty 含 2.1 无法补做），4 个产物真实存在，QC overall=pass")
EOF
ok $? "mark 后 result.json 为诚实 partial、产物齐全、QC 通过"

echo "== 4. 重复 run：应全部 SKIP 且三次产物一致 =="
H1=$(md5q "$OUT/result.json")
$PY "$RG" run --input "$IN" --work "$WORK" --output "$OUT" | tee "$HERE/.rerun1.log" >/dev/null
N1=$(grep -c "\[SKIP\]" "$HERE/.rerun1.log")
H2=$(md5q "$OUT/result.json")
$PY "$RG" run --input "$IN" --work "$WORK" --output "$OUT" | tee "$HERE/.rerun2.log" >/dev/null
H3=$(md5q "$OUT/result.json")
[ "$N1" -ge 8 ]; ok $? "第二次 run 幂等跳过全部 8 个阶段（SKIP=$N1）"
[ "$H1" = "$H2" ] && [ "$H2" = "$H3" ]; ok $? "三次重复运行产物一致（result.json 哈希不变）"

echo "== 5. 负例：锚点不存在的 edit 必须被 qc/finalize 报错 =="
NEGWORK="$HERE/work_neg"; NEGOUT="$HERE/output_neg"
$PY "$RG" run --input "$IN" --work "$NEGWORK" --output "$NEGOUT" > /dev/null 2>&1
cp "$HERE/decisions.json" "$NEGWORK/decisions.json"
$PY - "$HERE/edits.json" "$NEGWORK/edits.json" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
d["edits"].append({"chg_id": "CHG-009", "req_id": "1.1",
                   "anchor_quote": "这句锚点在基线中根本不存在。",
                   "replacement": "不应落稿的替换文本"})
json.dump(d, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
EOF
$PY "$RG" mark --input "$IN" --work "$NEGWORK" --output "$NEGOUT" > "$HERE/neg_mark.log" 2>&1
[ $? -ne 0 ]; ok $? "负例 mark 非零退出"
grep -q "QC 未通过" "$HERE/neg_mark.log"; ok $? "负例 QC 报错（锚点未命中被捕获）"
$PY "$FZ" --case "$IN/case.json" --work "$NEGWORK" --output "$NEGOUT" > "$HERE/neg_finalize.log" 2>&1
[ $? -ne 0 ]; ok $? "负例 finalize 非零退出"
grep -q "FINALIZE-ERROR" "$HERE/neg_finalize.log"; ok $? "负例 finalize 报错（FINALIZE-ERROR）"
$PY - "$NEGOUT/result.json" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
assert r["status"] in ("partial", "unable_to_determine"), r["status"]
print("负例 result.json 仍为诚实", r["status"])
EOF
ok $? "负例 result.json 仍诚实落盘"

echo "== 6. 清理负例与临时日志（保留 examples/work 与 examples/output 作为证据）=="
rm -rf "$NEGWORK" "$NEGOUT" "$HERE/neg_mark.log" "$HERE/neg_finalize.log" "$HERE"/.*.log

echo
if [ "$FAIL" -eq 0 ]; then echo "EXAMPLE-ALL-OK"; else echo "EXAMPLE-HAS-FAILURES"; fi
exit $FAIL
