#!/usr/bin/env bash
# run_example.sh — dataset-veritas-gate 端到端合成示例自测
# (a) 生成合成数据 → pipeline_a run → 断言 result.json 9 字段、status、重复剔除=2
# (b) source_audit 断言检出 TEXT affinity 与跨源一致结论
# (c) ledger_gate 好例 exit 0
# (d) 埋雷：篡改 cleaned_table.csv → exit 1 且 CLEANED_HASH_MISMATCH；
#     篡改台账行数 → exit 1 且 LEDGER_CLOSURE_MISMATCH
# 全部断言通过本脚本才 exit 0。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
SCRIPTS="$BUNDLE/scripts"

ROOT="$(mktemp -d /tmp/veritas_example.XXXXXX)"
INPUT="$ROOT/input"; WORK="$ROOT/work"; OUT="$ROOT/output"
PASS=0; FAIL=0
ok()  { echo "  [PASS] $1"; PASS=$((PASS+1)); }
bad() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

echo "=== (0) 生成合成示例数据 → $INPUT"
python3 "$HERE/make_synthetic.py" --out "$INPUT" || { echo "make_synthetic 失败"; exit 1; }

echo "=== (a) pipeline_a run（好例）"
mkdir -p "$WORK" "$OUT"
python3 "$SCRIPTS/pipeline_a.py" run --input-dir "$INPUT" --work-dir "$WORK" --output-dir "$OUT"
rc=$?
[ $rc -eq 0 ] && ok "pipeline_a run exit 0" || bad "pipeline_a run exit=$rc"

python3 - "$OUT/result.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
req = ["case_id","status","cleaning","descriptive","hypothesis_test",
       "effect_size","confidence_interval","interpretation","limitations"]
missing = [k for k in req if k not in r]
assert not missing, f"缺字段: {missing}"
assert r["status"] == "ok", f"status={r['status']}"
assert r["cleaning"]["duplicates_removed"] == 2, \
    f"duplicates_removed={r['cleaning']['duplicates_removed']}"
assert r["cleaning"]["closure_holds"] is True, "闭合律不成立"
assert r["cleaning"]["rows_raw"] == 29 and r["cleaning"]["rows_kept"] == 27, \
    f"rows {r['cleaning']['rows_raw']}→{r['cleaning']['rows_kept']}"
assert r["cleaning"]["outliers_flagged"].get("height_cm", 0) == 1, \
    f"outliers={r['cleaning']['outliers_flagged']}"
assert r["group_column"] == "group", f"group_column={r['group_column']}"
assert "height_cm" in r["hypothesis_test"], "height_cm 未推断"
for extra in ("sources","reproducibility","uncertainty","exceptions","decisions"):
    assert extra in r, f"缺附加字段 {extra}"
print("  [PASS] result.json: 9 字段齐全, status=ok, dup=2, outlier=1, group=group")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "result.json 断言失败"

echo "=== (b) source_audit 断言"
python3 "$SCRIPTS/source_audit.py" run --input-dir "$INPUT" --work-dir "$WORK" >/dev/null
python3 - "$WORK/source_audit.json" <<'PY'
import json, sys
a = json.load(open(sys.argv[1], encoding="utf-8"))
db = next(d for d in a["dbs"] if d["file"] == "plants.db")
t = db["tables"][0]
hc = next(c for c in t["columns"] if c["name"] == "height_cm")
assert hc["affinity"] == "TEXT", f"height_cm affinity={hc['affinity']}"
assert hc["numeric_in_text"] is True, "numeric-in-text 未检出"
cs = a["cross_source"][0]
assert cs["rows_equal"] is True and cs["n_value_mismatch"] == 0, f"cross={cs['verdict']}"
assert cs["verdict"] == "consistent_with_type_coercion", f"verdict={cs['verdict']}"
print("  [PASS] source_audit: TEXT affinity + numeric-in-text 检出, 跨源一致(带类型强转)")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "source_audit 断言失败"

