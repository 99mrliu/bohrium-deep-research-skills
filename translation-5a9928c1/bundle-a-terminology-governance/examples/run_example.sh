#!/usr/bin/env bash
# run_example.sh — terminology-governance 端到端合成示例自测
# (a) 抽取候选术语并断言定义模式命中 GB/YSZ/SOFC
# (b) 决议+锁定+export glossary
# (c) 对含禁用变体的合成译文跑审计 → 断言检出 multiple_variants/forbidden_variant
# (d) --apply-lock 回填后重审 → 断言硬性违规清零
# (e) 组装 result.json → 断言合同字段齐全且 status=success
# (f) 埋雷：锁定后强改决议 → verify-lock 必须 LOCK_BROKEN
# 全部断言通过才 exit 0。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
S="$BUNDLE/scripts"
ROOT="$(mktemp -d /tmp/termgov_example.XXXXXX)"
IN="$ROOT/input"; W="$ROOT/work"; O="$ROOT/output"
PASS=0; FAIL=0
ok()  { echo "  [PASS] $1"; PASS=$((PASS+1)); }
bad() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
mkdir -p "$IN" "$W" "$O"
cp "$HERE/source_en.txt" "$IN/source_en.txt"
cp "$HERE/case.json" "$IN/case.json"

echo "=== (a) extract_source + term_extract"
python3 "$S/extract_source.py" --input "$IN" --out "$W/source.md" >/dev/null && ok "extract_source exit 0" || bad "extract_source 失败"
python3 "$S/term_extract.py" --source "$W/source.md" --out "$W/candidates.json" >/dev/null && ok "term_extract exit 0" || bad "term_extract 失败"
python3 - "$W/candidates.json" <<'PY'
import json, sys
c = {x["term"]: x for x in json.load(open(sys.argv[1], encoding="utf-8"))["candidates"]}
for t in ("grain boundary", "yttria-stabilized zirconia", "solid oxide fuel cell"):
    assert t in c, f"未抽到定义术语: {t}"
    assert c[t]["defined_by_pattern"] is True, f"{t} 非定义模式命中"
assert c["grain boundary"].get("abbr") == "GB", "GB 缩写未关联"
print("  [PASS] 定义模式命中 grain boundary/YSZ/SOFC 且缩写关联正确")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "候选术语断言失败"

echo "=== (b) 决议 + 锁定 + glossary"
python3 "$S/termbase.py" init --candidates "$W/candidates.json" --out "$W/termbase.json" >/dev/null
python3 "$S/termbase.py" decide --termbase "$W/termbase.json" --term "grain boundary" --preferred "晶界" --forbid "颗粒边界,晶粒边缘" --reason "材料学标准译名" >/dev/null
python3 "$S/termbase.py" decide --termbase "$W/termbase.json" --term "yttria-stabilized zirconia" --preferred "氧化钇稳定氧化锆" --forbid "钇稳定锆石" --reason "陶瓷学通用译名" >/dev/null
python3 "$S/termbase.py" decide --termbase "$W/termbase.json" --term "solid oxide fuel cell" --preferred "固体氧化物燃料电池" --forbid "固态氧化物燃料电池" --reason "电化学标准译名" >/dev/null
python3 "$S/termbase.py" decide --termbase "$W/termbase.json" --term "Σ3" --keep-original --reason "晶体学取向记号保留原文" >/dev/null
python3 "$S/termbase.py" decide --termbase "$W/termbase.json" --term "segregation" --preferred "偏聚" --sense "溶质在晶界处的富集，非种族隔离义" --reason "材料学义项锁定" >/dev/null
python3 "$S/termbase.py" lock --termbase "$W/termbase.json" >/dev/null && ok "lock exit 0" || bad "lock 失败"
python3 "$S/termbase.py" verify-lock --termbase "$W/termbase.json" >/dev/null && ok "verify-lock 初始通过" || bad "verify-lock 初始失败"
python3 "$S/termbase.py" export-glossary --termbase "$W/termbase.json" --out "$W/glossary.md" >/dev/null && ok "export-glossary exit 0" || bad "export-glossary 失败"

