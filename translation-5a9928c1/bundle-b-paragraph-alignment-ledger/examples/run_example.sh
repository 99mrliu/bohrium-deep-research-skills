#!/usr/bin/env bash
# run_example.sh — paragraph-alignment-ledger 端到端合成示例自测
# (a) 分段：12 块、断词修复 1、换行合并 4，全部留痕
# (b) 台账：pending 数正确
# (c) 拒绝测试：未知 ID / 源文本被篡改（错位）→ apply exit 1
# (d) 完整回填 → report 全绿 exit 0 → 对齐导出 result.json 合同字段齐全 status=success
# (e) 缺段测试：删一段 → report exit 1、result status=partial
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
S="$BUNDLE/scripts"
ROOT="$(mktemp -d /tmp/align_example.XXXXXX)"
IN="$ROOT/input"; W="$ROOT/work"; O="$ROOT/output"
PASS=0; FAIL=0
ok()  { echo "  [PASS] $1"; PASS=$((PASS+1)); }
bad() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
mkdir -p "$IN" "$W" "$O"
cp "$HERE/source_paged.txt" "$IN/source_paged.txt"
cp "$HERE/case.json" "$IN/case.json"

echo "=== (a) 分段 + 修复留痕"
python3 "$S/segment_docs.py" run --input "$IN" --out "$W/segments.json" >/dev/null && ok "segment run exit 0" || bad "segment run 失败"
python3 "$S/segment_docs.py" repair-report --segments "$W/segments.json" --out "$W/repair_report.md" >/dev/null
python3 - "$W/segments.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
segs = d["segments"]
assert len(segs) == 12, f"段数={len(segs)}（期望 12）"
kinds = [s["kind"] for s in segs]
assert kinds.count("caption") == 1 and kinds.count("heading") == 4, f"kinds={kinds}"
assert any(s["page"] == 2 for s in segs), "分页未识别"
rep = d["repairs"]
assert sum(r["type"] == "dehyphen" for r in rep) == 1, "断词修复≠1"
assert sum(r["type"] == "join-line" for r in rep) == 4, "换行合并≠4"
assert any("electrical" in s["text"] for s in segs), "dehyphen 未生效"
print("  [PASS] 12 段/题注/4 标题/跨页；dehyphen=1 join=4 且全部留痕")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "分段断言失败"

echo "=== (b) 台账初始化"
python3 "$S/coverage.py" init --segments "$W/segments.json" --out "$W/ledger.json" >/dev/null && ok "init exit 0" || bad "init 失败"
python3 "$S/coverage.py" list-pending --ledger "$W/ledger.json" 2>&1 | grep -q "0/12 done, 12 pending" \
    && ok "初始 12 pending" || bad "初始 pending 数不对"

echo "=== (c1) 拒绝未知 ID"
python3 - <<PY
import json
items = json.load(open("$HERE/translations_full.json", encoding="utf-8"))["segments"][:2]
items[0]["id"] = "p999"
json.dump({"segments": items}, open("$W/tr_unknown.json", "w", encoding="utf-8"), ensure_ascii=False)
PY
python3 "$S/coverage.py" apply --ledger "$W/ledger.json" --translations "$W/tr_unknown.json" >/dev/null 2>&1
rc=$?
[ $rc -eq 1 ] && ok "未知 ID 被拒 exit 1" || bad "未知 ID exit=$rc"

echo "=== (c2) 拒绝错位（篡改 source 一个字符）"
python3 - <<PY
import json
items = json.load(open("$HERE/translations_full.json", encoding="utf-8"))["segments"][:2]
items[1]["source"] = items[1]["source"] + " [tampered]"
json.dump({"segments": items}, open("$W/tr_stale.json", "w", encoding="utf-8"), ensure_ascii=False)
PY
python3 "$S/coverage.py" apply --ledger "$W/ledger.json" --translations "$W/tr_stale.json" >/dev/null 2>&1
rc=$?
[ $rc -eq 1 ] && ok "错位/陈旧被拒 exit 1" || bad "错位 exit=$rc"

echo "=== (d) 完整回填 → 全绿导出"
cp "$HERE/translations_full.json" "$W/translations.json"
python3 "$S/coverage.py" apply --ledger "$W/ledger.json" --translations "$W/translations.json" >/dev/null && ok "apply 12 段" || bad "apply 失败"
python3 "$S/coverage.py" apply --ledger "$W/ledger.json" --translations "$W/translations.json" >/dev/null && ok "幂等重跑 apply" || bad "幂等 apply 失败"
python3 "$S/coverage.py" report --ledger "$W/ledger.json" --out "$W/coverage_report.json" >/dev/null && ok "report 全绿 exit 0" || bad "report 未全绿"
python3 "$S/align_export.py" --case "$IN/case.json" --ledger "$W/ledger.json" \
    --translations "$W/translations.json" --out "$O" >/dev/null && ok "align_export exit 0" || bad "align_export 失败"
python3 - "$O/result.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
for k in ("case_id", "status", "translated_text", "bilingual", "uncertainties"):
    assert k in r, f"缺字段 {k}"
assert r["status"] == "success", f"status={r['status']}"
assert len(r["bilingual"]) == 12
ids = [b["id"] for b in r["bilingual"]]
assert ids == sorted(ids) and len(set(ids)) == 12, "段号乱序或重复"
assert all(b["target"] for b in r["bilingual"]), "存在空译文段"
print("  [PASS] result.json 合同齐全, status=success, 12 段一一对应")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "result.json 断言失败"

echo "=== (e) 缺段 → partial"
python3 - <<PY
import json
items = json.load(open("$HERE/translations_full.json", encoding="utf-8"))["segments"][:-1]
json.dump({"segments": items}, open("$W/tr_missing.json", "w", encoding="utf-8"), ensure_ascii=False)
PY
rm -f "$W/ledger2.json"
python3 "$S/coverage.py" init --segments "$W/segments.json" --out "$W/ledger2.json" >/dev/null
python3 "$S/coverage.py" apply --ledger "$W/ledger2.json" --translations "$W/tr_missing.json" >/dev/null
python3 "$S/coverage.py" report --ledger "$W/ledger2.json" --out "$W/coverage2.json" >/dev/null 2>&1
rc=$?
[ $rc -eq 1 ] && ok "缺段 report exit 1" || bad "缺段 report exit=$rc"
O2="$ROOT/output2"; mkdir -p "$O2"
python3 "$S/align_export.py" --case "$IN/case.json" --ledger "$W/ledger2.json" \
    --translations "$W/tr_missing.json" --out "$O2" >/dev/null
python3 - "$O2/result.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
assert r["status"] == "partial", f"status={r['status']}"
u = [x for x in r["uncertainties"] if x.get("type") == "missing_segment"]
assert [x["segment"] for x in u] == ["p012"], f"missing={u}"
print("  [PASS] 缺段 → status=partial, uncertainties 指向 p012")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "partial 断言失败"

echo "=== 汇总: PASS=$PASS FAIL=$FAIL （工作目录 $ROOT）"
[ $FAIL -eq 0 ] && { echo "ALL ASSERTIONS PASSED"; exit 0; } || { echo "ASSERTIONS FAILED"; exit 1; }
