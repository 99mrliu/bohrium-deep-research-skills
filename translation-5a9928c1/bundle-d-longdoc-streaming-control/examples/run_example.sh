#!/usr/bin/env bash
# run_example.sh — longdoc-streaming-control 端到端合成示例自测
# (a) 生成合成长文 → 计划：多块、无超预算单元、单元不跨块
# (b) 台账：init + list-pending 全列
# (c) 上下文包：含待译单元、下块头部、术语表节选
# (d) 翻译 c001（合成占位译文）→ mark-done；幂等重跑不重复计预算
# (e) 埋雷：篡改 c002 单元 source → mark-done 拒绝；缺单元 → 拒绝
# (f) 续跑：完成剩余块 → report complete → assemble status=success
# (g) partial 演示：新建台账仅完成一块 → assemble status=partial
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
S="$BUNDLE/scripts"
ROOT="$(mktemp -d /tmp/stream_example.XXXXXX)"
IN="$ROOT/input"; W="$ROOT/work"; O="$ROOT/output"
PASS=0; FAIL=0
ok()  { echo "  [PASS] $1"; PASS=$((PASS+1)); }
bad() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
mkdir -p "$IN" "$W/chunks" "$W/context" "$O"
python3 "$HERE/make_synthetic.py" --out "$IN/synthetic_longdoc.txt"
cp "$HERE/case.json" "$IN/case.json"
printf '# 锁定术语表（合成）\n- **activation energy** → 活化能\n- **selectivity** → 选择性\n' > "$W/glossary.md"

echo "=== (a) 源文 + 切块计划"
python3 "$S/extract_source.py" --input "$IN" --out "$W/source.md" >/dev/null && ok "extract exit 0" || bad "extract 失败"
python3 "$S/plan_chunks.py" --source "$W/source.md" --budget-tokens 150 --out "$W/plan.json" >/dev/null && ok "plan exit 0" || bad "plan exit=$?"
python3 - "$W/plan.json" <<'PY'
import json, sys
p = json.load(open(sys.argv[1], encoding="utf-8"))
assert p["n_chunks"] >= 3, f"块数={p['n_chunks']}（期望≥3）"
assert p["oversized_single_unit_chunks"] == 0, "存在超预算独占块"
assert all(c["est_tokens"] <= p["budget_tokens"] for c in p["chunks"]), "块超预算"
seen = [u["unit_id"] for c in p["chunks"] for u in c["units"]]
assert len(seen) == len(set(seen)) == p["n_units"], "单元跨块或重复"
print(f"  [PASS] {p['n_units']} 单元 → {p['n_chunks']} 块（≤150 估计词元，无切断）")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "计划断言失败"

echo "=== (b) 台账"
python3 "$S/stream_state.py" init --plan "$W/plan.json" --out "$W/state.json" >/dev/null && ok "state init" || bad "state init 失败"
python3 "$S/stream_state.py" list-pending --state "$W/state.json" 2>"$W/pend.log" | grep -q "c001" && ok "list-pending 含 c001" || bad "list-pending 异常"
grep -q "budget left: 64 requests" "$W/pend.log" && ok "预算初始 64/900" || bad "预算初始值不对"

echo "=== (c) 上下文包"
python3 "$S/context_pack.py" --plan "$W/plan.json" --state "$W/state.json" --chunk c002 \
    --glossary "$W/glossary.md" --out "$W/context/c002.md" >/dev/null && ok "context_pack exit 0" || bad "context_pack 失败"
grep -q "待译单元" "$W/context/c002.md" && grep -q "下一块" "$W/context/c002.md" \
    && grep -q "活化能" "$W/context/c002.md" && ok "上下文包含 待译单元+下块头部+术语表" || bad "上下文包内容缺失"