echo "=== (c) ledger_gate 好例（应 exit 0）"
python3 "$SCRIPTS/ledger_gate.py" check --input-dir "$INPUT" --work-dir "$WORK" > "$ROOT/gate_good.log" 2>&1
rc=$?
[ $rc -eq 0 ] && ok "ledger_gate 好例 exit 0" || { bad "ledger_gate 好例 exit=$rc"; cat "$ROOT/gate_good.log"; }
grep -q "PASS" "$ROOT/gate_good.log" && ok "ledger_gate 输出 PASS 明细" || bad "无 PASS 明细"

echo "=== (d1) 埋雷：篡改 cleaned_table.csv 一行"
WT1="$ROOT/work_t1"; cp -r "$WORK" "$WT1"
python3 - "$WT1/cleaned_table.csv" <<'PY'
import sys
p = sys.argv[1]
lines = open(p, encoding="utf-8").read().splitlines()
lines[1] = lines[1].replace("21.3", "99.9")   # 篡改一个数值
open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
python3 "$SCRIPTS/ledger_gate.py" check --input-dir "$INPUT" --work-dir "$WT1" > "$ROOT/gate_t1.log" 2>&1
rc=$?
[ $rc -eq 1 ] && ok "篡改 cleaned → exit 1" || bad "篡改 cleaned exit=$rc（期望 1）"
grep -q "CLEANED_HASH_MISMATCH" "$ROOT/gate_t1.log" \
    && ok "命中 CLEANED_HASH_MISMATCH" || { bad "未命中 CLEANED_HASH_MISMATCH"; cat "$ROOT/gate_t1.log"; }

echo "=== (d2) 埋雷：篡改台账 rows_kept"
WT2="$ROOT/work_t2"; cp -r "$WORK" "$WT2"
python3 - "$WT2/cleaning_ledger.json" <<'PY'
import json, sys
p = sys.argv[1]
led = json.load(open(p, encoding="utf-8"))
led["rows_kept"] = led["rows_kept"] + 1   # 篡改行数
json.dump(led, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
python3 "$SCRIPTS/ledger_gate.py" check --input-dir "$INPUT" --work-dir "$WT2" > "$ROOT/gate_t2.log" 2>&1
rc=$?
[ $rc -eq 1 ] && ok "篡改台账行数 → exit 1" || bad "篡改台账 exit=$rc（期望 1）"
grep -q "LEDGER_CLOSURE_MISMATCH" "$ROOT/gate_t2.log" \
    && ok "命中 LEDGER_CLOSURE_MISMATCH" || { bad "未命中 LEDGER_CLOSURE_MISMATCH"; cat "$ROOT/gate_t2.log"; }

echo "=== (e) decide + finalize 冒烟"
python3 "$SCRIPTS/pipeline_a.py" decide --work-dir "$WORK" --output-dir "$OUT" \
    --key alpha --value 0.01 --reason "合成示例冒烟测试" >/dev/null \
    && ok "decide exit 0" || bad "decide 失败"
python3 "$SCRIPTS/pipeline_a.py" finalize --work-dir "$WORK" --output-dir "$OUT" >/dev/null
rc=$?
python3 - "$OUT/result.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
ht = r["hypothesis_test"]["height_cm"]
assert ht["alpha"] == 0.01, f"alpha={ht['alpha']}"
assert any(d["key"] == "alpha" and d["source"] == "agent" for d in r["decisions"])
print("  [PASS] finalize 后 alpha=0.01 且裁决已入账")
PY
[ $rc -eq 0 ] && [ $? -eq 0 ] && PASS=$((PASS+1)) || bad "finalize 断言失败"
# 恢复 alpha 供 example_output 使用默认口径
python3 "$SCRIPTS/pipeline_a.py" decide --work-dir "$WORK" --output-dir "$OUT" \
    --key alpha --value 0.05 --reason "恢复默认" >/dev/null
python3 "$SCRIPTS/pipeline_a.py" finalize --work-dir "$WORK" --output-dir "$OUT" >/dev/null

echo "=== 汇总: PASS=$PASS FAIL=$FAIL （工作目录 $ROOT）"
[ $FAIL -eq 0 ] && { echo "ALL ASSERTIONS PASSED"; exit 0; } || { echo "ASSERTIONS FAILED"; exit 1; }
