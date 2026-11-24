#!/usr/bin/env bash
# run_example.sh — exp-source-reconciler 合成示例端到端运行
# 对 mock_case.json 依次执行 extract / reconcile / pdfscan，输出写到 examples/output/。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/output"
SCRIPT="$HERE/../scripts/case_reconcile.py"
PY="${PYTHON:-python3}"
NOTICE="合成示例输出，非正式测评结果"

mkdir -p "$OUT"

echo "== 1/3 extract =="
"$PY" "$SCRIPT" extract --case "$HERE/mock_case.json" --outdir "$OUT"

echo "== 2/3 reconcile =="
"$PY" "$SCRIPT" reconcile --case "$HERE/mock_case.json" \
  --facts "$OUT/facts.json" --out "$OUT/reconcile_report.json"

echo "== 3/3 pdfscan =="
"$PY" "$SCRIPT" pdfscan --inputdir "$HERE" \
  --case "$HERE/mock_case.json" --out "$OUT/pdf_excerpts.md"

# 给示例输出头部注入"合成示例输出"标注（正式运行时脚本输出不含此标注）
"$PY" - "$OUT" "$NOTICE" <<'PYEOF'
import json, os, sys
outdir, notice = sys.argv[1], sys.argv[2]
for fn in sorted(os.listdir(outdir)):
    p = os.path.join(outdir, fn)
    if fn.endswith(".json"):
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        data = {"_notice": notice, **data}
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
    elif fn.endswith(".md"):
        with open(p, encoding="utf-8") as f:
            text = f.read()
        with open(p, "w", encoding="utf-8") as f:
            f.write("> %s\n\n" % notice + text)
print("[run_example] notice injected into outputs")
PYEOF

echo "== done: outputs in $OUT =="
ls -1 "$OUT"