echo "=== (d) 合成翻译 c001 + mark-done + 幂等"
python3 - "$W/plan.json" "$W/chunks" <<'PY'
import json, sys
plan = json.load(open(sys.argv[1], encoding="utf-8"))
for c in plan["chunks"][:1]:
    segs = [{"unit_id": u["unit_id"], "source": u["text"],
             "translation": "⟨SYNTH-ZH⟩" + u["text"]} for u in c["units"]]
    json.dump({"segments": segs}, open(f"{sys.argv[2]}/{c['id']}.translated.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
print("  [信息] 合成占位译文已写（⟨SYNTH-ZH⟩ 前缀，仅演示流水线）")
PY
python3 "$S/stream_state.py" mark-done --state "$W/state.json" --plan "$W/plan.json" \
    --chunk c001 --translations "$W/chunks/c001.translated.json" --requests 1 --seconds 25 >/dev/null \
    && ok "mark-done c001" || bad "mark-done c001 失败"
python3 "$S/stream_state.py" mark-done --state "$W/state.json" --plan "$W/plan.json" \
    --chunk c001 --translations "$W/chunks/c001.translated.json" --requests 1 --seconds 25 >"$W/idem.log" 2>&1 \
    && ok "幂等 mark-done exit 0" || bad "幂等 mark-done 失败"
grep -q "idempotent-skip" "$W/idem.log" && ok "幂等跳过且不计预算" || bad "幂等日志缺失"
python3 - "$W/state.json" <<'PY'
import json, sys
st = json.load(open(sys.argv[1], encoding="utf-8"))
assert st["budget"]["requests_used"] == 1, f"requests_used={st['budget']['requests_used']}"
print("  [PASS] 预算记账 requests_used=1（幂等未重复计入）")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "预算断言失败"

echo "=== (e1) 埋雷：篡改单元 source → 拒绝"
python3 - "$W/plan.json" "$W/chunks" <<'PY'
import json, sys
plan = json.load(open(sys.argv[1], encoding="utf-8"))
c = plan["chunks"][1]
segs = [{"unit_id": u["unit_id"], "source": u["text"] + " [tampered]",
         "translation": "⟨SYNTH-ZH⟩" + u["text"]} for u in c["units"]]
json.dump({"segments": segs}, open(f"{sys.argv[2]}/{c['id']}.tampered.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
PY
python3 "$S/stream_state.py" mark-done --state "$W/state.json" --plan "$W/plan.json" \
    --chunk c002 --translations "$W/chunks/c002.tampered.json" --requests 1 --seconds 25 >/dev/null 2>&1
rc=$?
[ $rc -eq 1 ] && ok "篡改 source 被拒 exit 1" || bad "篡改 exit=$rc"

echo "=== (e2) 缺单元 → 拒绝"
python3 - "$W/plan.json" "$W/chunks" <<'PY'
import json, sys
plan = json.load(open(sys.argv[1], encoding="utf-8"))
c = plan["chunks"][1]
segs = [{"unit_id": u["unit_id"], "source": u["text"],
         "translation": "⟨SYNTH-ZH⟩" + u["text"]} for u in c["units"][:-1]]
json.dump({"segments": segs}, open(f"{sys.argv[2]}/{c['id']}.incomplete.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
PY
python3 "$S/stream_state.py" mark-done --state "$W/state.json" --plan "$W/plan.json" \
    --chunk c002 --translations "$W/chunks/c002.incomplete.json" --requests 1 --seconds 25 >/dev/null 2>&1
rc=$?
[ $rc -eq 1 ] && ok "缺单元被拒 exit 1" || bad "缺单元 exit=$rc"

echo "=== (f) 续跑：完成全部剩余块"
python3 - "$W/plan.json" "$W/chunks" <<'PY'
import json, sys
plan = json.load(open(sys.argv[1], encoding="utf-8"))
for c in plan["chunks"][1:]:
    segs = [{"unit_id": u["unit_id"], "source": u["text"],
             "translation": "⟨SYNTH-ZH⟩" + u["text"]} for u in c["units"]]
    json.dump({"segments": segs}, open(f"{sys.argv[2]}/{c['id']}.translated.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
print(f"  [信息] 其余 {len(plan['chunks']) - 1} 块合成占位译文已写")
PY
for C in $(python3 "$S/stream_state.py" list-pending --state "$W/state.json" 2>/dev/null); do
  python3 "$S/stream_state.py" mark-done --state "$W/state.json" --plan "$W/plan.json" \
    --chunk "$C" --translations "$W/chunks/$C.translated.json" --requests 1 --seconds 25 >/dev/null || bad "mark-done $C"
done
ok "全部块 mark-done"
python3 "$S/stream_state.py" report --state "$W/state.json" --out "$O/state_report.json" >/dev/null
python3 - "$O/state_report.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
assert r["complete"] is True, f"complete={r['complete']}"
assert r["budget"]["requests_used"] == r["chunks_total"], "预算与块数不符"
print(f"  [PASS] report complete=True, 预算 {r['budget']['requests_used']} 请求/{r['budget']['seconds_used']:.0f} 秒")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "report 断言失败"
python3 "$S/assemble_result.py" --case "$IN/case.json" --plan "$W/plan.json" \
    --state "$W/state.json" --translations-dir "$W/chunks" --out "$O" >/dev/null && ok "assemble exit 0" || bad "assemble 失败"
python3 - "$O/result.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
for k in ("case_id", "status", "translated_text", "bilingual", "uncertainties"):
    assert k in r, f"缺字段 {k}"
assert r["status"] == "success", f"status={r['status']}"
assert len(r["bilingual"]) == r["coverage"]["units_total"]
print(f"  [PASS] result.json 合同齐全, status=success, units={len(r['bilingual'])}")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "result.json 断言失败"

echo "=== (g) partial 演示"
W2="$ROOT/work2"; O2="$ROOT/output2"; mkdir -p "$W2/chunks" "$O2"
cp "$W/plan.json" "$W2/plan.json"; cp "$W/chunks/c001.translated.json" "$W2/chunks/"
python3 "$S/stream_state.py" init --plan "$W2/plan.json" --out "$W2/state.json" >/dev/null
python3 "$S/stream_state.py" mark-done --state "$W2/state.json" --plan "$W2/plan.json" \
    --chunk c001 --translations "$W2/chunks/c001.translated.json" --requests 1 --seconds 25 >/dev/null
python3 "$S/assemble_result.py" --case "$IN/case.json" --plan "$W2/plan.json" \
    --state "$W2/state.json" --translations-dir "$W2/chunks" --out "$O2" >/dev/null
python3 - "$O2/result.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
assert r["status"] == "partial", f"status={r['status']}"
assert any(u.get("type") == "untranslated_unit" for u in r["uncertainties"]), "缺块未入 uncertainties"
print("  [PASS] 中断场景 → status=partial 且未译块清单完整")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "partial 断言失败"

echo "=== 汇总: PASS=$PASS FAIL=$FAIL （工作目录 $ROOT）"
[ $FAIL -eq 0 ] && { echo "ALL ASSERTIONS PASSED"; exit 0; } || { echo "ASSERTIONS FAILED"; exit 1; }
