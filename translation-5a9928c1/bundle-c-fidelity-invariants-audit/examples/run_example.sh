#!/usr/bin/env bash
# run_example.sh — fidelity-invariants-audit 端到端合成示例自测
# (a) 源文不变量抽取（数量/统计量/引用/编号/否定/限定均>0）
# (b) 坏译文审计 exit 1，且必须检出全部 planted errors：
#     p 值改写、HR 改写、引用 [1,2] 丢失、凭空增加 20%、否定丢失、限定升格
# (c) 好译文审计 exit 0（仅单位惯例提示）
# (d) 组装：好 → status=success；坏 → status=partial
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
S="$BUNDLE/scripts"
ROOT="$(mktemp -d /tmp/fidelity_example.XXXXXX)"
IN="$ROOT/input"; W="$ROOT/work"; O="$ROOT/output"; O2="$ROOT/output_bad"
PASS=0; FAIL=0
ok()  { echo "  [PASS] $1"; PASS=$((PASS+1)); }
bad() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
mkdir -p "$IN" "$W" "$O" "$O2"
cp "$HERE/source_en.txt" "$IN/source_en.txt"
cp "$HERE/case.json" "$IN/case.json"
cp "$HERE/source_en.txt" "$W/source.md"

echo "=== (a) 源文不变量抽取"
python3 "$S/extract_invariants.py" --text "$W/source.md" --out "$W/invariants_src.json" >/dev/null && ok "extract exit 0" || bad "extract 失败"
python3 - "$W/invariants_src.json" <<'PY'
import json, sys
from collections import Counter
inv = json.load(open(sys.argv[1], encoding="utf-8"))["invariants"]
c = Counter(i["kind"] for i in inv)
for k in ("quantity", "statistic", "citation", "ref", "negation", "qualifier"):
    assert c.get(k, 0) > 0, f"类别 {k} 未抽到"
stats = [i["normalized"] for i in inv if i["kind"] == "statistic"]
assert "p<0.01" in stats and "ci95" in stats and "p=0.42" in stats, f"统计量缺失: {stats}"
print(f"  [PASS] 六类不变量齐: {dict(c)}")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "不变量抽取断言失败"

echo "=== (b) 坏译文审计（应 exit 1 且检出全部 planted errors）"
python3 "$S/audit_invariants.py" --translations "$HERE/translations_bad.json" --source "$W/source.md" \
    --out "$W/audit_bad.json" --review "$O2/human_review.md" >/dev/null 2>&1
rc=$?
[ $rc -eq 1 ] && ok "坏译文审计 exit 1" || bad "坏译文审计 exit=$rc"
python3 - "$W/audit_bad.json" <<'PY'
import json, sys
a = json.load(open(sys.argv[1], encoding="utf-8"))
s = a["summary"]
assert s.get("changed", 0) >= 2, f"changed={s}"
assert s.get("missing", 0) >= 2, f"missing={s}"
assert s.get("added", 0) >= 1, f"added={s}"
assert s.get("negation_lost", 0) == 1, f"negation_lost={s}"
assert s.get("qualifier_lost", 0) == 1, f"qualifier_lost={s}"
flat = [(g["id"], i) for g in a["segments"] for i in g["issues"]]
assert any(i["class"] == "changed" and "p<0.01" in str(i.get("from")) for _, i in flat), "p 值改写未检出"
assert any(i["class"] == "changed" and "hr=0.72" in str(i.get("from")) for _, i in flat), "HR 改写未检出"
assert any(i["class"] == "missing" and i.get("kind") == "citation" and i.get("value") == "1,2" for _, i in flat), "引用丢失未检出"
assert any(i["class"] == "added" and i.get("value") == "20" for _, i in flat), "凭空增数未检出"
print(f"  [PASS] planted errors 全部检出: {s}")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "planted errors 断言失败"

echo "=== (c) 好译文审计（应 exit 0）"
python3 "$S/audit_invariants.py" --translations "$HERE/translations_good.json" --source "$W/source.md" \
    --out "$W/audit_good.json" --review "$O/human_review.md" >/dev/null 2>&1
rc=$?
[ $rc -eq 0 ] && ok "好译文审计 exit 0" || bad "好译文审计 exit=$rc"
[ -s "$O/human_review.md" ] && ok "人工确认清单已生成" || bad "human_review.md 缺失"

echo "=== (d) 组装 result.json"
python3 "$S/assemble_result.py" --case "$IN/case.json" --translations "$HERE/translations_good.json" \
    --audit "$W/audit_good.json" --out "$O" >/dev/null && ok "assemble(good) exit 0" || bad "assemble(good) 失败"
python3 - "$O/result.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
for k in ("case_id", "status", "translated_text", "bilingual", "uncertainties"):
    assert k in r, f"缺字段 {k}"
assert r["status"] == "success", f"status={r['status']}"
assert len(r["bilingual"]) == 6
assert any(u.get("class") == "unit_convention" for u in r["uncertainties"]), "惯例提示未入 uncertainties"
print("  [PASS] result.json 合同齐全, status=success, uncertainties 含惯例提示")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "result.json(good) 断言失败"
python3 "$S/assemble_result.py" --case "$IN/case.json" --translations "$HERE/translations_bad.json" \
    --audit "$W/audit_bad.json" --out "$O2" >/dev/null && ok "assemble(bad) exit 0" || bad "assemble(bad) 失败"
python3 - "$O2/result.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
assert r["status"] == "partial", f"status={r['status']}"
assert r["audit"].get("changed", 0) >= 2, "审计摘要未入 result"
print("  [PASS] 坏译文 → status=partial, 审计摘要随附")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "result.json(bad) 断言失败"

echo "=== 汇总: PASS=$PASS FAIL=$FAIL （工作目录 $ROOT）"
[ $FAIL -eq 0 ] && { echo "ALL ASSERTIONS PASSED"; exit 0; } || { echo "ASSERTIONS FAILED"; exit 1; }