echo "=== (c) 审计坏译文（应检出 forbidden/multiple 违规，exit 1）"
cp "$HERE/translations_bad.json" "$W/translations.json"
python3 "$S/consistency_audit.py" --termbase "$W/termbase.json" --translations "$W/translations.json" \
    --source "$W/source.md" --out "$W/violations.json" --report "$O/audit_report.md" >/dev/null 2>&1
rc=$?
[ $rc -eq 1 ] && ok "坏译文审计 exit 1" || bad "坏译文审计 exit=$rc（期望 1）"
python3 - "$W/violations.json" <<'PY'
import json, sys
v = json.load(open(sys.argv[1], encoding="utf-8"))
classes = {x["term"]: x["class"] for x in v["violations"]}
assert classes.get("solid oxide fuel cell") in ("multiple_variants", "forbidden_variant"), f"SOFC 违规未检出: {classes}"
print(f"  [PASS] 检出 SOFC 违规={classes['solid oxide fuel cell']}；共 {len(v['violations'])} 项")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "违规检出断言失败"

echo "=== (d) apply-lock 回填后重审（应 exit 0）"
python3 "$S/consistency_audit.py" --termbase "$W/termbase.json" --translations "$W/translations.json" \
    --source "$W/source.md" --out "$W/violations2.json" --report "$O/audit_report.md" --apply-lock >/dev/null 2>&1
python3 "$S/consistency_audit.py" --termbase "$W/termbase.json" --translations "$W/translations.json" \
    --source "$W/source.md" --out "$W/violations2.json" --report "$O/audit_report.md" >/dev/null 2>&1
rc=$?
[ $rc -eq 0 ] && ok "回填后审计 exit 0" || bad "回填后审计 exit=$rc"
python3 - "$W/translations.json" <<'PY'
import json, sys
segs = json.load(open(sys.argv[1], encoding="utf-8"))["segments"]
assert not any("固态氧化物燃料电池" in s["translation"] for s in segs), "禁用变体仍存在"
assert sum("固体氧化物燃料电池" in s["translation"] for s in segs) == 2, "回填数量不对"
print("  [PASS] 禁用变体已回填为锁定译名（2 处）")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "回填断言失败"

echo "=== (e) 组装 result.json"
python3 "$S/assemble_result.py" --case "$IN/case.json" --translations "$W/translations.json" \
    --termbase "$W/termbase.json" --violations "$W/violations2.json" --out "$O" >/dev/null && ok "assemble exit 0" || bad "assemble 失败"
python3 - "$O/result.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
for k in ("case_id", "status", "translated_text", "bilingual", "terminology", "uncertainties"):
    assert k in r, f"缺字段 {k}"
assert r["status"] == "success", f"status={r['status']}"
assert len(r["bilingual"]) == 5 and len(r["terminology"]) >= 5
print(f"  [PASS] result.json 合同字段齐全, status=success, bilingual=5, terminology={len(r['terminology'])}")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "result.json 断言失败"

echo "=== (f) 埋雷：锁定后强改决议 → verify-lock 必须失败"
python3 "$S/termbase.py" decide --termbase "$W/termbase.json" --term "grain boundary" --preferred "颗粒边界" --force >/dev/null 2>&1
python3 "$S/termbase.py" verify-lock --termbase "$W/termbase.json" >/dev/null 2>&1
rc=$?
[ $rc -eq 1 ] && ok "篡改后 verify-lock exit 1 (LOCK_BROKEN)" || bad "verify-lock exit=$rc（期望 1）"
python3 "$S/consistency_audit.py" --termbase "$W/termbase.json" --translations "$W/translations.json" \
    --source "$W/source.md" --out /dev/null --report /dev/null >/dev/null 2>&1
rc=$?
[ $rc -eq 2 ] && ok "篡改后审计拒绝出报告 exit 2" || bad "审计 exit=$rc（期望 2）"

echo "=== 汇总: PASS=$PASS FAIL=$FAIL （工作目录 $ROOT）"
[ $FAIL -eq 0 ] && { echo "ALL ASSERTIONS PASSED"; exit 0; } || { echo "ASSERTIONS FAILED"; exit 1; }
