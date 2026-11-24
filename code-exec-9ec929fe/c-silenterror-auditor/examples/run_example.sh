#!/usr/bin/env bash
# 合成示例端到端运行（silenterror-auditor）。所有数据为人工合成并埋有陷阱，
# 输出不对应任何正式案例结果。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CASE="$HERE/synthetic_case"
WORK="$HERE/work"
OUT="$HERE/out"
AUD="$HERE/../scripts/secaudit.py"
rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"

python3 "$HERE/make_synthetic_data.py" "$CASE/lab.db" >/dev/null

echo "== 1) scan：计算前挖出全部陷阱"
python3 "$AUD" scan "$CASE/readings.csv" "$CASE/lab.db" --out "$WORK/scan_report.json" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); [print(' -', r['file'].split('/')[-1], '->', len(r['risks']), '项风险') for r in d['reports']]"

echo "== 2) 主分析管道（修正版）：去重 + 剔缺失 + 剔哨兵"
python3 "$HERE/main_analysis_demo.py" "$CASE" "$WORK" "$OUT"

echo "== 3) audit 拦截 naive claims（预期 exit 1，演示阻断）"
sed "s|CASEDIR|$CASE|g; s|WORKDIR|$WORK|g" "$HERE/claims_naive.json" > "$WORK/claims_naive.json"
if python3 "$AUD" audit --claims "$WORK/claims_naive.json" --out "$WORK/audit_naive.json"; then
  echo "!! 意外：naive claims 居然通过了"
else
  echo ">> 符合预期：naive claims 被阻断（MISMATCH），禁止交付"
fi

echo "== 4) audit 通过修正版 claims"
sed "s|CASEDIR|$CASE|g; s|WORKDIR|$WORK|g" "$HERE/claims_fixed.json" > "$WORK/claims_fixed.json"
python3 "$AUD" audit --claims "$WORK/claims_fixed.json" --out "$WORK/audit_fixed.json"

echo "== 5) diff：naive 结论 vs 修正结论"
python3 - "$OUT" <<'PY'
import json, sys
out = sys.argv[1]
naive = {"case_id": "synthetic-demo-secaudit-001", "status": "success",
         "summary_statistics": {"n": 9, "mean": -102.11, "std": 330.4,
                                "min": -999.0, "max": 13.0},
         "anomalies": [], "provenance": {"demo": "naive 错误版（演示用）"}}
json.dump(naive, open(out + "/result_naive.json", "w"), ensure_ascii=False, indent=2)
PY
python3 "$AUD" diff --a "$OUT/result_naive.json" --b "$OUT/result_fixed.json" || true

echo "== 产物 =="
ls -la "$WORK" "$OUT"
