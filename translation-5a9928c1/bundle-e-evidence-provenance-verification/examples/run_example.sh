#!/usr/bin/env bash
# run_example.sh — evidence-provenance-verification 端到端合成示例自测
# (a) 源文 + 构建带证据的译文（quote+offset 由脚本从源文本实际计算）
# (b) 埋雷 1：篡改证据引文 → 核验失败 exit 1
# (c) 埋雷 2：引文截短造成覆盖缺口 → exit 2 且 gap 检出
# (d) 干净版：全部 verified、无 gap → register status=success → result.json 合同齐全
# (e) 诚实版：标注不可读符号与存疑缩写 → status=partial 且未决项入册
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
S="$BUNDLE/scripts"
ROOT="$(mktemp -d /tmp/evidence_example.XXXXXX)"
IN="$ROOT/input"; W="$ROOT/work"; O="$ROOT/output"
PASS=0; FAIL=0
ok()  { echo "  [PASS] $1"; PASS=$((PASS+1)); }
bad() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
mkdir -p "$IN" "$W" "$O"
cp "$HERE/source_en.txt" "$IN/source_en.txt"
cp "$HERE/case.json" "$IN/case.json"

echo "=== (a) 源文 + 构建带证据译文"
python3 "$S/extract_source.py" --input "$IN" --out "$W/source.md" >/dev/null && ok "extract exit 0" || bad "extract 失败"
python3 - "$W/source.md" "$W" <<'PY'
import json, sys
src = open(sys.argv[1], encoding="utf-8").read()
W = sys.argv[2]
ZH = {
 "p001": "流式语言模型的一致估计量",
 "p002": "摘要",
 "p003": "流式语言模型必须在不回访全量语料的前提下更新。我们证明：在漂移量 Δ ≤ 0.1 有界时，滑动窗口估计量（SWE）是一致的，且 regret 按 O(√T log T) 增长。窗口大小 w 在内存与偏差之间折中；实践中 w = 512 在各类任务上均适用。",
 "p004": "方法",
 "p005": "SWE 保留容量为 w 的样本库并按新近度重加权。当特征 � 被量化噪声破坏时，估计量退化为半衰期 h = 24 h 的指数衰减。全部超参数遵循文献 [4] 的方案。",
 "p006": "图 1. 三种漂移情形下 regret 随窗口大小的变化。",
}
NOTES = {
 "p001": ("literal", "标题直译；Streaming 取流式"),
 "p002": ("literal", "章节标题直译"),
 "p003": ("termbase", "regret 按强化学习惯例保留英文并给中文说明；SWE 首次出现给全称（滑动窗口估计量）"),
 "p004": ("literal", "章节标题直译"),
 "p005": ("convention", "half-life 译为半衰期并按物理惯例给符号 h"),
 "p006": ("literal", "题注直译，Figure→图"),
}
parts = [
 ("p001", "Consistent Estimators for Streaming Language Models"),
 ("p002", "Abstract"),
 ("p003", "Streaming language models must update without revisiting the full corpus. We prove that the sliding-window estimator (SWE) is consistent under drift bounded by Δ ≤ 0.1, and the regret grows as O(√T log T). The window size w trades memory against bias; in practice w = 512 works across tasks."),
 ("p004", "Methods"),
 ("p005", "The SWE keeps a reservoir of w examples and reweights them by recency. When the feature � is corrupted by quantization noise, the estimator falls back to exponential decay with half-life h = 24 h. All hyperparameters follow the protocol of [4]."),
 ("p006", "Figure 1. Regret versus window size for three drift regimes."),
]
segs = []
for sid, quote in parts:
    start = src.find(quote)
    assert start >= 0, f"quote 未找到: {sid}"
    basis, note = NOTES[sid]
    segs.append({"id": sid, "source": quote, "translation": ZH[sid],
                 "evidence": {"quote": quote, "start": start, "basis": basis, "note": note},
                 "uncertainty": None})
