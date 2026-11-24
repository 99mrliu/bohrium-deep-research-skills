#!/usr/bin/env bash
# run_example.sh — 合成示例端到端演示：extract_refs → lint_refs → crossref_check(--offline)
# → 汇总 result.json。有网时额外跑一次在线核验写入 crossref_online.json（不阻断主流程）。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
OUT="$HERE/output"
mkdir -p "$OUT"
NOTE="合成示例输出，非正式测评结果"

echo "== [1/4] extract_refs =="
python3 "$ROOT/scripts/extract_refs.py" \
  --input "$HERE/mock_paper.txt" --output "$OUT/refs.json"

echo "== [2/4] lint_refs =="
python3 "$ROOT/scripts/lint_refs.py" \
  --input "$OUT/refs.json" --output "$OUT/lint.json"

echo "== [3/4] crossref_check (offline，演示优雅降级) =="
python3 "$ROOT/scripts/crossref_check.py" \
  --input "$OUT/refs.json" --lint "$OUT/lint.json" \
  --output "$OUT/crossref_offline.json" --offline --max-queries 12

echo "== [4/4] 汇总 result.json =="
python3 - "$HERE" "$OUT" "$NOTE" <<'PY'
import json, sys, os, datetime
here, out, note = sys.argv[1], sys.argv[2], sys.argv[3]

def load(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return default

case = load(os.path.join(here, "mock_case.json"), {})
refs = load(os.path.join(out, "refs.json"), {})
lint = load(os.path.join(out, "lint.json"), {})
xref = load(os.path.join(out, "crossref_offline.json"), {})

# 给每个中间输出文件头部注入 _note（保持字段顺序：_note 在最前）
for name in ("refs.json", "lint.json", "crossref_offline.json", "crossref_online.json"):
    p = os.path.join(out, name)
    d = load(p, None)
    if isinstance(d, dict) and "_note" not in d:
        d2 = {"_note": note}
        d2.update(d)
        json.dump(d2, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

findings = []
def hint_page(hint):
    if not isinstance(hint, dict):
        return None
    if hint.get("page") is not None:
        return hint.get("page")
    pages = hint.get("pages") or []
    return pages[0] if pages else None

for c in lint.get("candidates") or []:
    findings.append({
        "id": c.get("id"), "type": c.get("type"),
        "severity": c.get("severity_candidate"), "category": c.get("category"),
        "location": {"file": "mock_paper.txt",
                     "page": hint_page(c.get("location_hint")),
                     "quote": (c.get("evidence") or {}).get("raw_excerpt")
                              or (c.get("evidence") or {}).get("context") or ""},
        "evidence": {"rule": c.get("rule"), "detail": c.get("evidence")},
        "suggestion": c.get("suggestion"),
        "verdict_status": c.get("verdict_status"),
        "confidence": c.get("confidence"),
    })
pending = [r.get("ref_index") for r in xref.get("results") or []
           if r.get("status") == "pending_review"]

result = {
    "_note": note,
    "case_id": case.get("case_id", "unknown"),
    "status": "partial",
    "partial_reason": "示例以 --offline 运行，外部核验全部 pending_review；"
                      "本地可判项（lint 候选）照常给出，候选 ≠ 结论。",
    "findings": findings,
    "external_verification": {
        "mode": xref.get("mode"),
        "budget": xref.get("budget"),
        "status_counts": xref.get("status_counts"),
        "pending_review_refs": pending,
        "two_signal_rule": xref.get("two_signal_rule"),
    },
    "not_reviewed": [
        {"facet": "参考文献真实性外部核验", "reason": "offline 模式，断网降级为待复核"},
        {"facet": "claim_citation_mismatch 终裁", "reason": "本地零重叠仅为低置信候选，需人工通读语境与文献"},
    ],
    "uncertainty": "lint 输出全部为非结论候选；合成案例中的 DOI 为虚构，"
                   "在线核验时预期 not_found/不可解析，属预期行为。",
    "sources": ["mock_paper.txt（合成）", "lint_refs.py 本地规则",
                "crossref_check.py --offline（未发起网络请求）"],
    "change_log": [{"at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "action": "example pipeline run (offline)"}],
}
json.dump(result, open(os.path.join(out, "result.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("result.json: %d findings, external pending=%s" % (len(findings), pending))
PY

# 可选：有网时再跑一次真实在线核验（失败不阻断；结果头部含检索时间）
echo "== [optional] crossref_check (online) =="
if python3 "$ROOT/scripts/crossref_check.py" \
    --input "$OUT/refs.json" --lint "$OUT/lint.json" \
    --output "$OUT/crossref_online.json" --max-queries 12; then
  python3 - "$OUT" "$NOTE" <<'PY'
import json, sys, os
out, note = sys.argv[1], sys.argv[2]
p = os.path.join(out, "crossref_online.json")
try:
    d = json.load(open(p, encoding="utf-8"))
    if "_note" not in d:
        d2 = {"_note": note + "；在线检索时间见 generated_at_utc"}
        d2.update(d)
        json.dump(d2, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("online run recorded:", d.get("status_counts"))
except (OSError, ValueError) as e:
    print("online output post-process skipped: %s" % e)
PY
else
  echo "online run failed; offline results remain authoritative"
fi

echo "== done. outputs in: $OUT =="
ls -la "$OUT"