json.dump({"segments": segs}, open(f"{W}/translations_clean.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
# 埋雷 1：篡改 p002 的引文（错字）
bad1 = json.loads(json.dumps({"segments": segs}, ensure_ascii=False))
bad1["segments"][2]["evidence"]["quote"] = bad1["segments"][2]["evidence"]["quote"].replace(
    "consistent", "consistant")
json.dump(bad1, open(f"{W}/translations_tampered.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
# 埋雷 2：p003 引文截短（制造覆盖缺口）
bad2 = json.loads(json.dumps({"segments": segs}, ensure_ascii=False))
q = bad2["segments"][4]["evidence"]["quote"]
bad2["segments"][4]["evidence"]["quote"] = q[:len(q) // 2]
json.dump(bad2, open(f"{W}/translations_gap.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
# 诚实版：标注不可读符号与存疑缩写
honest = json.loads(json.dumps({"segments": segs}, ensure_ascii=False))
honest["segments"][4]["uncertainty"] = {"type": "unreadable",
    "detail": "源文本 offset 附近符号不可读（�），译文中按占位符保留"}
honest["segments"][2]["evidence"]["basis"] = "uncertain"
honest["segments"][2]["evidence"]["note"] = "SWE 缩写或指 sliding-window estimator 或 stochastic weight erosion，需人工确认"
json.dump(honest, open(f"{W}/translations_honest.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("  [信息] 4 份合成译文已构建（clean/tampered/gap/honest）")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "译文构建失败"

echo "=== (b) 埋雷 1：篡改引文 → 核验失败"
python3 "$S/anchor_evidence.py" --source "$W/source.md" --translations "$W/translations_tampered.json" \
    --out "$W/ev_tampered.json" >/dev/null 2>&1
rc=$?
[ $rc -eq 1 ] && ok "篡改引文 exit 1" || bad "篡改引文 exit=$rc"
python3 - "$W/ev_tampered.json" <<'PY'
import json, sys
e = json.load(open(sys.argv[1], encoding="utf-8"))
v = {s["id"]: s["verdict"] for s in e["segments"]}
assert v["p003"] in ("offset_mismatch", "quote_not_found"), f"p003 verdict={v['p003']}"
assert v["p001"] == "verified", "正常段应 verified"
print(f"  [PASS] 检出篡改段 p003={v['p003']}，其余段 verified")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "篡改检出断言失败"

echo "=== (c) 埋雷 2：引文截短 → 覆盖缺口 exit 2"
python3 "$S/anchor_evidence.py" --source "$W/source.md" --translations "$W/translations_gap.json" \
    --out "$W/ev_gap.json" >/dev/null 2>&1
rc=$?
[ $rc -eq 2 ] && ok "覆盖缺口 exit 2" || bad "覆盖缺口 exit=$rc"
python3 - "$W/ev_gap.json" <<'PY'
import json, sys
e = json.load(open(sys.argv[1], encoding="utf-8"))
assert e["counts"]["gaps"] >= 1, "缺口未检出"
print(f"  [PASS] 缺口检出 {e['counts']['gaps']} 处: {e['coverage']['gaps'][0]['preview'][:50]}…")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "缺口检出断言失败"

echo "=== (d) 干净版 → success"
python3 "$S/anchor_evidence.py" --source "$W/source.md" --translations "$W/translations_clean.json" \
    --out "$W/ev_clean.json" >/dev/null 2>&1 && ok "anchor(clean) exit 0" || bad "anchor(clean) exit=$?"
python3 "$S/uncertainty_register.py" --translations "$W/translations_clean.json" \
    --evidence "$W/ev_clean.json" --out "$W/register_clean.json" >/dev/null && ok "register exit 0" || bad "register 失败"
python3 "$S/verification_report.py" --translations "$W/translations_clean.json" \
    --evidence "$W/ev_clean.json" --register "$W/register_clean.json" \
    --out "$O/verification_report.md" >/dev/null && ok "verification_report exit 0" || bad "报告失败"
python3 "$S/assemble_result.py" --case "$IN/case.json" --translations "$W/translations_clean.json" \
    --evidence "$W/ev_clean.json" --register "$W/register_clean.json" --out "$O" >/dev/null \
    && ok "assemble exit 0" || bad "assemble 失败"
python3 - "$O/result.json" "$O/verification_report.md" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
for k in ("case_id", "status", "translated_text", "bilingual", "uncertainties"):
    assert k in r, f"缺字段 {k}"
assert r["status"] == "success", f"status={r['status']}"
assert all(b["evidence"]["verdict"] == "verified" for b in r["bilingual"])
assert r["evidence_map"]["coverage"]["gaps"] == 0
rep = open(sys.argv[2], encoding="utf-8").read()
assert "逐段证据" in rep and "译法依据" in rep
print("  [PASS] result.json 合同齐全, status=success, 全部证据 verified, 报告含译法依据")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "result.json 断言失败"

echo "=== (e) 诚实版 → partial（不可读+存疑入册）"
python3 "$S/anchor_evidence.py" --source "$W/source.md" --translations "$W/translations_honest.json" \
    --out "$W/ev_honest.json" >/dev/null 2>&1
python3 "$S/uncertainty_register.py" --translations "$W/translations_honest.json" \
    --evidence "$W/ev_honest.json" --out "$W/register_honest.json" >/dev/null
python3 - "$W/register_honest.json" <<'PY'
import json, sys
g = json.load(open(sys.argv[1], encoding="utf-8"))
assert g["status"] == "partial", f"status={g['status']}"
types = {r["type"] for r in g["register"]}
assert "unreadable" in types and "uncertain_basis" in types, f"types={types}"
print(f"  [PASS] 诚实版 status=partial, 未决项: {sorted(types)}")
PY
[ $? -eq 0 ] && PASS=$((PASS+1)) || bad "诚实版断言失败"

echo "=== 汇总: PASS=$PASS FAIL=$FAIL （工作目录 $ROOT）"
[ $FAIL -eq 0 ] && { echo "ALL ASSERTIONS PASSED"; exit 0; } || { echo "ASSERTIONS FAILED"; exit 1; }
